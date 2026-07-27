# Monitor de Caminhadas e Corridas (Appai)

Avisa você (via Telegram) sempre que a página logada
`associado.appai.org.br/caminhadas-e-corridas` mudar — ou seja, quando surgir
uma corrida nova ou o status de vaga mudar.

## Como funciona
Um robô (Playwright) faz login no Portal do Associado com seu usuário e
senha, abre a página de Caminhadas e Corridas, e compara o texto da página
com a última vez que rodou. Se mudou, te manda uma mensagem no Telegram.
Isso roda sozinho a cada 3h via GitHub Actions — você não precisa deixar
computador nenhum ligado.

⚠️ **Importante sobre privacidade/segurança**: sua matrícula e senha ficam
guardadas como "Secrets" criptografados do GitHub (nunca aparecem no código
nem em logs). Ainda assim, é sensato criar isso num repositório **privado**.

---

## Passo 1 — Testar o login localmente (recomendado antes de tudo)

Isso evita descobrir problemas só depois de configurar o GitHub Actions.

```bash
pip install playwright
playwright install chromium
APPAI_USER="sua_matricula" APPAI_PASS="sua_senha" python discover.py
```

Isso vai gerar:
- `discover_login.png` — print da tela de login (confira se carregou certo)
- `discover_page.png` — print da página de Caminhadas e Corridas já logado
- `discover_page.html` / `discover_page.txt` — conteúdo da página

**Se o login não funcionar automaticamente**: o script tenta adivinhar os
campos de usuário/senha (primeiro `<input type="text">` e primeiro
`<input type="password">` da página). Se a tela de login da Appai tiver uma
estrutura diferente, me mande o `discover_login.png` (ou o HTML da tela de
login) que eu ajusto o `monitor.py` e o `discover.py` para acertar os
seletores certos.

## Passo 2 — Criar um bot do Telegram (2 minutos, grátis)

1. No Telegram, procure o bot **@BotFather** e mande `/newbot`.
2. Siga as instruções e guarde o **token** que ele te dá (algo como
   `123456:ABC-...`).
3. Mande uma mensagem qualquer para o seu bot novo (para ele "conhecer" você).
4. Acesse no navegador:
   `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
   e pegue o número em `"chat":{"id": ...}` — esse é o seu `chat_id`.

## Passo 3 — Criar o repositório no GitHub

1. Crie um repositório **privado** no GitHub (ex: `appai-monitor`).
2. Suba estes arquivos (`monitor.py`, `discover.py`, `requirements.txt`,
   `.github/workflows/monitor.yml`, `README.md`) para ele.
3. Vá em **Settings → Secrets and variables → Actions → New repository
   secret** e crie 4 secrets:
   - `APPAI_USER` → sua matrícula
   - `APPAI_PASS` → sua senha
   - `TELEGRAM_BOT_TOKEN` → token do Passo 2
   - `TELEGRAM_CHAT_ID` → chat id do Passo 2

## Passo 4 — Rodar

- Vá na aba **Actions** do repositório, escolha o workflow "Monitorar
  Caminhadas e Corridas (Appai)" e clique em **Run workflow** para testar
  manualmente.
- Depois disso ele roda sozinho a cada 3 horas (pode mudar o intervalo
  editando o `cron` em `.github/workflows/monitor.yml`).
- Na primeira execução ele só salva o estado atual (sem aviso). A partir da
  segunda, qualquer mudança de conteúdo dispara mensagem no Telegram.

## Ajustando a sensibilidade / o que é comparado

Por padrão o script compara o **texto inteiro visível da página**. Isso
pega qualquer mudança (corrida nova, vaga liberada, etc.), mas também pode
disparar por mudanças irrelevantes (ex: um banner rotativo). Se isso
acontecer muito, me mande o `discover_page.html` gerado no Passo 1 que eu
ajusto o `monitor.py` para olhar só a área específica da lista de corridas.
