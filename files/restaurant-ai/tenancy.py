"""
Infra de multi-tenancy — Sprint White-Label, Fase C.

C1  (entregue): flag inerte + helpers pass-through.
C2  (este arquivo): lógica real — consulta usuario_restaurante + 403 quando negado.

Rollback emergencial: setar MULTI_TENANT_ENABLED=false no Railway (~30s).
"""

import logging
import os

from fastapi import HTTPException

import database as db  # import direto — database.py NÃO importa tenancy (sem circular)

logger = logging.getLogger("tenancy")

# Lido uma vez no import — imutável em runtime.
# Valor padrão "false" → Railway prod parte sempre desligado.
MULTI_TENANT_ENABLED: bool = (
    os.environ.get("MULTI_TENANT_ENABLED", "false").lower() == "true"
)


async def get_casas_permitidas(operator_id: str) -> list[str]:
    """Retorna os restaurant_ids que o operador tem acesso.

    C2 — consulta usuario_restaurante WHERE usuario_id = operator_id.
    """
    return await db.get_casas_do_operador(operator_id)


async def check_tenancy(rid: str, operator_id: str) -> bool:
    """Verifica se operator_id tem acesso ao restaurante rid.

    flag=false → sempre True (comportamento atual, sem custo de DB).
    flag=true  → consulta usuario_restaurante; 403 se rid não autorizado.
    """
    if not MULTI_TENANT_ENABLED:
        return True

    casas = await get_casas_permitidas(operator_id)
    logger.info(
        "tenancy_check rid=%s operator=%s casas=%s result=%s",
        rid,
        operator_id,
        casas,
        "allowed" if rid in casas else "denied",
    )
    if rid not in casas:
        raise HTTPException(403, "Acesso negado a este restaurante")
    return True
