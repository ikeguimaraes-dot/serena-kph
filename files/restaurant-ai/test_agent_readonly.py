"""Test turns must never reserve, cancel, update CRM or generate/send proposals."""
import os
os.environ.setdefault('ANTHROPIC_API_KEY','test-key-not-used')
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch
import agent


class ReadonlyTests(unittest.IsolatedAsyncioTestCase):
    async def run_tool(self,name,read_only):
        tool=NS(type='tool_use',name=name,id='fixture',input={})
        response=NS(stop_reason='tool_use',content=[tool],usage=None)
        done=NS(stop_reason='end_turn',content=[NS(type='text',text='Resposta de teste')],usage=None)
        with patch.object(agent.client.messages,'create',side_effect=[response,done]), \
             patch.object(agent,'execute_tool',new_callable=AsyncMock) as execute:
            execute.return_value='Fixture'
            await agent.RestaurantAgent()._run('system',[], '+000test','fixture',read_only=read_only)
            return execute.await_count

    async def test_all_write_tools_blocked(self):
        for name in ('fazer_reserva','cancelar_reserva','update_contact','gerar_proposta','calcular_proposta','future_unknown_tool'):
            with self.subTest(name=name): self.assertEqual(await self.run_tool(name,True),0)

    async def test_catalog_read_allowed(self):
        self.assertEqual(await self.run_tool('lookup_menu',True),1)

    async def test_live_flow_retains_write_tools(self):
        self.assertEqual(await self.run_tool('fazer_reserva',False),1)

    async def test_test_turn_enables_readonly(self):
        with patch.object(agent,'build_prompt',new_callable=AsyncMock,return_value=('system',1)), \
             patch.object(agent.RestaurantAgent,'_run',new_callable=AsyncMock) as run:
            run.return_value={'text':'ok','tokens_input':0,'tokens_output':0,'tools_called':[]}
            await agent.RestaurantAgent().test_turn('menu',{'id':'fixture'})
            self.assertTrue(run.call_args.kwargs['read_only'])


if __name__=='__main__': unittest.main()
