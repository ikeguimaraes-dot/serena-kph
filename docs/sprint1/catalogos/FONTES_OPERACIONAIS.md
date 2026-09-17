# Fontes operacionais — Meet e Madonna

Consulta em 17/09/2026, somente leitura. Não houve envio de mensagens, alteração de contatos, cadastro de membros, troca de webhook ou mudança de capacidade.

## Meet & Eat

- **Site oficial:** <https://www.meeteat.com.br/>.
- **Catálogo oficial:** o botão “Explore o cardápio” aponta para <https://livemenu.app/menu/62ffd74ddaf31500126b3e29>, confirmando a origem do pacote Meet existente.
- **Contato público para orçamento de eventos:** o botão “Orçamento” aponta para <https://wa.me/5511945511170>. O mesmo número foi encontrado no contato operacional salvo como **Vic Eventos Meet**. Evidência forte de contato para eventos do Meet. Não houve teste de entrega nem confirmação de disponibilidade atual.
- **Endereço publicado:** Rua Ramos Batista, 443, Vila Olímpia, São Paulo. O site publica horários, mas eles não foram promovidos automaticamente à agenda operacional.

### Capacidade: fonte pública inconsistente

O site informa 160 pessoas em pé e 100 sentadas; em outra seção, fala em três ambientes com até 110 pessoas cada. O Book Mestre registra a correção operacional para **96/68/80 sentados** e aponta expressamente que os canais públicos precisam ser corrigidos. Portanto, a publicação pública não prevalece sobre essa informação operacional. É necessária revisão do site pelo responsável. Nenhum número de capacidade foi alterado neste trabalho.

`fontes_operacionais_publicas.json` registra o status HTTP, horário, hash da página e links públicos. O HTML completo não foi copiado.

## Madonna Cucina

- **Catálogo oficial localizado:** <https://livemenu.app/menu/691377229337bdf1ad07625f>. Origem e extração estão documentadas em [madonna/README.md](madonna/README.md).
- **Contato salvo “Madonna Cucina Reservas”:** localizado na agenda conectada. Seu número pode ser o próprio canal automatizado; não deve ser usado como destinatário humano sem comparação com o remetente configurado.
- **Contato salvo “Alex - Gerente Madonna”:** localizado na agenda conectada. O nome indica função de gerência, mas a fonte não demonstra escala, disponibilidade ou designação atual como responsável por handoff.
- Os números privados desses dois contatos foram comunicados apenas ao agente responsável pela implementação e não foram incluídos no repositório. Nenhuma mensagem foi enviada.
- Não foi encontrada prova de que **Vic** seja responsável pelo handoff da **Madonna**. Não transferir essa atribuição automaticamente por ela atuar no Meet.

O domínio `madonnacucina.com.br` apareceu em referência pública, mas o leitor web não conseguiu abrir a página. O perfil público do Instagram foi limitado por throttling. Não houve tentativa de contornar essas limitações. Não se confirmou capacidade atual da Madonna em fonte oficial acessível. Resultados de imprensa, diretórios e Tripadvisor não foram usados para preencher capacidade ou preços.

## Lacunas concretas

1. Confirmar destinatário humano e turno de handoff Madonna, evitando o número de entrada da própria automação.
2. Confirmar que Vic recebe eventos/reservas no fluxo desejado do Meet e se há substituto fora da escala.
3. Corrigir a capacidade publicada no site Meet, tomando como referência os valores operacionais validados.
4. Resolver o vinho Madonna com preço zero e confirmar os centavos de Carne Cruda antes de aprovar esses valores comercialmente.
