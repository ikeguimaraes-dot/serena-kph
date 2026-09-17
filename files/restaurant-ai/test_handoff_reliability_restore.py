"""Restored local database only, all notification transports mocked."""
import asyncio
import json
import os
import uuid
from pathlib import Path
from unittest.mock import Mock, patch
import asyncpg
import database as db
import notifications as notif


async def run():
    host=os.environ.get('PGHOST','')
    if not host.startswith('/tmp/serena-restore-') or os.environ.get('PGDATABASE')!='serena_restore':
        raise RuntimeError('Only isolated restore socket allowed')
    pool=await asyncpg.create_pool(host=host,port=int(os.environ['PGPORT']),user=os.environ['PGUSER'],database='serena_restore',ssl=False,min_size=1,max_size=5)
    db._pool=pool
    try:
        migration=Path(__file__).with_name('migrations').joinpath('20260917050154_handoff_reliability.sql').read_text()
        await pool.execute(migration); await pool.execute(migration)
        nonce=uuid.uuid4().hex
        a,b='handoff-a-'+nonce,'handoff-b-'+nonce
        phone='+15550000003'
        for rid,sender in ((a,'+15550000001'),(b,'+15550000002')):
            await pool.execute('INSERT INTO restaurants(id,nome,whatsapp_number,ativo) VALUES($1,$1,$2,true)',rid,sender)
            await db.ensure_contact(phone,'Synthetic '+rid,rid)
        discord=Mock(return_value=False)
        clinical=Mock(return_value=notif.NotificationResult('accepted','SM'+'a'*32,'queued'))
        with patch.object(notif,'notify_handoff_discord',discord),patch.object(notif,'notify_escalacao_gerente',clinical):
            first,duplicate=await asyncio.gather(db.create_handoff(phone,a,'Synthetic A'),db.create_handoff(phone,a,'Synthetic A'))
            assert first==duplicate and discord.call_count==1
            other=await db.create_handoff(phone,b,'Synthetic B')
            assert first!=other and discord.call_count==2
            assert await db.is_in_handoff(phone,a) and await db.is_in_handoff(phone,b)
            saved=await db.get_handoff_by_id(first)
            channels=json.loads(saved['notification_status'])
            assert channels['discord']['state']=='unconfirmed'
            assert channels['whatsapp']['state']=='skipped'
            assert saved['status']=='aguardando'
            # Existing duplicate rows are preserved but resolved as one chat.
            legacy=await pool.fetchval("INSERT INTO handoff_sessions(restaurant_id,user_phone,motivo) VALUES($1,$2,'Synthetic duplicate') RETURNING id",a,phone)
            assert await db.update_handoff_kanban(first,'resolvido')
            assert not await db.is_in_handoff(phone,a)
            assert await db.is_in_handoff(phone,b)
            assert await pool.fetchval('SELECT resolved_at IS NOT NULL FROM handoff_sessions WHERE id=$1',legacy)
            assert await pool.fetchval("SELECT count(*) FROM handoff_sessions WHERE restaurant_id=$1",a)==2
            reopened=await db.create_handoff(phone,a,'New request after resolution')
            assert reopened not in (first,legacy)
            assert await db.update_handoff_status(first,'resolvido')
            assert await db.is_in_handoff(phone,a)  # stale resolve cannot close reopened chat
            assert await db.update_handoff_status(reopened,'em_atendimento','Synthetic operator')
            row=await db.get_handoff_by_id(reopened)
            assert row['assumed_at'] is not None and row['first_human_response_at'] is None
            sid='SM'+'b'*32
            await db.record_human_handoff_reply(reopened,'Synthetic operator','Reply',sid)
            await db.record_human_handoff_reply(reopened,'Synthetic operator','Reply',sid)
            assert await pool.fetchval('SELECT count(*) FROM conversations WHERE restaurant_id=$1 AND provider_message_sid=$2',a,sid)==1
            row=await db.get_handoff_by_id(reopened)
            assert row['first_human_response_at'] is not None and row['last_reply_message_sid']==sid
            assert (await db.get_handoff_sla_stats(a))['tempo_primeira_resposta_minutos'] is not None
            assert not (await db.get_handoff_sla_stats(a))['sla_validado']
            assert not await db.update_handoff_status(reopened,'invalid')
            assert not await db.update_handoff_status(9223372036854775807,'resolvido')
            # Reject bot endpoints as human destinations, including other units.
            for number in ('whatsapp:+1 (555) 000-0001','+15550000002'):
                try:
                    await db.create_team_member(a,{'nome':'Synthetic','whatsapp':number,'role':'gerente'})
                    raise AssertionError('Bot sender must not be a human destination')
                except ValueError:
                    pass
            await db.create_team_member(a,{'nome':'Synthetic','whatsapp':'+15550000004','role':'gerente'})
            # Legacy misconfiguration is also excluded at routing time.
            await pool.execute("UPDATE team_members SET ativo=false WHERE restaurant_id='levvai'")
            await pool.execute("INSERT INTO team_members(restaurant_id,nome,whatsapp,role,ativo) VALUES('levvai','Synthetic loop',$1,'gerente',true)",'+15550000001')
            await pool.execute("INSERT INTO team_members(restaurant_id,nome,whatsapp,role,ativo) VALUES('levvai','Synthetic human',$1,'gerente',true)",'+15550000005')
            clinical_id=await db.create_handoff('+15550000006','levvai','[LARA] Synthetic clinical route')
            assert clinical.call_args.kwargs['gerente_whatsapp']=='+15550000005'
            clinical_state=json.loads((await db.get_handoff_by_id(clinical_id))['notification_status'])['whatsapp']
            assert clinical_state['provider_message_sid']=='SM'+'a'*32 and clinical_state['state']=='accepted'
            assert 'delivery_confirmed' not in clinical_state
        print(json.dumps({'success':True,'migration_replay':True,'concurrent_single_open_handoff':True,
            'notification_outcomes_persisted_without_delivery_claim':True,'duplicate_resolution_preserves_history':True,
            'human_reply_sid_and_first_response_atomic':True,'same_sid_persistence_idempotent':True,
            'live_status_after_resolution_and_reopen':True,'tenant_and_sender_loop_protection':True,'external_messages_sent':0}))
    finally:
        db._pool=None
        await pool.close()


if __name__=='__main__': asyncio.run(run())
