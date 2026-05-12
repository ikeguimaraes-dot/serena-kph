# ─── main.py — adicionar após os routers existentes ──────────────────────────
# Importe os models novos no topo do main.py:
#   from models import (ContactCreate, ContactUpdate, ContactKanbanMove,
#                       ContactOut, ContactListResponse, ContactStatsOut)

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

router_contacts = APIRouter(prefix="/contacts", tags=["contacts"])


# ── GET /contacts ──────────────────────────────────────────────────────────────
@router_contacts.get("", response_model=ContactListResponse)
async def list_contacts(
    page: int       = Query(1, ge=1),
    page_size: int  = Query(20, ge=1, le=100),
    tier: Optional[str]            = Query(None),
    estagio_kanban: Optional[str]  = Query(None),
    search: Optional[str]          = Query(None),
):
    """Lista contatos com filtros e paginação."""
    if search:
        rows = await db.search_contacts(search)
    else:
        rows = await db.list_contacts(
            tier=tier,
            estagio_kanban=estagio_kanban,
            page=page,
            page_size=page_size,
        )
    return {
        "contacts": rows["data"],
        "total":    rows["total"],
        "page":     page,
        "page_size": page_size,
    }


# ── POST /contacts ─────────────────────────────────────────────────────────────
@router_contacts.post("", response_model=ContactOut, status_code=201)
async def create_contact(body: ContactCreate):
    """Cria um novo contato manualmente."""
    contact = await db.upsert_contact(body.dict())
    if not contact:
        raise HTTPException(status_code=400, detail="Erro ao criar contato")
    return contact


# ── GET /contacts/stats ────────────────────────────────────────────────────────
@router_contacts.get("/stats", response_model=ContactStatsOut)
async def contact_stats():
    """Retorna resumo de contatos por tier e estágio."""
    return await db.contact_stats()


# ── GET /contacts/{contact_id} ─────────────────────────────────────────────────
@router_contacts.get("/{contact_id}", response_model=ContactOut)
async def get_contact(contact_id: int):
    contact = await db.get_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato não encontrado")
    return contact


# ── PATCH /contacts/{contact_id} ───────────────────────────────────────────────
@router_contacts.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(contact_id: int, body: ContactUpdate):
    """Atualiza campos parciais de um contato."""
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    updated = await db.update_contact(contact_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Contato não encontrado")
    return updated


# ── PATCH /contacts/{contact_id}/kanban ────────────────────────────────────────
@router_contacts.patch("/{contact_id}/kanban", response_model=ContactOut)
async def move_kanban(contact_id: int, body: ContactKanbanMove):
    """Move contato para outro estágio do kanban."""
    updated = await db.move_contact_kanban(contact_id, body.estagio_kanban)
    if not updated:
        raise HTTPException(status_code=404, detail="Contato não encontrado")
    return updated


# ── GET /contacts/{contact_id}/reservations ────────────────────────────────────
@router_contacts.get("/{contact_id}/reservations")
async def contact_reservations(contact_id: int):
    rows = await db.get_contact_reservations(contact_id)
    return {"reservations": rows}


# ── GET /contacts/{contact_id}/conversations ───────────────────────────────────
@router_contacts.get("/{contact_id}/conversations")
async def contact_conversations(contact_id: int):
    rows = await db.get_contact_conversations(contact_id)
    return {"conversations": rows}


# ── POST /contacts/mark-inactive ──────────────────────────────────────────────
@router_contacts.post("/mark-inactive")
async def mark_inactive(days: int = Query(45, ge=1)):
    """Marca como inativo contatos sem visita há N dias."""
    count = await db.mark_inactive_contacts(days)
    return {"marked_inactive": count}


# ── Registrar no app principal ────────────────────────────────────────────────
# No main.py, adicione:
#   app.include_router(router_contacts)
