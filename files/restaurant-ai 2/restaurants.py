# ============================================================
# CONFIGURAÇÃO DAS UNIDADES — edite aqui para cada restaurante
# Chave = número WhatsApp Business da unidade (formato +55...)
# ============================================================

RESTAURANTS = {
    "+5511900000001": {
        "id": "unidade_jardins",
        "nome": "Restaurante X — Jardins",
        "endereco": "Rua Oscar Freire, 123 — Jardins, São Paulo",
        "horarios": {
            "Seg–Qui": "12h às 23h",
            "Sex–Sáb": "12h às 00h",
            "Domingo": "12h às 22h",
        },
        "capacidade_maxima_reserva_whatsapp": 8,
        "antecedencia_minima_horas": 2,
        "cardapio_resumo": (
            "Especialidades: carnes nobres e frutos do mar. "
            "Pratos principais: R$ 65–180. "
            "Menu degustação: R$ 220–380 por pessoa. "
            "Carta de vinhos com mais de 200 rótulos."
        ),
        "faq": {
            "pagamento": "Aceitamos todos os cartões, Pix e dinheiro. Sem cheques.",
            "estacionamento": "Valet disponível Ter–Dom a partir das 18h. Custo: R$ 35.",
            "dress_code": "Não obrigatório. Preferimos traje passeio.",
            "criancas": "Bem-vindas. Cardápio kids disponível.",
            "alergias": "Informe ao reservar. Adaptamos pratos conforme necessidade.",
            "pets": "Animais não permitidos no interior. Área externa pet-friendly.",
            "cancelamento": "Cancelamentos com menos de 2h geram taxa de R$ 50 por pessoa.",
        },
    },
    "+5511900000002": {
        "id": "unidade_itaim",
        "nome": "Restaurante X — Itaim Bibi",
        "endereco": "Rua Pedroso Alvarenga, 456 — Itaim Bibi, São Paulo",
        "horarios": {
            "Seg–Qui": "12h às 23h",
            "Sex–Sáb": "12h às 00h",
            "Domingo": "Fechado",
        },
        "capacidade_maxima_reserva_whatsapp": 8,
        "antecedencia_minima_horas": 2,
        "cardapio_resumo": (
            "Especialidades: cozinha italiana contemporânea e frutos do mar. "
            "Pratos principais: R$ 55–160. "
            "Carta de vinhos com mais de 150 rótulos."
        ),
        "faq": {
            "pagamento": "Aceitamos todos os cartões, Pix e dinheiro.",
            "estacionamento": "Estacionamento rotativo na rua. Valet não disponível.",
            "dress_code": "Sem dress code.",
            "criancas": "Bem-vindas até as 20h.",
            "alergias": "Informe ao reservar. Adaptamos quando possível.",
            "pets": "Animais não permitidos.",
            "cancelamento": "Cancelamentos até 3h antes sem custo.",
        },
    },
    # Adicione novas unidades seguindo o mesmo padrão acima
}


def get_restaurant_by_phone(phone: str) -> dict | None:
    """Retorna configuração do restaurante pelo número WhatsApp"""
    normalized = phone.replace("whatsapp:", "").strip()
    return RESTAURANTS.get(normalized)


def get_restaurant_by_id(restaurant_id: str) -> dict | None:
    """Retorna configuração do restaurante pelo ID"""
    for r in RESTAURANTS.values():
        if r["id"] == restaurant_id:
            return r
    return None
