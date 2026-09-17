"""Production-schema regression test; all synthetic rows roll back, no messaging."""
import asyncio
import os

import asyncpg
import database as db
from test_recovery_contract import TransactionPool


async def run():
    connection = await asyncpg.connect(
        os.environ["DATABASE_URL"], ssl="require", statement_cache_size=0
    )
    transaction = connection.transaction()
    await transaction.start()
    db._pool = TransactionPool(connection)
    suffix = os.urandom(6).hex()
    phone = "+000-sprint1-" + suffix
    first, second = "sprint1-a-" + suffix, "sprint1-b-" + suffix
    try:
        for rid in (None, "freneze", "levvai", "madonna_cucina", "meet_and_eat"):
            assert "insights" in await db.insights_aggregate(rid)

        # Separate uncommitted tenants make fixtures independent of the UI top-25 limit.
        for rid in (first, second):
            await connection.execute(
                "INSERT INTO restaurants (id,nome,whatsapp_number,ativo) VALUES ($1,$1,$2,false)",
                rid, phone + rid,
            )
            await db.ensure_contact(phone, rid, rid)
            await db.save_message(phone, rid, "user", "Synthetic conversation " + rid)
            await connection.execute(
                "INSERT INTO handoff_sessions (user_phone,restaurant_id,motivo) "
                "VALUES ($1,$2,'Synthetic regression; never notify')", phone, rid,
            )
        await connection.execute(
            "UPDATE contacts SET tier='Ouro',ultima_visita=NOW()-INTERVAL '90 days' "
            "WHERE celular=$1 AND restaurant_id=$2", phone, first,
        )
        category = "sprint1-" + suffix
        for _ in range(3):
            await connection.execute(
                "INSERT INTO serena_metrics "
                "(user_phone,restaurant_id,handoff_acionado,handoff_categoria) VALUES ($1,$2,true,$3)",
                phone, first, category,
            )

        for rid in (first, second):
            conversations = await db.get_conversations_list(rid)
            assert len(conversations) == 1, "Conversation list must not duplicate the shared phone"
            assert conversations[0]["user_phone"] == phone
            assert conversations[0]["nome"] == rid, "Conversation must use its tenant's CRM name"
            assert conversations[0]["content"] == "Synthetic conversation " + rid
            for status in (None, "aguardando"):
                handoffs = await db.get_handoff_sessions(rid, status)
                assert len(handoffs) == 1, "Shared phone must not duplicate handoffs across tenants"
                assert handoffs[0]["restaurant_id"] == rid and handoffs[0]["user_phone"] == phone
                assert handoffs[0]["nome"] == rid, "Handoff must use its tenant's CRM name"

            result = await db.insights_aggregate(rid)
            gold = [row for item in result["insights"] if item["kind"] == "ouro_aguardando"
                    for row in item["items"]]
            inactive = [item for item in result["insights"] if item["kind"] == "reactivation"]
            patterns = [item for item in result["insights"] if item["kind"] == "faq_pattern"]
            if rid == first:
                assert len(gold) == 1 and gold[0]["nome"] == first
                assert len(inactive) == 1 and inactive[0]["title"].startswith("1 cliente ")
                assert len(patterns) == 1 and patterns[0]["id"] == "faq_" + category
            else:
                assert gold == [], "Other tenant must not inherit the same phone's Ouro tier"
                assert inactive == [], "Inactive clients must be counted within the tenant"
                assert patterns == [], "Handoff categories must be counted within the tenant"
        print("PASS: insights compile; conversations, handoffs and CRM profiles isolated by tenant")
    finally:
        await transaction.rollback()
        db._pool = None
        await connection.close()
        print("All Sprint 1 test rows rolled back; no messages sent")


if __name__ == "__main__":
    asyncio.run(run())
