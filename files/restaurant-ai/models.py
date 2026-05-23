"""Modelos Pydantic — contratos da API REST."""

from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


# ── Restaurantes ──────────────────────────────────────────────
class RestaurantCreate(BaseModel):
    id: str
    nome: str
    whatsapp_number: str
    endereco: str = ""
    descricao: str = ""
    capacidade_maxima_reserva: int = 8
    antecedencia_minima_horas: int = 2
    capacidade_total: int = 80

class RestaurantUpdate(BaseModel):
    nome: Optional[str] = None
    endereco: Optional[str] = None
    descricao: Optional[str] = None
    capacidade_maxima_reserva: Optional[int] = None
    antecedencia_minima_horas: Optional[int] = None
    capacidade_total: Optional[int] = None
    ativo: Optional[bool] = None

class BusinessHourItem(BaseModel):
    dia: str
    horario: str
    fechado: bool = False


# ── Cardápio ──────────────────────────────────────────────────
class MenuItemCreate(BaseModel):
    categoria: str
    nome: str
    descricao: str = ""
    preco: Optional[float] = None
    disponivel: bool = True
    ordem: int = 0

class MenuItemUpdate(BaseModel):
    categoria: Optional[str] = None
    nome: Optional[str] = None
    descricao: Optional[str] = None
    preco: Optional[float] = None
    disponivel: Optional[bool] = None
    ordem: Optional[int] = None


# ── FAQ ───────────────────────────────────────────────────────
class FaqItemCreate(BaseModel):
    chave: str
    resposta: str
    ordem: int = 0

class FaqItemUpdate(BaseModel):
    chave: Optional[str] = None
    resposta: Optional[str] = None
    ordem: Optional[int] = None


# ── Reservas ──────────────────────────────────────────────────
class ReservationUpdate(BaseModel):
    status: Optional[str] = None
    observacoes: Optional[str] = None
    nome: Optional[str] = None
    hora: Optional[str] = None
    pessoas: Optional[int] = None

    @field_validator("pessoas")
    @classmethod
    def pessoas_positivo(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Número de pessoas deve ser maior que zero")
        return v


# ── Handoff ───────────────────────────────────────────────────
class HandoffReply(BaseModel):
    mensagem: str
    atendente_nome: str

class HandoffResolve(BaseModel):
    atendente_nome: str


# ── Equipe ────────────────────────────────────────────────────
class TeamMemberCreate(BaseModel):
    nome: str
    whatsapp: str
    role: str = "atendente"


# ── CRM / Contatos ────────────────────────────────────────────
class ContactUpsert(BaseModel):
    celular: str
    nome: Optional[str] = None
    sobrenome: Optional[str] = None
    email: Optional[str] = None

    @field_validator("email", mode="before")
    @classmethod
    def email_basico(cls, v):
        if v and "@" not in str(v):
            raise ValueError("Email inválido")
        return v
    data_nascimento: Optional[str] = None  # ISO date YYYY-MM-DD
    endereco: Optional[str] = None
    tipo_aparelho: Optional[str] = None
    canal_entrada: Optional[str] = None
    ocasiao: Optional[list[str]] = None
    restricoes_alimentares: Optional[list[str]] = None
    ticket_medio: Optional[float] = None
    ultima_visita: Optional[str] = None
    tags: Optional[list[str]] = None
    opt_in_marketing: Optional[bool] = None
    estagio_kanban: Optional[str] = None
    notas: Optional[str] = None
    frequencia_visitas: Optional[int] = None

class ContactUpdate(BaseModel):
    nome: Optional[str] = None
    sobrenome: Optional[str] = None
    email: Optional[str] = None

    @field_validator("email", mode="before")
    @classmethod
    def email_basico(cls, v):
        if v and "@" not in str(v):
            raise ValueError("Email inválido")
        return v
    data_nascimento: Optional[str] = None
    endereco: Optional[str] = None
    tipo_aparelho: Optional[str] = None
    canal_entrada: Optional[str] = None
    ocasiao: Optional[list[str]] = None
    restricoes_alimentares: Optional[list[str]] = None
    ticket_medio: Optional[float] = None
    ultima_visita: Optional[str] = None
    tags: Optional[list[str]] = None
    opt_in_marketing: Optional[bool] = None
    estagio_kanban: Optional[str] = None
    notas: Optional[str] = None
    frequencia_visitas: Optional[int] = None

class ContactKanbanMove(BaseModel):
    estagio_kanban: str
