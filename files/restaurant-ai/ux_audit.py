"""UX audit do painel Madonna Cucina via Playwright."""
import asyncio
import json
import time
from pathlib import Path
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout

BASE = "https://madonna-painel.vercel.app"
OUT = Path("/tmp/ux_report")
OUT.mkdir(exist_ok=True)

findings = []
console_errors_global = []


async def shot(page: Page, name: str) -> str:
    path = OUT / f"{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    return str(path)


async def visible_count(page: Page, selector: str) -> int:
    return await page.locator(selector).count()


def add_finding(fluxo, url, status, tempo_ms, notes, problems, screenshot):
    findings.append({
        "fluxo": fluxo, "url": url, "status": status,
        "tempo_ms": tempo_ms, "notes": notes, "problems": problems,
        "screenshot": screenshot,
    })


async def check_accessibility(page: Page) -> bool:
    """Testa se o painel não está atrás de auth wall. Retorna True se acessível."""
    try:
        resp = await page.goto(BASE, wait_until="domcontentloaded", timeout=15000)
        if resp and resp.status != 200:
            return False
        # Vercel protection page tem texto "Authentication Required" ou "Log in"
        body_text = await page.inner_text("body")
        if "Authentication Required" in body_text or "Vercel" in body_text and "Login" in body_text:
            return False
        return True
    except PlaywrightTimeout:
        return False


async def audit_dashboard(page: Page):
    notes, problems = [], []
    t0 = time.time()
    try:
        await page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_selector("text=Restaurant AI", timeout=10000)
        tempo = int((time.time() - t0) * 1000)
    except PlaywrightTimeout as e:
        tempo = int((time.time() - t0) * 1000)
        problems.append(("P1", f"Página não carregou em 20s: {str(e)[:100]}"))
        shot_path = await shot(page, "1_dashboard_ERROR")
        add_finding("1. Dashboard", f"{BASE}/", "❌", tempo, notes, problems, shot_path)
        return

    if tempo > 3000:
        problems.append(("P2", f"Dashboard carregou em {tempo}ms (>3s)"))
    notes.append(f"Carregou em {tempo}ms")
    await page.wait_for_timeout(3000)

    for label in ["Reservas Hoje", "Pessoas Esperadas", "Reservas no Mês", "Handoffs Abertos"]:
        c = await visible_count(page, f"text={label}")
        if c == 0:
            problems.append(("P1", f"Card '{label}' não encontrado"))
            notes.append(f"❌ Card '{label}' ausente")
        else:
            notes.append(f"✓ Card '{label}' presente")

    hp = await visible_count(page, "text=Handoffs Pendentes")
    notes.append(f"{'✓' if hp else 'ℹ'} 'Handoffs Pendentes': {'presente' if hp else 'ausente (esperado se vazio)'}")

    assumir = await visible_count(page, "button:has-text('Assumir')")
    if assumir == 0:
        problems.append(("P3", "Botão 'Assumir' nunca foi implementado"))
        notes.append("❌ Botão 'Assumir' inexistente")
    else:
        notes.append(f"✓ Botão 'Assumir' visível ({assumir}x)")

    shot_path = await shot(page, "1_dashboard")
    status = "❌" if any(p[0] == "P1" for p in problems) else ("⚠️" if problems else "✅")
    add_finding("1. Dashboard", f"{BASE}/", status, tempo, notes, problems, shot_path)


