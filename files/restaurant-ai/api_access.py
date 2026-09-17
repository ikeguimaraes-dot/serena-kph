"""Server-side panel authorization; public integrations have explicit exceptions.

The Next proxy validates Supabase sessions and supplies x-operator-id together
with the server-only ADMIN_SECRET. A secret-only caller is a trusted service.
Operator roles/scopes always come from the server-owned operadores record.
"""
import os
import re
import secrets
from uuid import UUID

from fastapi import HTTPException, Request
import database as db


PUBLIC_ROUTES = {
    ("GET", "/api/agenda/{restaurant_id}/disponibilidade"),
    ("POST", "/api/widget/reserva/{restaurant_id}"),
}


def staff_route_allowed(method: str, path: str) -> bool:
    if path == "/api/restaurants":
        return method == "GET"
    if re.fullmatch(r"/api/restaurants/[^/]+", path):
        return method == "GET"
    if re.fullmatch(r"/api/restaurants/[^/]+/(menu|ambientes|experiencias|eventos|faq|team|conversations|handoff|handoff/sla-stats)", path):
        return method == "GET"
    if path.startswith("/api/contacts"):
        return path != "/api/contacts/mark-inactive"
    return any(path.startswith(prefix) for prefix in
               ("/api/agenda/", "/api/handoff/", "/api/conversations/", "/api/os/", "/api/reservations/"))


async def operator_profile(operator_id: str) -> dict | None:
    try:
        UUID(operator_id)
    except ValueError:
        raise HTTPException(403, "Operador inválido")
    async with db.pool().acquire() as connection:
        row = await connection.fetchrow(
            "SELECT id, role, restaurante_id FROM operadores WHERE id=$1::uuid", operator_id)
    return dict(row) if row else None


async def resource_tenant(table: str, resource_id: str) -> str | None:
    # table is selected exclusively from the fixed mapping below, never user input.
    async with db.pool().acquire() as connection:
        return await connection.fetchval(
            f"SELECT restaurant_id FROM {table} WHERE id::text=$1", str(resource_id))


async def authorize_api_request(request: Request):
    path = request.url.path
    if not path.startswith("/api/"):
        return  # health and webhooks retain their own authentication contracts.
    route = request.scope.get("route")
    template = getattr(route, "path", "")
    if (request.method, template) in PUBLIC_ROUTES:
        return

    secret = os.environ.get("ADMIN_SECRET")
    if not secret:
        raise HTTPException(503, "Autenticação indisponível")
    supplied = request.headers.get("x-admin-secret", "")
    if not supplied or not secrets.compare_digest(supplied, secret):
        raise HTTPException(401, "Autenticação obrigatória")

    operator_id = request.headers.get("x-operator-id")
    actor = {"role": "admin", "restaurante_id": None, "service": True}
    if operator_id:
        try:
            actor = await operator_profile(operator_id)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "Autenticação indisponível")
        if not actor or actor.get("role") not in {"admin", "atendente"}:
            raise HTTPException(403, "Operador sem acesso ao painel")
    request.state.operator = actor
    if actor["role"] != "admin" and not staff_route_allowed(request.method, path):
        raise HTTPException(403, "Ação restrita a administradores")

    params = request.path_params
    tenant = params.get("rid") or params.get("restaurant_id")
    requested = [tenant] if tenant else []
    requested += request.query_params.getlist("rid") + request.query_params.getlist("restaurant_id")
    if len(set(requested)) > 1:
        raise HTTPException(403, "Unidade divergente")
    tenant = next(iter(requested), None)
    if path.startswith("/api/contacts"):
        tenant = tenant or request.headers.get("x-restaurant-id")
    body = {}
    if request.method not in {"GET", "HEAD"}:
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            body = {}
        body_tenant = body.get("restaurant_id") if isinstance(body, dict) else None
        if tenant and body_tenant and tenant != body_tenant:
            raise HTTPException(403, "Unidade divergente")
        tenant = tenant or body_tenant

    resources = {"hid": "handoff_sessions", "res_id": "reservas",
                 "reserva_id": "reservas", "os_id": "ordens_servico",
                 "amb_id": "restaurant_ambientes", "exp_id": "experiencias",
                 "evento_id": "agenda_eventos"}
    if path.startswith("/api/menu/"):
        resources["item_id"] = "menu_items"
    elif path.startswith("/api/faq/"):
        resources["item_id"] = "faq_items"
    for parameter, table in resources.items():
        if parameter in params:
            owner = await resource_tenant(table, params[parameter])
            if not owner or (tenant and tenant != owner):
                raise HTTPException(404, "Registro não encontrado nesta unidade")
            tenant = owner

    if path.startswith("/api/agenda/") and isinstance(body, dict):
        for field, table in (("turno_id", "agenda_turnos"), ("evento_id", "agenda_eventos")):
            if body.get(field):
                owner = await resource_tenant(table, body[field])
                if not owner or owner != tenant:
                    raise HTTPException(404, "Agenda não encontrada nesta unidade")

    if path.startswith("/api/os/") and params.get("item_id"):
        async with db.pool().acquire() as connection:
            parent = await connection.fetchval(
                "SELECT os_id::text FROM checklist_instancias WHERE id::text=$1", str(params["item_id"]))
        if parent != str(params.get("os_id")):
            raise HTTPException(404, "Item não encontrado nesta ordem")

    scope = actor.get("restaurante_id")
    if scope and not staff_route_allowed(request.method, path):
        # An arbitrary ?rid must not make a groupwide aggregate look scoped.
        # Unit-specific admin configuration has its own path/resource owner.
        has_owner = bool(params.get("rid") or params.get("restaurant_id") or
                         any(name in params for name in resources))
        if not has_owner:
            raise HTTPException(403, "Ação exige acesso ao grupo")
    if scope and tenant and tenant != scope:
        raise HTTPException(403, "Acesso negado a esta unidade")
    # NULL scope is the existing, explicitly server-assigned groupwide contract.
    # A scoped operator cannot use unscoped aggregate/admin routes.
    if scope and not tenant and path != "/api/restaurants":
        if path.startswith("/api/contacts"):
            tenant = scope
        else:
            raise HTTPException(403, "Unidade obrigatória para este operador")
    request.state.restaurant_id = tenant


def contact_tenant(request: Request) -> str:
    """A phone can have several CRM profiles; never choose or mutate one implicitly."""
    tenant = getattr(request.state, "restaurant_id", None)
    if not tenant:
        raise HTTPException(422, "Informe rid para selecionar a unidade do contato")
    return tenant
