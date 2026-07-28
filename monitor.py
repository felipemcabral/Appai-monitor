"""
Monitor do benefício "Caminhadas e Corridas" da Appai.

O que faz:
1. Faz login no Portal do Associado (associado.appai.org.br) com Playwright
   (navegador headless), pois a página exige login e é renderizada via JS.
2. Abre a página de Caminhadas e Corridas e captura o texto visível.
3. Compara com a última versão salva (state.json).
4. Se houver diferença, envia um aviso via Telegram com o que mudou.

Como a estrutura exata do HTML da página não pôde ser inspecionada sem login
(o portal exige matrícula/senha), o script usa uma abordagem robusta: compara
o TEXTO VISÍVEL da página inteira (não depende de saber o nome de classes
CSS específicas). Isso já é suficiente para detectar:
  - uma corrida nova aparecendo na lista
  - o status de "vaga aberta"/"fora do período" mudando
  - qualquer texto novo na página

Se depois você quiser refinar (ex: extrair só o NOME de cada corrida em vez
do texto inteiro), rode primeiro o discover.py para ver a estrutura real da
página logada e me mande o HTML/print — aí eu ajusto os seletores.
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# ----------------------------------------------------------------------
# CONFIGURAÇÃO
# ----------------------------------------------------------------------

LOGIN_URL = "https://associado.appai.org.br/caminhadas-e-corridas"
TARGET_URL = "https://associado.appai.org.br/caminhadas-e-corridas"

STATE_FILE = Path("state.json")

APPAI_USER = os.environ.get("APPAI_USER")
APPAI_PASS = os.environ.get("APPAI_PASS")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# O Portal do Associado redireciona (via JS) para um servidor de login à
# parte: segurancaapi.appai.org.br, um sistema OAuth/OpenID (IdentityServer).
# Os nomes de campo abaixo cobrem os padrões mais comuns desse tipo de tela.
LOGIN_FIELD_CANDIDATES = [
    "input[name='Username']",
    "input[id='Username']",
    "input[name='Input.Username']",
    "input[id='Input_Username']",
    "input[name*='matricula' i]",
    "input[id*='matricula' i]",
    "input[name*='usuario' i]",
    "input[id*='usuario' i]",
    "input[name*='user' i]",
    "input[id*='user' i]",
    "input[type='email']",
    "input[type='text']",
]
PASSWORD_FIELD_CANDIDATES = [
    "input[name='Password']",
    "input[id='Password']",
    "input[name='Input.Password']",
    "input[id='Input_Password']",
    "input[type='password']",
]
SUBMIT_CANDIDATES = [
    "button[type='submit']",
    "input[type='submit']",
]


def log(msg: str) -> None:
    print(f"[monitor] {msg}", flush=True)


def send_telegram(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("Telegram não configurado (faltam TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID). Pulando envio.")
        return
    import urllib.request
    import urllib.parse

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text[:4000],  # limite do Telegram
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            log(f"Telegram respondeu status {resp.status}")
    except Exception as e:
        log(f"Falha ao enviar Telegram: {e}")


def normalize_text(raw: str) -> str:
    """Remove linhas ruidosas/variáveis (ex: relógios, contadores) para
    evitar falsos positivos."""
    lines = [l.strip() for l in raw.splitlines()]
    lines = [l for l in lines if l]
    # remove linhas que parecem timestamps tipo 12:34:56
    lines = [l for l in lines if not re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", l)]
    return "\n".join(lines)


def find_login_fields(page):
    """Procura os campos de usuário/senha na página principal E dentro de
    qualquer iframe (alguns portais colocam o formulário de login em um
    iframe, o que faz a página "principal" parecer vazia)."""
    frames_to_try = [page] + list(page.frames)
    for frame in frames_to_try:
        try:
            user_loc = None
            for sel in LOGIN_FIELD_CANDIDATES:
                if frame.locator(sel).count() > 0:
                    user_loc = frame.locator(sel).first
                    break
            pass_loc = None
            for sel in PASSWORD_FIELD_CANDIDATES:
                if frame.locator(sel).count() > 0:
                    pass_loc = frame.locator(sel).first
                    break
            if user_loc and pass_loc:
                return user_loc, pass_loc, frame
        except Exception:
            continue
    return None, None, None


def login_and_get_text() -> str:
    if not APPAI_USER or not APPAI_PASS:
        log("ERRO: defina as variáveis de ambiente APPAI_USER e APPAI_PASS.")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="pt-BR",
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.on("console", lambda msg: log(f"[console:{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: log(f"[pageerror] {err}"))

        log(f"Abrindo {LOGIN_URL}")
        page.goto(LOGIN_URL, wait_until="load", timeout=60000)

        # A página tenta redirecionar via JS para segurancaapi.appai.org.br
        # (tela de login OAuth). Esperamos essa troca de URL acontecer.
        try:
            page.wait_for_url(re.compile(r"segurancaapi\.appai\.org\.br"), timeout=20000)
            log("Redirecionado para o servidor de login (segurancaapi).")
        except Exception:
            log("Não foi redirecionado automaticamente para segurancaapi dentro do tempo esperado.")

        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            log("networkidle não atingido a tempo, seguindo mesmo assim.")
        page.wait_for_timeout(3000)

        # Diagnóstico sempre impresso no log, ajuda a entender o que a página
        # realmente carregou nesta execução.
        log(f"URL atual: {page.url}")
        log(f"Título da página: {page.title()!r}")
        log(f"Nº de <input> na página principal: {page.locator('input').count()}")
        log(f"Nº de iframes na página: {len(page.frames) - 1}")
        for i, fr in enumerate(page.frames):
            if fr is page.main_frame:
                continue
            log(f"  iframe[{i}] url={fr.url}")

        user_field, pass_field, login_frame = find_login_fields(page)

        if not user_field or not pass_field:
            page.screenshot(path="login_debug.png", full_page=True)
            with open("login_debug.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            log("Não encontrei os campos de login automaticamente (nem em iframes). "
                "Screenshot e HTML salvos em login_debug.png / login_debug.html.")
            sys.exit(1)

        log("Campos de login encontrados, preenchendo...")
        user_field.fill(APPAI_USER)
        pass_field.fill(APPAI_PASS)

        submitted = False
        for sel in SUBMIT_CANDIDATES:
            if login_frame.locator(sel).count() > 0:
                login_frame.locator(sel).first.click()
                submitted = True
                break
        if not submitted:
            pass_field.press("Enter")

        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            log("networkidle não atingido após login, seguindo mesmo assim.")
        page.wait_for_timeout(2000)
        log("Login enviado.")
        log(f"URL após login: {page.url}")

        log(f"Abrindo {TARGET_URL}")
        page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
        # espera extra pra SPA terminar de renderizar a lista
        page.wait_for_timeout(4000)

        text = page.inner_text("body")
        browser.close()
        return normalize_text(text)


def main() -> None:
    current_text = login_and_get_text()
    current_hash = hashlib.sha256(current_text.encode()).hexdigest()

    previous = {}
    if STATE_FILE.exists():
        previous = json.loads(STATE_FILE.read_text())

    previous_hash = previous.get("hash")
    previous_text = previous.get("text", "")

    if previous_hash is None:
        log("Primeira execução — salvando estado inicial, sem aviso.")
    elif current_hash != previous_hash:
        log("Mudança detectada! Enviando aviso.")
        old_lines = set(previous_text.splitlines())
        new_lines = set(current_text.splitlines())
        added = [l for l in new_lines - old_lines]
        removed = [l for l in old_lines - new_lines]

        msg = "🏃 Mudança detectada em Caminhadas e Corridas (Appai)!\n\n"
        if added:
            msg += "Novidades / linhas novas:\n" + "\n".join(f"+ {l}" for l in added[:20]) + "\n\n"
        if removed:
            msg += "Linhas que saíram:\n" + "\n".join(f"- {l}" for l in removed[:20]) + "\n\n"
        msg += f"Confira em: {TARGET_URL}"
        send_telegram(msg)
    else:
        log("Sem mudanças.")

    STATE_FILE.write_text(json.dumps({"hash": current_hash, "text": current_text}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
