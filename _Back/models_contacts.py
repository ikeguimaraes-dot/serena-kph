# ─── models.py — adicionar ao arquivo existente ───────────────────────────────
# Cole abaixo dos modelos já existentes

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ── Enums ──────────────────────────────────────────────────────────────────────

class ContactTier(str, Enum):
    vip     = "vip"
    regular = "regular"
    new     = "new"
    inactive = "inactive"

class KanbanEstagio(str, Enum):
    lead          = "lead"
    primeiro_contato = "primeiro_contato"
    ativo         = "ativo"
    fidelizado    = "fidelizado"
    inativo       = "inativo"

class ContactOrigem(str, Enum):
    reserva     = "reserva"
    whatsapp    = "whatsapp"
    indicacao   = "indicacao"
    walk_in     = "walk_in"
    evento      = "evento"
    manual      = "manual"


# ── Request / Response bodies ──────────────────────────────────────────────────

class ContactCreate(BaseModel):
    nome: str                           = Field(..., min_length=2, max_length=200)
    telefone: str                       = Field(..., min_length=8, max_length=20)
    email: Optional[str]                = None
    data_nascimento: Optional[str]      = None   # ISO date string "YYYY-MM-DD"
    preferencias: Optional[str]         = None
    restricoes_alimentares: Optional[str] = None
    origem: Optional[ContactOrigem]     = ContactOrigem.manual
    notas_internas: Optional[str]       = None
    estagio_kanban: Optional[KanbanEstagio] = KanbanEstagio.lead


class ContactUpdate(BaseModel):
    nome: Optional[str]                 = Field(None, min_length=2, max_length=200)
    telefone: Optional[str]             = Field(None, min_length=8, max_length=20)
    email: Optional[str]                = None
    data_nascimento: Optional[str]      = None
    preferencias: Optional[str]         = None
    restricoes_alimentares: Optional[str] = None
    notas_internas: Optional[str]       = None
    tier: Optional[ContactTier]         = None
    estagio_kanban: Optional[KanbanEstagio] = None


class ContactKanbanMove(BaseModel):
    estagio_kanban: KanbanEstagio


class ContactOut(BaseModel):
    id: int
    nome: str
    telefone: str
    email: Optional[str]
    data_nascimento: Optional[str]
    preferencias: Optional[str]
    restricoes_alimentares: Optional[str]
    origem: Optional[str]
    notas_internas: Optional[str]
    tier: ContactTier
    estagio_kanban: KanbanEstagio
    total_reservas: int
    ultima_visita: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContactListResponse(BaseModel):
    contacts: List[ContactOut]
    total: int
    page: int
    page_size: int


class ContactStatsOut(BaseModel):
    total: int
    vip: int
    regular: int
    new: int
    inactive: int
    por_estagio: dict
    aniversariantes_mes: int
