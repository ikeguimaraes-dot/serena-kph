"""Anonymous reservation API: public facts only, no CRM/read-by-phone surface."""
import time
from uuid import UUID
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt
import database as db
from reservation_service import availability, BookingError

router = APIRouter()
_hits = TTLCache(maxsize=10000, ttl=60)


class PublicBooking(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=40)
    date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    people: StrictInt = Field(ge=1, le=1000)
    slot_id: UUID
    idempotency_key: UUID


def throttle(request):
    # Per-worker/IP coarse shield; successful writes also have a shared DB/phone limit.
    # Ignore client-controlled forwarded headers. A shared reverse proxy gets a
    # larger aggregate allowance; stronger edge/WAF limits can be applied later.
    key = (request.client.host if request.client else 'unknown', request.method, int(time.time() // 60))
    count = _hits.get(key, 0) + 1
    _hits[key] = count
    if count > (120 if request.method == 'POST' else 300):
        raise HTTPException(429, 'Muitas solicitações. Tente novamente em um minuto.', headers={'Retry-After': '60'})


def translate_error(exc):
    return HTTPException(exc.status, detail={'code': exc.code, 'message': exc.message})


@router.get('/api/public/reservations/{restaurant_id}')
async def public_availability(restaurant_id: str, request: Request, response: Response,
                              date: str = Query(...), people: int = Query(2, ge=1, le=1000)):
    throttle(request)
    response.headers['Cache-Control'] = 'no-store'
    try:
        async with db.pool().acquire() as c:
            return await availability(c, restaurant_id, date, people)
    except BookingError as exc:
        raise translate_error(exc)
    except Exception:
        raise HTTPException(503, detail={'code': 'temporarily_unavailable', 'message': 'Não foi possível consultar a agenda agora. Tente novamente ou confirme com a equipe.'})


@router.post('/api/public/reservations/{restaurant_id}', status_code=201)
async def public_booking(restaurant_id: str, body: PublicBooking, request: Request, response: Response):
    throttle(request)
    response.headers['Cache-Control'] = 'no-store'
    try:
        result = await db.criar_reserva({'restaurant_id': restaurant_id, 'cliente_nome': body.name,
            'cliente_phone': body.phone, 'data': body.date, 'posicoes': body.people,
            'turno_id': str(body.slot_id), '_idempotency_key': str(body.idempotency_key), 'canal': 'widget'})
    except BookingError as exc:
        raise translate_error(exc)
    except Exception:
        raise HTTPException(503, detail={'code': 'temporarily_unavailable', 'message': 'Não foi possível concluir agora. Tente novamente com o mesmo pedido.'})
    response.status_code = 200 if result.get('_replayed') else 201
    return {'status': 'pending', 'reservation_id': str(result['id']), 'date': str(result['data']),
            'time': str(result['hora_inicio'])[:5], 'people': result['posicoes']}
