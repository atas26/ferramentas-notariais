# Handoff — migração da Calculadora Avançada (repo `atas26/calculadoras`) para o Contabo

> **Para quem é isto:** a **sessão Claude do repositório `calculadoras`**.
> **Quem escreveu:** a sessão do repositório `ferramentas-notariais` (o site do Portal), que já
> migrou 4 ferramentas para o Contabo (ITCMD, Ganho de Capital, Classificador, Agenda) usando o
> padrão validado abaixo. Este documento reúne **tudo que foi levantado do servidor** para você
> não precisar redescobrir. Cole este arquivo (ou o resumo no fim) na sessão da calculadora.

A Calculadora Avançada é a **mais complexa e a de maior risco** das ferramentas: tem **Postgres com
dados reais de assinantes**, **Celery + Redis** e **segredos de pagamento**. Por isso ela é a única
que **não** deve ser migrada "no braço" junto com as outras — merece um passo dedicado, e é este.

---

## 1. Estado atual (produção)

| Item | Valor |
|---|---|
| Domínio de produção | `https://calculadora.portalnotarial.com.br/calculus/` |
| DNS | CNAME → `calculadoras-yn6w.onrender.com` (Render, IPs 216.24.57.x) — **ainda no Render** |
| Repositório | `https://github.com/atas26/calculadoras.git` |
| Framework | Django (app `calculus`; `calculadora.wsgi:application`, `--chdir calculadora`) |
| Path | Servida sob o prefixo **`/calculus/`** (não em `/`) |
| Banco (produção) | **Postgres no Render** (`calculadoras-db`) — **CONFIRMAR** e tratar com cuidado (dados reais) |
| Fila | **Celery** (worker) + **Redis** (broker) |
| Pagamento | Stripe hoje → **vai migrar para Mercado Pago** (coordenar; não fixar Stripe) |
| Segredos | Mercado Pago, OpenAI, Gemini, DeepSeek (motores de IA) |

---

## 2. O servidor Contabo — o que JÁ existe (não pise em cima!)

