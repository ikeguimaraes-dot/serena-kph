"""Consented, tenant-bound follow-ups with a durable single-attempt outbox.

Defaults: preview only, all rules disabled, no inferred consent or template approval.
Provider acceptance (SID) is separate from delivery. Ambiguous attempts never retry.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
import database as db

STAGES = ("nurture_d3", "d1", "d3", "d7", "d30")
WINDOWS = {"d1": (20, 30, None), "d3": (68, 80, "d1"),
           "d7": (168, 192, "d3"), "d30": (720, 768, "d7")}
LEGACY_TEMPLATES = {"d1": "HX7a16cfb714c360daa4cb1dd391839f1a",
                    "d3": "HXe90e74853e6f43815ed076964f39030b",
                    "d7": "HXaacf87d6d7d582ff3a26c98bd41b9637",
                    "d30": "HX2f99ec2032087dc650b2e84047345048"}
PHONE = re.compile(r"^\+[1-9][0-9]{7,14}$")
MESSAGE_SID = re.compile(r"^SM[0-9a-fA-F]{32}$")


def utcnow():
    return datetime.now(timezone.utc)


def sending_enabled():
    return os.environ.get("SERENA_OUTREACH_SEND_ENABLED", "").lower() == "true"


class ConsentChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    granted: bool
    source: Literal["form", "whatsapp_explicit", "paper", "import_documented", "revocation"]
    occurred_at: datetime
    evidence: str = Field(min_length=8, max_length=2000)

    @model_validator(mode="after")
    def explicit_evidence(self):
        self.evidence = self.evidence.strip()
        if len(self.evidence) < 8:
            raise ValueError("Informe a referência ou descrição da prova do consentimento/revogação.")
        if self.occurred_at.tzinfo is None or self.occurred_at > utcnow():
            raise ValueError("A data deve ter timezone e não pode estar no futuro.")
        if self.granted and self.source == "revocation":
            raise ValueError("Revogação não concede consentimento.")
        return self


class RuleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    content_sid: str | None = Field(None, pattern=r"^HX[0-9a-fA-F]{32}$")
    messaging_service_sid: str | None = Field(None, pattern=r"^MG[0-9a-fA-F]{32}$")


def actor_id(request):
    actor = getattr(request.state, "operator", {})
    if actor.get("id"):
        return str(actor["id"])
    if actor.get("service"):
        return "authenticated_service"
    raise HTTPException(403, "Operador autenticado obrigatório")


async def record_consent(rid, phone, change: ConsentChange, actor):
    """Append evidence and sync existing flag; contact row lock serializes claims."""
    async with db.pool().acquire() as c:
        async with c.transaction():
            contact = await c.fetchrow("SELECT id FROM contacts WHERE restaurant_id=$1 AND celular=$2 FOR UPDATE", rid, phone)
            if not contact:
                raise HTTPException(404, "Contato não encontrado nesta unidade")
            last = await c.fetchrow("SELECT occurred_at FROM outreach_consent_events WHERE restaurant_id=$1 AND customer_phone=$2 ORDER BY id DESC LIMIT 1", rid, phone)
            if change.granted and last and change.occurred_at < last["occurred_at"]:
                raise HTTPException(409, "Consentimento anterior à última alteração; registre uma nova autorização explícita.")
            row = await c.fetchrow("""
                INSERT INTO outreach_consent_events
                  (restaurant_id,customer_phone,granted,source,occurred_at,recorded_by,evidence)
                VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING *
            """, rid, phone, change.granted, change.source, change.occurred_at, actor, change.evidence)
            await c.execute("UPDATE contacts SET opt_in_marketing=$3 WHERE restaurant_id=$1 AND celular=$2", rid, phone, change.granted)
            return dict(row)


async def consent_history(rid, phone):
    async with db.pool().acquire() as c:
        contact = await c.fetchrow("SELECT opt_in_marketing FROM contacts WHERE restaurant_id=$1 AND celular=$2", rid, phone)
        if not contact:
            raise HTTPException(404, "Contato não encontrado nesta unidade")
        rows = await c.fetch("SELECT * FROM outreach_consent_events WHERE restaurant_id=$1 AND customer_phone=$2 ORDER BY id DESC LIMIT 50", rid, phone)
    history = [{**dict(row), "actor_id": row["recorded_by"]} for row in rows]
    current = history[0] if history else None
    return {"restaurant_id": rid, "phone": phone, "purpose": "whatsapp_followup",
            "eligible": bool(contact["opt_in_marketing"] and current and current["granted"]),
            "eligible_consent": bool(contact["opt_in_marketing"] and current and current["granted"]),
            "legacy_opt_in": contact["opt_in_marketing"], "current": current,
            "history": history}


def provider_credentials():
    sid, token = os.environ.get("TWILIO_ACCOUNT_SID", ""), os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not re.fullmatch(r"AC[0-9a-fA-F]{32}", sid) or not token:
        return None
    return sid, token


async def verify_template(content_sid):
    """Read-only live verification; never submit/create templates or messages."""
    credentials = provider_credentials()
    if not credentials or not content_sid:
        raise HTTPException(409, "Twilio ou template não configurado")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"https://content.twilio.com/v1/Content/{content_sid}/ApprovalRequests", auth=credentials)
        response.raise_for_status()
        status = response.json().get("whatsapp", {}).get("status")
    except (httpx.HTTPError, ValueError, AttributeError):
        raise HTTPException(503, "Não foi possível verificar a aprovação do template")
    if status != "approved":
        raise HTTPException(409, "Template não está aprovado no WhatsApp")
    return {"status": status, "verified_at": utcnow()}


async def rules_for(rid):
    async with db.pool().acquire() as c:
        if not await c.fetchval("SELECT EXISTS(SELECT 1 FROM restaurants WHERE id=$1)", rid):
            raise HTTPException(404, "Unidade não encontrada")
        rows = await c.fetch("SELECT * FROM outreach_rules WHERE restaurant_id=$1 ORDER BY stage", rid)
    existing = {row["stage"]: dict(row) for row in rows}
    return {"restaurant_id": rid, "sending_enabled": sending_enabled(), "default_dry_run": True,
            "rules": [existing.get(stage, {"restaurant_id": rid, "stage": stage, "enabled": False,
                       "content_sid": None, "template_status": "unverified",
                       "legacy_content_sid": LEGACY_TEMPLATES.get(stage)}) for stage in STAGES]}


async def save_rule(rid, stage, change: RuleChange, actor):
    if stage not in STAGES:
        raise HTTPException(422, "Etapa inválida")
    approval = await verify_template(change.content_sid) if change.enabled else {"status": "unverified", "verified_at": None}
    async with db.pool().acquire() as c:
        if not await c.fetchval("SELECT EXISTS(SELECT 1 FROM restaurants WHERE id=$1)", rid):
            raise HTTPException(404, "Unidade não encontrada")
        row = await c.fetchrow("""
            INSERT INTO outreach_rules(restaurant_id,stage,enabled,content_sid,messaging_service_sid,template_status,template_verified_at,updated_by)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT(restaurant_id,stage) DO UPDATE SET enabled=EXCLUDED.enabled,
              content_sid=EXCLUDED.content_sid,messaging_service_sid=EXCLUDED.messaging_service_sid,
              template_status=EXCLUDED.template_status,template_verified_at=EXCLUDED.template_verified_at,
              updated_by=EXCLUDED.updated_by,updated_at=NOW()
            RETURNING *
        """, rid, stage, change.enabled, change.content_sid, change.messaging_service_sid,
            approval["status"], approval["verified_at"], actor)
    return dict(row)


async def candidates(c, rid, family, now):
    """Only existing events, same-unit exact phone joins, stable event identity."""
    if family == "nurture":
        rows = await c.fetch("""
            SELECT ct.celular AS customer_phone,ct.nome,ct.opt_in_marketing,
                   last_message.id::text AS object_id,last_message.created_at AS event_at
            FROM contacts ct
            JOIN LATERAL (
              SELECT cv.id,cv.created_at FROM conversations cv
              WHERE cv.restaurant_id=ct.restaurant_id AND cv.user_phone=ct.celular AND cv.role='user'
              ORDER BY cv.created_at DESC,cv.id DESC LIMIT 1
            ) last_message ON true
            WHERE ct.restaurant_id=$1 AND ct.lead_score='morno'
              AND last_message.created_at >= $2::timestamptz - INTERVAL '90 days'
              AND last_message.created_at <= $2::timestamptz - INTERVAL '3 days'
              AND NOT EXISTS(SELECT 1 FROM reservas r WHERE r.restaurant_id=ct.restaurant_id
                AND r.cliente_phone=ct.celular AND r.status IN ('pendente','confirmada'))
            ORDER BY last_message.created_at,ct.celular LIMIT 100
        """, rid, now)
        return [{**dict(row), "object_type": "conversation", "stage": "nurture_d3",
                 "variables": {"1": (row["nome"] or "você").split()[0]}} for row in rows]
    if family != "pos_evento":
        raise HTTPException(422, "Família inválida")
    rows = await c.fetch("""
        SELECT os.id::text AS object_id,os.cliente_phone AS customer_phone,
          os.cliente_nome AS nome,os.tipo_evento AS titulo,os.evento_realizado_em AS event_at,
          os.regua_d1_enviado_em,os.regua_d3_enviado_em,os.regua_d7_enviado_em,os.regua_d30_enviado_em,
          ct.opt_in_marketing
        FROM ordens_servico os LEFT JOIN contacts ct
          ON ct.restaurant_id=os.restaurant_id AND ct.celular=os.cliente_phone
        WHERE os.restaurant_id=$1 AND os.status='realizado'
          AND os.evento_realizado_em >= $2::timestamptz - INTERVAL '32 days'
          AND os.evento_realizado_em <= $2::timestamptz - INTERVAL '20 hours'
        ORDER BY os.evento_realizado_em,os.id LIMIT 100
    """, rid, now)
    result = []
    for row in rows:
        hours = (now - row["event_at"]).total_seconds() / 3600
        for stage, (minimum, maximum, previous) in WINDOWS.items():
            if minimum <= hours <= maximum and not row[f"regua_{stage}_enviado_em"] and (not previous or row[f"regua_{previous}_enviado_em"]):
                result.append({**dict(row), "object_type": "ordem_servico", "stage": stage,
                               "variables": {"1": (row["nome"] or "você").split()[0], "2": row["titulo"] or "o evento"}})
    return result


async def evaluate(c, rid, candidate, sender):
    rule = await c.fetchrow("SELECT * FROM outreach_rules WHERE restaurant_id=$1 AND stage=$2", rid, candidate["stage"])
    consent = await c.fetchrow("SELECT id,granted FROM outreach_consent_events WHERE restaurant_id=$1 AND customer_phone=$2 ORDER BY id DESC LIMIT 1", rid, candidate["customer_phone"])
    attempt = await c.fetchrow("SELECT id,status,provider_message_sid FROM outreach_outbox WHERE restaurant_id=$1 AND object_type=$2 AND object_id=$3 AND stage=$4", rid, candidate["object_type"], candidate["object_id"], candidate["stage"])
    reasons = []
    if not sender or not PHONE.fullmatch(sender): reasons.append("sender_invalid_or_missing")
    if not candidate["customer_phone"] or not PHONE.fullmatch(candidate["customer_phone"]): reasons.append("recipient_invalid")
    if not candidate["opt_in_marketing"] or not consent or not consent["granted"]: reasons.append("explicit_consent_missing_or_revoked")
    if not rule or not rule["enabled"]: reasons.append("rule_disabled")
    if not rule or rule["template_status"] != "approved" or not rule["content_sid"]: reasons.append("template_unverified")
    if attempt: reasons.append("event_already_attempted")
    return {**candidate, "restaurant_id": rid, "sender_phone": sender,
            "eligible": not reasons, "blocked_reasons": reasons,
            "rule": dict(rule) if rule else None, "consent_event_id": consent["id"] if consent else None,
            "existing_attempt": dict(attempt) if attempt else None}


async def preview(rid, family):
    async with db.pool().acquire() as c:
        restaurant = await c.fetchrow("SELECT whatsapp_number,ativo FROM restaurants WHERE id=$1", rid)
        if not restaurant:
            raise HTTPException(404, "Unidade não encontrada")
        found = await candidates(c, rid, family, utcnow())
        items = [await evaluate(c, rid, item, restaurant["whatsapp_number"] if restaurant["ativo"] else None) for item in found]
    return {"restaurant_id": rid, "family": family, "dry_run": True,
            "sending_enabled": sending_enabled(), "total": len(items), "items": items,
            "sent": 0, "note": "Prévia não grava tentativas nem envia mensagens; SID confirma aceitação, não entrega."}


async def claim(rid, family, item):
    """Persist before network call. Existing event, including unknown, never retries."""
    async with db.pool().acquire() as c:
        async with c.transaction():
            await c.fetchrow("SELECT id FROM contacts WHERE restaurant_id=$1 AND celular=$2 FOR UPDATE", rid, item["customer_phone"])
            fresh = next((value for value in await candidates(c, rid, family, utcnow())
                          if value["object_id"] == item["object_id"] and value["stage"] == item["stage"]), None)
            if not fresh:
                return None
            restaurant = await c.fetchrow("SELECT whatsapp_number,ativo FROM restaurants WHERE id=$1", rid)
            checked = await evaluate(c, rid, fresh, restaurant["whatsapp_number"] if restaurant and restaurant["ativo"] else None)
            if not checked["eligible"] or checked["rule"]["updated_at"] != item["rule"]["updated_at"] or not sending_enabled():
                return None
            payload = {"variables": checked["variables"], "event_at": checked["event_at"].isoformat(),
                       "messaging_service_sid": checked["rule"]["messaging_service_sid"],
                       "template_verified_at": utcnow().isoformat()}
            row = await c.fetchrow("""
                INSERT INTO outreach_outbox(restaurant_id,object_type,object_id,stage,customer_phone,sender_phone,
                  content_sid,consent_event_id,payload,status)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,'dispatching')
                ON CONFLICT(restaurant_id,object_type,object_id,stage) DO NOTHING RETURNING *
            """, rid, checked["object_type"], checked["object_id"], checked["stage"], checked["customer_phone"],
                checked["sender_phone"], checked["rule"]["content_sid"], checked["consent_event_id"], json.dumps(payload))
    return dict(row) if row else None


async def send_template(attempt):
    """Exactly one HTTP request, no library retry policy and no free-form fallback."""
    credentials = provider_credentials()
    if not credentials:
        return {"status": "failed", "error_code": "provider_unavailable"}
    payload = json.loads(attempt["payload"]) if isinstance(attempt["payload"], str) else attempt["payload"]
    data = {"From": "whatsapp:" + attempt["sender_phone"], "To": "whatsapp:" + attempt["customer_phone"],
            "ContentSid": attempt["content_sid"], "ContentVariables": json.dumps(payload["variables"])}
    if payload.get("messaging_service_sid"):
        data["MessagingServiceSid"] = payload["messaging_service_sid"]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(f"https://api.twilio.com/2010-04-01/Accounts/{credentials[0]}/Messages.json", auth=credentials, data=data)
        if response.status_code >= 500:
            return {"status": "unknown", "error_code": "provider_5xx"}
        if not 200 <= response.status_code < 300:
            return {"status": "failed", "error_code": "provider_http_" + str(response.status_code)}
        result = response.json()
        sid = result.get("sid")
        if not isinstance(sid, str) or not MESSAGE_SID.fullmatch(sid):
            return {"status": "unknown", "error_code": "missing_valid_message_sid"}
        state = "failed" if result.get("status") in ("failed", "undelivered", "canceled") else "sent"
        return {"status": state, "provider_message_sid": sid, "provider_status": result.get("status")}
    except (httpx.HTTPError, ValueError, AttributeError):
        return {"status": "unknown", "error_code": "ambiguous_transport_or_response"}


async def finish(attempt, outcome):
    async with db.pool().acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("""
                UPDATE outreach_outbox SET status=$3,provider_message_sid=$4,provider_status=$5,error_code=$6,finished_at=NOW()
                WHERE id=$1 AND restaurant_id=$2 AND status='dispatching' RETURNING id
            """, attempt["id"], attempt["restaurant_id"], outcome["status"], outcome.get("provider_message_sid"), outcome.get("provider_status"), outcome.get("error_code"))
            if row and outcome["status"] == "sent" and attempt["object_type"] == "ordem_servico" and attempt["stage"] in WINDOWS:
                column = "regua_" + attempt["stage"] + "_enviado_em"
                await c.execute(f"UPDATE ordens_servico SET {column}=COALESCE({column},NOW()) WHERE restaurant_id=$1 AND id::text=$2", attempt["restaurant_id"], attempt["object_id"])


async def run(rid, family, dry_run=True):
    report = await preview(rid, family)
    if dry_run or not sending_enabled():
        if not dry_run:
            report["note"] = "Envio desativado globalmente; retornada apenas prévia."
        return report
    report["dry_run"] = False
    report["results"] = []
    for item in report["items"]:
        if not item["eligible"]:
            continue
        if not provider_credentials():
            report["results"].append({"object_id": item["object_id"], "status": "blocked", "reason": "provider_unavailable"})
            continue
        try:
            await verify_template(item["rule"]["content_sid"])
        except HTTPException:
            report["results"].append({"object_id": item["object_id"], "status": "blocked", "reason": "template_not_verified_live"})
            continue
        attempt = await claim(rid, family, item)
        if not attempt:
            continue
        outcome = await send_template(attempt)
        await finish(attempt, outcome)
        report["results"].append({"outbox_id": attempt["id"], **outcome})
        report["sent"] += outcome["status"] == "sent"
    return report


def create_router(auth_dependency):
    router = APIRouter(dependencies=[Depends(auth_dependency)])

    @router.get("/api/restaurants/{restaurant_id}/contacts/{phone}/outreach-consent")
    async def read_consent(restaurant_id: str, phone: str):
        return await consent_history(restaurant_id, phone)

    @router.put("/api/restaurants/{restaurant_id}/contacts/{phone}/outreach-consent")
    async def write_consent(restaurant_id: str, phone: str, change: ConsentChange, request: Request):
        return await record_consent(restaurant_id, phone, change, actor_id(request))

    @router.get("/api/restaurants/{restaurant_id}/outreach/config")
    async def read_rules(restaurant_id: str):
        return await rules_for(restaurant_id)

    @router.put("/api/restaurants/{restaurant_id}/outreach/config/{stage}")
    async def write_rule(restaurant_id: str, stage: str, change: RuleChange, request: Request):
        return await save_rule(restaurant_id, stage, change, actor_id(request))

    @router.post("/api/restaurants/{restaurant_id}/outreach/{family}/run")
    async def run_rule(restaurant_id: str, family: Literal["nurture", "pos_evento"], dry_run: bool = Query(True)):
        return await run(restaurant_id, family, dry_run)

    @router.get("/api/restaurants/{restaurant_id}/outreach/outbox")
    async def read_outbox(restaurant_id: str, limit: int = Query(100, ge=1, le=500)):
        async with db.pool().acquire() as c:
            rows = await c.fetch("SELECT id,restaurant_id,object_type,object_id,stage,status,provider_message_sid,provider_status,error_code,created_at,finished_at FROM outreach_outbox WHERE restaurant_id=$1 ORDER BY id DESC LIMIT $2", restaurant_id, limit)
        return [dict(row) for row in rows]
    return router
