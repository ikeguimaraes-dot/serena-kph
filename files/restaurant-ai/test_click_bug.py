"""Reproduz o bug reportado: clicar em conversa não abre histórico."""
import asyncio
from playwright.async_api import async_playwright

BASE = "https://madonna-painel.vercel.app"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1366, "height": 800})
        page = await ctx.new_page()

        errors = []
        page.on("console", lambda m: errors.append(f"[console.{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        net_fails = []
        page.on("requestfailed", lambda r: net_fails.append(f"{r.method} {r.url} → {r.failure}"))

        await page.goto(f"{BASE}/", wait_until="domcontentloaded")
        await page.click("button:has-text('Conversas')")
        await page.wait_for_timeout(3500)

        # Conta items da lista antes do click
        items_before = await page.locator("span").filter(has_text="+55").count()
        print(f"items na lista: {items_before}")

        panel_before = await page.locator("text=Selecione uma conversa").count()
        print(f"painel direito está mostrando 'Selecione uma conversa' antes do click: {panel_before > 0}")

        if items_before == 0:
            print("⚠ sem conversas pra clicar — teste inconclusivo")
            await browser.close()
            return

        # Captura o telefone que vai clicar
        first_phone_span = page.locator("span").filter(has_text="+55").first
        phone_text = await first_phone_span.inner_text()
        print(f"vou clicar em: {phone_text!r}")

        # Clica no DIV pai clicável (o span em si não é clicável — o div com cursor:pointer é)
        first_item = page.locator("div[style*='cursor']").filter(has_text="+55").first
        await first_item.click()
        print("clique disparado")

        await page.wait_for_timeout(3000)

        # Verifica estados após click
        panel_after = await page.locator("text=Selecione uma conversa").count()
        hist_header = await page.locator("text=Histórico de conversa").count()
        hist_msgs = await page.locator("div:has-text('Serena')").count()
        selected_phone_in_panel = await page.locator(f"text={phone_text}").count()

        print()
        print("=== RESULTADO ===")
        print(f"'Selecione uma conversa' ainda visível? {panel_after > 0}")
        print(f"'Histórico de conversa' header visível? {hist_header > 0}")
        print(f"phone {phone_text!r} aparece no painel direito? {selected_phone_in_panel > 1}")  # >1 porque aparece na lista também

        print()
        print("=== network fails ===")
        for f in net_fails[:10]:
            print(f)
        print()
        print("=== console errors ===")
        for e in errors[:10]:
            print(e)

        # Screenshot pós-click
        await page.screenshot(path="/tmp/click_bug.png", full_page=True)
        print("\nscreenshot: /tmp/click_bug.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
