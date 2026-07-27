"""
Script de DIAGNÓSTICO — rode este primeiro, uma vez, localmente (não precisa
ser no GitHub Actions), para confirmar que o login automático funciona e ver
a página real depois de logado.

Gera:
  - discover_login.png   (screenshot da tela de login antes de enviar)
  - discover_page.png    (screenshot da página de Caminhadas e Corridas já logado)
  - discover_page.html   (HTML renderizado da página, já com JS executado)
  - discover_page.txt    (texto visível da página)

Uso:
  APPAI_USER="sua_matricula" APPAI_PASS="sua_senha" python discover.py
"""

import os
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://associado.appai.org.br/autenticar.aspx?ReturnUrl=/"
TARGET_URL = "https://associado.appai.org.br/caminhadas-e-corridas"

APPAI_USER = os.environ["APPAI_USER"]
APPAI_PASS = os.environ["APPAI_PASS"]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(locale="pt-BR")

    page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
    page.screenshot(path="discover_login.png", full_page=True)
    print("Screenshot da tela de login salvo em discover_login.png")
    print("Campos <input> encontrados na tela de login:")
    for el in page.locator("input").all():
        print(" -", el.evaluate("e => e.outerHTML"))

    # tentativa simples de login (mesma lógica do monitor.py)
    user_field = page.locator("input[type='text']").first
    pass_field = page.locator("input[type='password']").first
    user_field.fill(APPAI_USER)
    pass_field.fill(APPAI_PASS)

    if page.locator("button[type='submit']").count() > 0:
        page.locator("button[type='submit']").first.click()
    elif page.locator("input[type='submit']").count() > 0:
        page.locator("input[type='submit']").first.click()
    else:
        pass_field.press("Enter")

    page.wait_for_load_state("networkidle", timeout=60000)

    page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(4000)

    page.screenshot(path="discover_page.png", full_page=True)
    with open("discover_page.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    with open("discover_page.txt", "w", encoding="utf-8") as f:
        f.write(page.inner_text("body"))

    print("Pronto! Veja discover_page.png / .html / .txt")
    browser.close()
