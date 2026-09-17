"""NPS and customer value integration; disposable backup restore only, no sends."""
import asyncio
from decimal import Decimal
import os
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'files/restaurant-ai'))
os.environ.setdefault('ANTHROPIC_API_KEY','synthetic-no-api-call')
import asyncpg
import database as db
from test_recovery_contract import TransactionPool
import main as app

async def run():
    assert os.environ.get('PGDATABASE')=='serena_restore'
    assert os.environ.get('PGHOST','').startswith('/')
    c=await asyncpg.connect(host=os.environ['PGHOST'],port=int(os.environ['PGPORT']),user=os.environ['PGUSER'],database='serena_restore',ssl=False)
    tx=c.transaction();await tx.start();db._pool=TransactionPool(c)
    try:
        await c.execute((ROOT/'files/restaurant-ai/migrations/20260917043459_ctwa_cache_commercial_reporting.sql').read_text())
        suffix=uuid.uuid4().hex[:8]
        first,second='nps-a-'+suffix,'nps-b-'+suffix
        phone='+nps-customer-'+suffix
        ids={}
        for rid,value in [(first,Decimal('100.00')),(second,Decimal('900.00'))]:
            await c.execute('INSERT INTO restaurants(id,nome,whatsapp_number,ativo) VALUES($1,$1,$2,true)',rid,'+sender-'+rid)
            await db.upsert_contact({'celular':phone,'nome':'Synthetic'},restaurant_id=rid)
            ids[rid]=await c.fetchval("""INSERT INTO ordens_servico(restaurant_id,cliente_phone,cliente_nome,tipo_evento,data,hora_inicio,pessoas,status,valor_total,regua_d3_enviado_em)
                VALUES($1,$2,'Synthetic','teste','2026-09-01','19:00',2,'realizado',$3,now()) RETURNING id""",rid,phone,value)
        assert await app._tentar_capturar_nps(phone,'10','+sender-'+first,'SM-nps-'+suffix,'test-click')
        assert await c.fetchval('SELECT nps_score FROM ordens_servico WHERE id=$1',ids[first])==10
        assert await c.fetchval('SELECT nps_score FROM ordens_servico WHERE id=$1',ids[second]) is None
        assert not await app._tentar_capturar_nps(phone,'9','+sender-unknown')
        assert not await app._tentar_capturar_nps(phone,'10','+sender-'+first)
        assert not await db.registrar_nps(ids[second],1,first)
        assert await c.fetchval('SELECT count(*) FROM conversations WHERE restaurant_id=$1 AND user_phone=$2',first,phone)==1
        assert await c.fetchval('SELECT count(*) FROM conversations WHERE restaurant_id=$1 AND user_phone=$2',second,phone)==0
        a=await db.recalcular_ltv(first)
        assert a['ltv_total_brl']==100.0
        b=await db.get_contact(phone,restaurant_id=second)
        assert b['ltv_total'] in (None,Decimal('0'))
        b=await db.recalcular_ltv(second)
        assert b['ltv_total_brl']==900.0
        a=await db.get_contact(phone,restaurant_id=first)
        assert a['ltv_total']==Decimal('100')
        print('PASS: NPS sender ownership, immutable captured score, inbound trace and tenant-isolated value')
    finally:
        await tx.rollback();db._pool=None;await c.close()

if __name__=='__main__':asyncio.run(run())
