"""Modelos Pydantic — contratos da API REST."""

from pydantic import BaseModel, Field, field_validator, model_validator
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
    # Sprint 12 — config de concierge/loja (aba Minha Casa)
    nome_agente: Optional[str] = None
    personalidade: Optional[str] = None
    tom_voz: Optional[str] = None
    idioma: Optional[str] = None
    telefone: Optional[str] = None
    site: Optional[str] = None
    horario_atendimento: Optional[str] = None
    donts: Optional[list[str]] = None

class BusinessHourItem(BaseModel):
    dia: str
    horario: str
    fechado: bool = False


# ── Cardápio ──────────────────────────────────────────────────
class MenuItemCreate(BaseModel):
    categoria: str
    nome: str
    descricao: str = ""
    preco: Optional[float] = Field(None, ge=0, allow_inf_nan=False)
    disponivel: bool = True
    ordem: int = 0

class MenuItemUpdate(BaseModel):
    categoria: Optional[str] = None
    nome: Optional[str] = None
    descricao: Optional[str] = None
    preco: Optional[float] = Field(None, ge=0, allow_inf_nan=False)
    disponivel: Optional[bool] = None
    ordem: Optional[int] = None


# ── Ambientes (Sprint 12 — Minha Casa) ───────────────────────
class AmbienteCreate(BaseModel):
    nome: str
    capacidade: Optional[int] = None
    num_mesas: Optional[int] = None
    pessoas_por_mesa: Optional[int] = None
    ativo: bool = True
    horario_proprio: Optional[dict] = None
    imagem_url: Optional[str] = None
    ordem: int = 0

class AmbienteUpdate(BaseModel):
    nome: Optional[str] = None
    capacidade: Optional[int] = None
    num_mesas: Optional[int] = None
    pessoas_por_mesa: Optional[int] = None
    ativo: Optional[bool] = None
    horario_proprio: Optional[dict] = None
    imagem_url: Optional[str] = None
    ordem: Optional[int] = None


# ── Experiências (Sprint 12 — Minha Casa) ────────────────────
class ExperienciaCreate(BaseModel):
    nome: str
    descricao: str = ""
    datas: str = ""
    valores: str = ""
    link: str = ""
    ativo: bool = True
    ordem: int = 0

class ExperienciaUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    datas: Optional[str] = None
    valores: Optional[str] = None
    link: Optional[str] = None
    ativo: Optional[bool] = None
    ordem: Optional[int] = None


# ── Eventos ───────────────────────────────────────────────────
class EventoCreate(BaseModel):
    nome: str
    data: str                            # "YYYY-MM-DD"
    descricao: Optional[str] = None
    capacidade_total: Optional[int] = None
    hora_inicio: Optional[str] = None    # "HH:MM"
    hora_fim: Optional[str] = None
    hora_evento: Optional[str] = None
    dia_semana_label: Optional[str] = None
    enquadramento: Optional[str] = None
    adversario: Optional[str] = None
    requer_pagamento: bool = True
    # ativo NÃO exposto — sempre FALSE no POST; publicar é ação separada

class EventoUpdate(BaseModel):
    nome: Optional[str] = None
    data: Optional[str] = None
    descricao: Optional[str] = None
    capacidade_total: Optional[int] = None
    hora_inicio: Optional[str] = None
    hora_fim: Optional[str] = None
    hora_evento: Optional[str] = None
    dia_semana_label: Optional[str] = None
    enquadramento: Optional[str] = None
    adversario: Optional[str] = None
    requer_pagamento: Optional[bool] = None

class EventoExperienciasSet(BaseModel):
    experiencia_ids: list[str] = []


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
class ContactStageFields(BaseModel):
    estagio_kanban: Optional[str] = None
    motivo_perda: Optional[str] = None
    motivo_perda_detalhe: Optional[str] = None

    @model_validator(mode="after")
    def validate_stage(self):
        from crm_stages import validate_stage_payload
        reason, detail = validate_stage_payload(
            self.estagio_kanban, self.motivo_perda, self.motivo_perda_detalhe)
        # PATCH must distinguish an omitted field from an explicit null.
        supplied = self.model_fields_set.copy()
        if "motivo_perda" in supplied:
            self.motivo_perda = reason
        if "motivo_perda_detalhe" in supplied:
            self.motivo_perda_detalhe = detail
        return self


class ContactUpsert(ContactStageFields):
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
    notas: Optional[str] = None
    frequencia_visitas: Optional[int] = None

class ContactUpdate(ContactStageFields):
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
    notas: Optional[str] = None
    frequencia_visitas: Optional[int] = None

class ContactKanbanMove(ContactStageFields):
    estagio_kanban: str