async def audit_conversas(page: Page):
    notes, problems = [], []
    t0 = time.time()
    try:
        await page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=20000)
        await page.click("button:has-text('Conversas')", timeout=10000)
        await page.wait_for_timeout(2500)
        tempo = int((time.time() - t0) * 1000)
    except PlaywrightTimeout as e:
        tempo = int((time.time() - t0) * 1000)
        problems.append(("P1", f"Não abriu Conversas: {str(e)[:100]}"))
        shot_path = await shot(page, "2_conversas_ERROR")
        add_finding("2. Conversas", f"{BASE}/ (tab)", "❌", tempo, notes, problems, shot_path)
        return

    notes.append(f"Carregou em {tempo}ms (incl. clique na tab)")
    notes.append("ℹ /conversas não é rota Next — é tab da SPA em /")

    if await visible_count(page, "text=Conversas Ativas"):
        notes.append("✓ Painel 'Conversas Ativas' visível")
    else:
        problems.append(("P1", "Lista 'Conversas Ativas' não renderizou"))

    # Itens da lista renderizam o user_phone num <span> dentro de um div clicável.
    conversations = page.locator("span").filter(has_text="+55")
    count = await conversations.count()
    notes.append(f"Conversas listadas: {count}")
    if count == 0:
        problems.append(("P2", "Nenhuma conversa listada — impossível testar resposta"))
    else:
        await conversations.first.click()
        await page.wait_for_timeout(1500)

        input_ph = await visible_count(page, "input[placeholder*='Responder']")
        input_disabled = await visible_count(page, "input[placeholder*='Responder']:disabled")
        if input_ph:
            notes.append(f"✓ Campo resposta visível ({'disabled (sem handoff)' if input_disabled else 'enabled'})")
            if not input_disabled:
                try:
                    await page.fill("input[placeholder*='Responder']", "teste diagnóstico — não enviar")
                    notes.append("✓ Campo aceita input")
                    send_disabled = await page.locator("button:has-text('Enviar')").is_disabled()
                    notes.append(f"{'ℹ' if send_disabled else '✓'} Botão 'Enviar' {'disabled' if send_disabled else 'ativo'}")
                except Exception as e:
                    problems.append(("P2", f"Erro ao preencher: {str(e)[:100]}"))
            else:
                notes.append("ℹ Input bloqueado — conversa sem handoff ativo")
        else:
            problems.append(("P1", "Campo 'Responder como atendente' não encontrado"))

        if await visible_count(page, "text=Histórico de conversa"):
            notes.append("✓ Painel histórico abriu à direita")
        else:
            problems.append(("P2", "Painel histórico não apareceu"))

    shot_path = await shot(page, "2_conversas")
    status = "❌" if any(p[0] == "P1" for p in problems) else ("⚠️" if problems else "✅")
    add_finding("2. Conversas", f"{BASE}/ (tab)", status, tempo, notes, problems, shot_path)