- **IP:** `89.117.73.91` · **usuário:** `fernando` · Ubuntu 22.04 · Apache 2.4 (80/443) · **sem painel**.
- **Padrão do servidor (validado em 4 ferramentas):** Apache + **Gunicorn em socket unix** + **certbot** (Let's Encrypt). **Não** é Docker.
- **Redis já está no ar:** `redis-server.service` ativo em `127.0.0.1:6379` (broker compartilhado). Use um **número de DB Redis** livre para o Celery da calculadora (ex.: `redis://127.0.0.1:6379/3`) para não colidir com outros serviços.
- **Sem Postgres local** (nada na 5432). Se optar por banco local, precisa **instalar/subir o Postgres** no Contabo primeiro.
- **Pasta do socket** já configurada via tmpfiles: `/run/gunicorn` (`d /run/gunicorn 0775 fernando www-data -`).

### ⚠️ Já existe uma instância `calculus` no Contabo — NÃO é a de produção
- `gunicorn_calculadora.service` (ativo) serve **`calculoescritura.com.br`**, a partir de `/home/fernando/calculadora`.
- Essa cópia **não é git** (`fatal: not a git repository`), usa **SQLite próprio** (`/home/fernando/calculadora/calculadora/db.sqlite3`) e tem **dados diferentes** da produção. É uma instância paralela/dev de outro produto/domínio.
- **Não sobrescreva** `/home/fernando/calculadora` nem o serviço `gunicorn_calculadora`. Faça o deploy da calculadora de produção em **pasta e serviço novos** (ex.: `/home/fernando/calculadora-portal` e `gunicorn_calculadora_portal`), com **subdomínio de staging próprio**.

---

## 3. Decisões que ESTA migração precisa tomar (antes de executar)

1. **Banco (o ponto crítico — dados de assinantes):**
   - **Estratégia A** — Contabo aponta para o **Postgres do Render** temporariamente (`DATABASE_URL` do Render no env). Sobe rápido, sem migrar dados agora; ainda depende do Render por um tempo.
   - **Estratégia B** — **Postgres local** no Contabo + **dump/restore** dos dados do Render, com **janela de manutenção** (congelar escrita durante a cópia para não perder registros). Independência total.
   - Recomendação: começar por **A** para tirar do Render sem risco, e fazer **B** depois, planejado, como parte da saída definitiva do Render.
2. **Path `/calculus/`** — replicar o prefixo (via `FORCE_SCRIPT_NAME=/calculus` no Django + `ProxyPass /calculus/` no Apache, ou o esquema que o app já usa no Render). O `urls.py` tem `path('calculus/', RedirectView(...home))`.
3. **Celery** — criar um **systemd próprio** (`celery-calculadora-portal.service`) apontando pro broker Redis (DB livre). Rodar as tasks com o mesmo env do web.
4. **Pagamento** — Stripe→Mercado Pago é migração paralela (feita na sessão `portal-notarial-app`). **Coordene**: não hardcode Stripe; use as chaves que o app padronizar.
5. **Slug do `pn_token`** — confirmar no código o slug esperado (provável `calculadora-avancada` ou `calculus`). Tem que bater com o que o hub emite.
6. **Subdomínio de staging** — usar `calculadora-teste.portalnotarial.com.br` → `89.117.73.91`. **Nunca** mexer no CNAME de produção (`calculadora.portalnotarial.com.br` → Render) antes do cutover.

---

## 4. Receita validada do Contabo (Django) — resumo

Igual ao que funcionou no ITCMD/Ganho. Troque as variáveis (pasta/serviço/subdomínio NOVOS):

```
TOOL=calculadora-portal
DIR=/home/fernando/calculadora-portal
SUB=calculadora-teste.portalnotarial.com.br
SOCK=/run/gunicorn/gunicorn_${TOOL}.sock
SVC=gunicorn_${TOOL}
WSGI=calculadora.wsgi:application   # com WorkingDirectory=$DIR/calculadora OU --chdir calculadora
```

Passos: clonar do repo → venv + `pip install -r requirements.txt` + `gunicorn` → `/etc/default/$TOOL`
(env, `640 root:fernando`) → `migrate` (na estratégia escolhida) + `collectstatic` + comandos de dados
(ex.: `import_itbi`, `import_juros`) → **systemd web** → **systemd Celery** → Apache `:80` (ACME+redirect)
→ `certbot` → Apache `:443` (SSL + `ProxyPass` pro socket + `RequestHeader set X-Forwarded-Proto "https"`
+ tratar `/calculus/` e `ProxyPass /static/ !`) → **prova E2E com token**.

O passo a passo completo copiável está em `deploy/RECEITA-tool-python.md` (Django) neste repo — e as
variações FastAPI (verify remoto e HMAC+Supabase) nas ferramentas 3 e 4, se precisar de referência.

### systemd web (modelo)
```ini
[Unit]
Description=gunicorn daemon for calculadora-portal
After=network.target
[Service]
User=fernando
Group=www-data
WorkingDirectory=/home/fernando/calculadora-portal
EnvironmentFile=/etc/default/calculadora-portal
ExecStart=/home/fernando/calculadora-portal/venv/bin/gunicorn --workers 3 --timeout 3600 \
  --chdir calculadora --bind unix:/run/gunicorn/gunicorn_calculadora-portal.sock calculadora.wsgi:application
[Install]
WantedBy=multi-user.target
```

### systemd Celery (modelo)
```ini
[Unit]
Description=Celery Worker (calculadora-portal)
After=network.target redis-server.service
[Service]
User=fernando
Group=www-data
WorkingDirectory=/home/fernando/calculadora-portal/calculadora
EnvironmentFile=/etc/default/calculadora-portal
ExecStart=/home/fernando/calculadora-portal/venv/bin/celery -A calculadora worker -l info --concurrency=2
[Install]
WantedBy=multi-user.target
```

---

## 5. CONTRATO DO `pn_token` (não pode quebrar)

As ferramentas migradas validam o acesso pelo **mesmo** token do hub. Formato:
`<base64url(JSON, sem padding)>.<hmac_sha256_hex>` — payload `{slug, exp, sub, email, iat}`.
Cookie `pn_tool_access` (HttpOnly, Secure, SameSite=Lax, Max-Age 7200).

- **Segredo compartilhado:** `PORTAL_TOOL_ACCESS_SECRET` — o **mesmo** em todas as ferramentas e no app.
  No Contabo, o valor está em `/etc/default/itcmd` (copie de lá; **nunca** cole no chat/Git).
- A Calculadora deve validar por **HMAC local** (com esse segredo) OU por **verify remoto**
  (`https://app.portalnotarial.com.br/api/tool-ticket/verify-get`), conforme o código dela já faz.

### Teste E2E (forja um token e abre a ferramenta)
```bash
python3 - <<'PY'
import json, base64, hmac, hashlib, time
secret=None
for line in open("/etc/default/itcmd"):
    if line.startswith("PORTAL_TOOL_ACCESS_SECRET="):
        secret=line.split("=",1)[1].strip().encode(); break
now=int(time.time())
payload={"slug":"<SLUG-DA-CALCULADORA>","exp":now+600,"sub":"teste-migracao","email":"teste@portalnotarial.com.br","iat":now}
b64=base64.urlsafe_b64encode(json.dumps(payload,separators=(",",":")).encode()).rstrip(b"=").decode()
sig=hmac.new(secret,b64.encode(),hashlib.sha256).hexdigest()
print("https://calculadora-teste.portalnotarial.com.br/calculus/?pn_token="+b64+"."+sig)
PY
```
Abrir a URL no navegador → a Calculadora deve **renderizar** (não redirecionar para login).

---

## 6. Cutover (só no fim, quando o staging estiver 100%)
1. App aponta a Calculadora para o novo domínio/instância.
2. Trocar o DNS de produção (`calculadora.portalnotarial.com.br` CNAME→Render) para **A → 89.117.73.91** (Contabo).
3. Desligar o serviço no Render.
4. (Estratégia B) Fazer o dump/restore final do banco na janela de manutenção **antes** de trocar o DNS.

---

## 7. Resumo curtíssimo (se for colar só um parágrafo)
> Migrar a Calculadora Avançada (`atas26/calculadoras`, Django app `calculus`, path `/calculus/`) do
> Render para o Contabo (`89.117.73.91`, user `fernando`, padrão Apache+Gunicorn-socket+certbot; Redis
> já ativo em `127.0.0.1:6379`; **sem** Postgres local). **Não** sobrescrever a instância existente
> `/home/fernando/calculadora` (é outra app, `calculoescritura.com.br`, SQLite). Fazer deploy em pasta/
> serviço NOVOS + subdomínio `calculadora-teste.portalnotarial.com.br`. Decidir a estratégia de banco
> (A: apontar pro Postgres do Render; B: Postgres local + dump/restore). Criar systemd web + Celery.
> Validar o `pn_token` (segredo em `/etc/default/itcmd`, mesmo do hub). Coordenar Stripe→Mercado Pago
> com a sessão do `portal-notarial-app`. Cutover só no fim (DNS + desligar Render).
