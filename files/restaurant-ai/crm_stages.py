"""One API contract for intentional CRM transitions; no inferred losses."""
KANBAN_ESTAGIOS = ("captacao", "qualificado", "proposta", "fechado", "perdido")
MOTIVOS_PERDA = ("preco", "indisponibilidade", "sem_retorno", "desistiu", "outro")


def validate_stage_payload(estagio=None, motivo_perda=None, motivo_perda_detalhe=None):
    reason = motivo_perda.strip() if isinstance(motivo_perda, str) else motivo_perda
    detail = motivo_perda_detalhe.strip() if isinstance(motivo_perda_detalhe, str) else motivo_perda_detalhe
    reason, detail = reason or None, detail or None
    if estagio is not None and estagio not in KANBAN_ESTAGIOS:
        raise ValueError("Estágio inválido")
    if reason is not None and reason not in MOTIVOS_PERDA:
        raise ValueError("Motivo de perda inválido")
    if detail is not None and (not isinstance(detail, str) or len(detail) > 1000):
        raise ValueError("Detalhe do motivo deve ter no máximo 1000 caracteres")
    if estagio == "perdido":
        if reason is None:
            raise ValueError("Classificação de perda exige motivo informado")
        if reason == "outro" and detail is None:
            raise ValueError("Informe o detalhe para o motivo outro")
    elif reason is not None or detail is not None:
        raise ValueError("Motivo de perda só pode ser informado com estágio perdido")
    return reason, detail