async def audit_contatos(page: Page):
    notes, problems = [], []
    t0 = time.time()
    try:
        await page.goto(f"{BASE}/contatos", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_selector("text=Contatos", timeout=10000)
        await page.wait_for_timeout(2500)
        tempo = int((time.time() - t0) * 1000)
    except PlaywrightTimeout as e:
        tempo = int((time.time() - t0) * 1000)
        problems.append(("P1", f"/contatos não carregou: {str(e)[:100]}"))
        shot_path = await shot(page, "3_contatos_ERROR")
        add_finding("3. Contatos", f"{BASE}/contatos", "❌", tempo, notes, problems, shot_path)
        return

    notes.append(f"Carregou em {tempo}ms")

    for f in ["Tier", "Estágio", "Ocasião", "Opt-in"]:
        if await visible_count(page, f"text={f}"):
            notes.append(f"✓ Filtro '{f}' visível")
        else:
            problems.append(("P2", f"Filtro '{f}' não encontrado"))

    search_input = page.locator("input[placeholder*='Buscar']")
    if await search_input.count():
        await search_input.fill("teste")
        await page.wait_for_timeout(1500)
        notes.append("✓ Busca aceita input e dispara query")
    else:
        problems.append(("P1", "Campo de busca não encontrado"))

    rows = await visible_count(page, "table tbody tr")
    empty_msg = await visible_count(page, "text=Nenhum contato encontrado")
    loading = await visible_count(page, "text=Carregando")
    if rows:
        notes.append(f"✓ Tabela com {rows} linhas após busca 'teste'")
    elif empty_msg:
        notes.append("✓ Empty state claro: 'Nenhum contato encontrado'")
    elif loading:
        problems.append(("P2", "Ainda 'Carregando…' após 4s — API lenta?"))
    else:
        problems.append(("P1", "Estado indefinido — nem tabela, nem empty, nem loading"))

    shot_path = await shot(page, "3_contatos")
    status = "❌" if any(p[0] == "P1" for p in problems) else ("⚠️" if problems else "✅")
    add_finding("3. Contatos", f"{BASE}/contatos", status, tempo, notes, problems, shot_path)


async def audit_kanban(page: Page):
    notes, problems = [], []
    t0 = time.time()
    try:
        await page.goto(f"{BASE}/kanban", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_selector("text=Kanban", timeout=10000)
        await page.wait_for_timeout(2500)
        tempo = int((time.time() - t0) * 1000)
    except PlaywrightTimeout as e:
        tempo = int((time.time() - t0) * 1000)
        problems.append(("P1", f"/kanban não carregou: {str(e)[:100]}"))
        shot_path = await shot(page, "4_kanban_ERROR")
        add_finding("4. Kanban", f"{BASE}/kanban", "❌", tempo, notes, problems, shot_path)
        return

    notes.append(f"Carregou em {tempo}ms")

    colunas = ["Novo Lead", "Qualificado", "Proposta Enviada", "Confirmado", "Realizado", "Recorrente", "Inativo"]
    faltando = [c for c in colunas if await visible_count(page, f"text={c}") == 0]
    if faltando:
        problems.append(("P1", f"Colunas ausentes: {', '.join(faltando)}"))
    else:
        notes.append("✓ Todas as 7 colunas presentes")

    for f in ["Tier", "Ocasião"]:
        if await visible_count(page, f"text={f}"):
            notes.append(f"✓ Filtro '{f}' visível")
        else:
            problems.append(("P2", f"Filtro '{f}' não encontrado"))

    empty = await visible_count(page, "text=Sem contatos")
    notes.append(f"ℹ {empty} coluna(s) com empty state")

    shot_path = await shot(page, "4_kanban")
    status = "❌" if any(p[0] == "P1" for p in problems) else ("⚠️" if problems else "✅")
    add_finding("4. Kanban", f"{BASE}/kanban", status, tempo, notes, problems, shot_path)


async def audit_relatorios(page: Page):
    notes, problems = [], []
    t0 = time.time()
    try:
        await page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=20000)
        await page.click("button:has-text('Relatórios')", timeout=10000)
        await page.wait_for_timeout(3500)
        tempo = int((time.time() - t0) * 1000)
    except PlaywrightTimeout as e:
        tempo = int((time.time() - t0) * 1000)
        problems.append(("P1", f"Não abriu Relatórios: {str(e)[:100]}"))
        shot_path = await shot(page, "5_relatorios_ERROR")
        add_finding("5. Relatórios", f"{BASE}/ (tab)", "❌", tempo, notes, problems, shot_path)
        return

    notes.append(f"Carregou em {tempo}ms")
    notes.append("ℹ /relatorios não é rota — é tab da SPA em /")

    for card in ["Taxa de Conversão", "Taxa de Cancelamento", "NPS"]:
        if await visible_count(page, f"text={card}"):
            notes.append(f"✓ Card '{card}' presente")
        else:
            problems.append(("P1", f"Card '{card}' ausente"))

    if await visible_count(page, "text=Performance Mensal"):
        notes.append("✓ 'Performance Mensal' presente")
    else:
        problems.append(("P1", "'Performance Mensal' não encontrada"))

    charts = await visible_count(page, ".recharts-responsive-container")
    notes.append(f"Recharts containers: {charts}")
    if charts < 2:
        problems.append(("P2", f"Esperava 2 gráficos, encontrei {charts}"))

    empty = await visible_count(page, "text=Nenhum dado disponível")
    if empty:
        notes.append(f"ℹ {empty}x 'Nenhum dado disponível' (ok se sem reservas)")

    shot_path = await shot(page, "5_relatorios")
    status = "❌" if any(p[0] == "P1" for p in problems) else ("⚠️" if problems else "✅")
    add_finding("5. Relatórios", f"{BASE}/ (tab)", status, tempo, notes, problems, shot_path)


def generate_report() -> str:
    lines = [
        "# Diagnóstico UX — Painel Madonna Cucina",
        f"\n**URL:** {BASE}",
        f"**Rodado:** {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Resumo\n",
        "| # | Fluxo | Status | Tempo | # Problemas |",
        "|---|-------|--------|-------|-------------|",
    ]
    for f in findings:
        num = f["fluxo"].split(".")[0]
        nome = f["fluxo"].split(". ", 1)[1] if ". " in f["fluxo"] else f["fluxo"]
        lines.append(f"| {num} | {nome} | {f['status']} | {f['tempo_ms']}ms | {len(f['problems'])} |")

    p1, p2, p3 = [], [], []
    for f in findings:
        for prio, msg in f["problems"]:
            {"P1": p1, "P2": p2, "P3": p3}[prio].append(f"**[{f['fluxo']}]** {msg}")

    lines.append("\n## Problemas priorizados\n")
    lines.append("### 🔴 P1 — Crítico")
    lines.extend([f"- {m}" for m in p1] or ["- Nenhum 🎉"])
    lines.append("\n### 🟡 P2 — Importante")
    lines.extend([f"- {m}" for m in p2] or ["- Nenhum"])
    lines.append("\n### 🔵 P3 — Melhoria")
    lines.extend([f"- {m}" for m in p3] or ["- Nenhum"])

    lines.append("\n## Erros de console\n")
    if console_errors_global:
        for e in console_errors_global[:20]:
            lines.append(f"- `{e[:200]}`")
    else:
        lines.append("- Nenhum 🎉")

    lines.append("\n## Detalhes por fluxo\n")
    for f in findings:
        lines.append(f"### {f['fluxo']} — {f['status']}")
        lines.append(f"URL: `{f['url']}` · Tempo: {f['tempo_ms']}ms")
        lines.append(f"\n![screenshot]({f['screenshot']})\n")
        lines.append("**Observações:**")
        lines.extend([f"- {n}" for n in f["notes"]])
        if f["problems"]:
            lines.append("\n**Problemas:**")
            lines.extend([f"- [{prio}] {msg}" for prio, msg in f["problems"]])
        lines.append("")

    return "\n".join(lines)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1366, "height": 800})
        page = await ctx.new_page()

        page.on("console", lambda msg: console_errors_global.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: console_errors_global.append(f"pageerror: {exc}"))

        # Check if Vercel protection is still on
        accessible = await check_accessibility(page)
        if not accessible:
            await shot(page, "00_access_wall")
            print("⚠ Site não acessível — provavelmente Vercel Deployment Protection ainda ligado.")
            print(f"  Screenshot: {OUT}/00_access_wall.png")
            print(f"  Abra a URL em janela anônima: {BASE}")
            await browser.close()
            report = (
                f"# Diagnóstico UX — BLOQUEADO\n\n"
                f"**URL:** {BASE}\n\n"
                f"⚠ O painel retornou HTTP 401 ou tela de login Vercel — "
                f"Deployment Protection ainda está ligado no dashboard Vercel.\n\n"
                f"**Ação:** vercel.com → projeto madonna-painel → Settings → Deployment Protection "
                f"→ 'Only Preview Deployments' ou 'Disabled' → Save.\n\n"
                f"Screenshot da tela de bloqueio: `{OUT}/00_access_wall.png`\n"
            )
            (OUT / "report.md").write_text(report)
            print(report)
            return

        await audit_dashboard(page)
        await audit_conversas(page)
        await audit_contatos(page)
        await audit_kanban(page)
        await audit_relatorios(page)

        await browser.close()

    report = generate_report()
    (OUT / "report.md").write_text(report)
    (OUT / "findings.json").write_text(json.dumps(findings, indent=2, ensure_ascii=False))
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
