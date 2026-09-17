"""Opt-in DATABASE_URL regression with synthetic tenants and guaranteed rollback.

Never sends messages or reads existing customer records. Run as a standalone script.
"""
import asyncio
import os

import asyncpg
import database as db
from test_recovery_contract import TransactionPool


async def run():
    connection = await asyncpg.connect(os.environ["DATABASE_URL"], ssl="require", statement_cache_size=0)
    transaction = connection.transaction()
    await transaction.start()
    db._pool = TransactionPool(connection)
    suffix = os.urandom(6).hex()
    phone = "+auth-test-" + suffix
    first, second = "auth-a-" + suffix, "auth-b-" + suffix
    try:
        for rid in (first, second):
            await connection.execute(
                "INSERT INTO restaurants (id,nome,whatsapp_number,ativo) VALUES ($1,$1,$2,false)",
                rid, phone + rid)
            await db.upsert_contact({"celular": phone, "nome": rid, "notas": rid}, restaurant_id=rid)
            await db.save_message(phone, rid, "user", "Synthetic " + rid)
        await db.update_contact(phone, {"nome": "Changed first"}, restaurant_id=first)
        await db.move_contact_kanban(phone, "qualificado", restaurant_id=first)
        for rid in (first, second):
            contact = await db.get_contact(phone, restaurant_id=rid)
            assert contact["nome"] == ("Changed first" if rid == first else second)
            assert contact["notas"] == rid
            assert len(await db.list_contacts(restaurant_id=rid)) == 1
            results = await db.search_contacts(phone, restaurant_id=rid)
            assert len(results) == 1 and results[0]["restaurant_id"] == rid
            assert (await db.contact_stats(restaurant_id=rid))["total"] == 1
            assert (await db.get_funil_stats(restaurant_id=rid))["leads_7d"] == 1
            messages = await db.get_contact_conversations(phone, restaurant_id=rid)
            assert len(messages) == 1 and messages[0]["restaurant_id"] == rid
            assert await db.get_contact_reservations(phone, restaurant_id=rid) == []
        assert await db.get_contact(phone) is None
        assert await db.update_contact(phone, {"nome": "Unscoped"}) is None
        try:
            await db.upsert_contact({"celular": phone, "nome": "Unscoped"})
        except ValueError:
            pass
        else:
            raise AssertionError("Unscoped upsert must be rejected")
        print("PASS: scoped CRM upsert, update, search, stats, history and no implicit cross-unit profile")
    finally:
        await transaction.rollback()
        db._pool = None
        await connection.close()
        print("All auth test records rolled back; no messages sent")


if __name__ == "__main__":
    asyncio.run(run())
