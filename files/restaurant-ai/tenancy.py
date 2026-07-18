"""
Infra de multi-tenancy — Sprint White-Label, Fase C.

C1  (este arquivo): flag inerte + helpers pass-through.
     Comportamento idêntico ao de hoje em QUALQUER valor da flag.
C2  (próximo pacote): substituir os corpos pass-through pela lógica real
     (consulta usuario_restaurante + validação de x-operator-id).

Rollback emergencial: setar MULTI_TENANT_ENABLED=false no Railway (~30s).
"""

import logging
import os

logger = logging.getLogger("tenancy")

# Lido uma vez no import — imutável em runtime.
# Valor padrão "false" → Railway prod parte sempre desligado.
MULTI_TENANT_ENABLED: bool = (
    os.environ.get("MULTI_TENANT_ENABLED", "false").lower() == "true"
)


async def get_casas_permitidas(operator_id: str) -> list[str]:
    """Retorna os restaurant_ids que o operador tem acesso.

    C1 — pass-through: retorna [] (sem restrição).
    C2 — consultar usuario_restaurante WHERE usuario_id = operator_id.
    """
    # C2: return await db.get_casas_do_operador(operator_id)
    return []


async def check_tenancy(rid: str, operator_id: str) -> bool:
    """Verifica se operator_id tem acesso ao restaurante rid.

    Retorna True em AMBOS os estados da flag (C1 é inerte).
    Quando flag=True, emite log estruturado para provar que a fiação está viva.
    C2 — substituir o corpo pelo check real em usuario_restaurante.
    """
    if not MULTI_TENANT_ENABLED:
        return True

    # Flag ligada: fiação viva, mas ainda sem restrição (C2 pendente).
    logger.info(
        "tenancy_check rid=%s operator=%s result=allowed note=C2_pending",
        rid,
        operator_id,
    )
    # C2: casas = await get_casas_permitidas(operator_id)
    #     if rid not in casas: raise HTTPException(403, "Acesso negado a este restaurante")
    return True
