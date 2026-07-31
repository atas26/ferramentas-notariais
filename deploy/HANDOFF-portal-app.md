# Handoff — do repositório `ferramentas-notariais` para a sessão do `portal-notarial-app`

Este documento é o **mapeamento feito pelo lado das Ferramentas** para orientar a
migração (Render → Contabo) e a troca de **Supabase → próprio** e **Stripe → Mercado Pago**,
que serão implementadas no repositório `portal-notarial-app`.

O ponto mais importante está na seção **"CONTRATO DE INTEGRAÇÃO"**: é o que o app usa
para liberar o acesso às ferramentas. **Isso não pode quebrar na migração.**

---

## 0. STATUS ATUAL (atualizado — leia primeiro)

A migração Render → Contabo **já foi feita para todas as ferramentas e o site**. Falta
**só o app** (`portal-notarial-app`) — que é o alvo desta sessão.

**Já no Contabo (89.117.73.91), domínios de produção virados no registro.br:**
- `itcmd.portalnotarial.com.br` (ITCMD) · `ganhodecapital.portalnotarial.com.br` (Ganho)
- `classificadordearquivos.portalnotarial.com.br` (Classificador) · `agenda.portalnotarial.com.br` (Agenda)
- `calculadora.portalnotarial.com.br` (Calculadora Avançada)
- **Site:** `portalnotarial.com.br` (apex) + `www` + `ferramentas` → Node no Contabo, **guard ativo** (Tarifas/Emolumentos agora protegidas)
- Padrão do servidor: **Apache + Gunicorn/Node (socket ou porta local) + certbot**. Redis já ativo. Sem Docker.
- Segredo `PORTAL_TOOL_ACCESS_SECRET` já replicado em todas as ferramentas (o MESMO do app).

**Ainda no Render:**
- 🔴 **`app.portalnotarial.com.br` → portal-notarial-app.onrender.com — ESTE (o hub).**
- ⚪ `cpf-rf`, `triagem`, `verificador` — ferramentas não-prioritárias, **suspensas**, migração posterior.

### ⚠️ ALERTA CRÍTICO antes de virar o app
1. **NÃO suspenda o app no Render antes de migrá-lo.** Hoje TODAS as ferramentas dependem dele:
   nenhuma abre sem o `pn_token` que só ele emite para assinante ativo.
2. **O Classificador faz VERIFY REMOTO** direto em `https://app.portalnotarial.com.br/api/tool-ticket/verify-get`
   a cada acesso. Se esse endpoint sair do ar ou mudar de contrato, **o Classificador para na hora**.
   Mantenha o endpoint e o segredo idênticos durante e depois da virada.
3. A virada do app é a **última e mais delicada** (leva junto Supabase→próprio e Stripe→Mercado Pago,
   com dados reais de assinantes e cobrança). Faça com os gates: plano no MP, E2E sandbox, `pg_dump`
   do Supabase, reautorização dos assinantes atuais. Só então troque o DNS `app` (CNAME→Render) por
   **A → 89.117.73.91** e desligue o app no Render.

### Receita de deploy já validada (no repo `ferramentas-notariais`)
- `deploy/RECEITA-site-node.md` (Node) e `deploy/RECEITA-tool-python.md` (Django/Gunicorn) — o app é Node,
  então o padrão do site serve de molde: systemd rodando `node server.js` com `HOST=127.0.0.1`, Apache
  `ProxyPass` para a porta local, `RequestHeader set X-Forwarded-Proto "https"`, certbot.

---

## 1. Arquitetura atual (11 ativos no Render + 2 fora dos prints)

| Serviço (Render) | Runtime | Papel |
|---|---|---|
| ferramentas-notariais | Node (`server.js`) | site + **guard** de acesso (este repo) |
| consulta-pep-backend | Node | backend Consulta PEP (este repo, `backend/`) |
| **portal-notarial-app** | Node | **login + assinatura (Supabase + Stripe)** ← alvo desta sessão |
| calculadoras | Python | backend de calculadora |
| calculadoras-db | PostgreSQL | banco |
| CPF-RF | Python | Consulta de óbito por CPF/RF |
| ganho-de-capital | Python | Ganho de Capital |
| itcmd-sp | Python | ITCMD |
| agenda-cartorios | Python | Agenda Notarial |
| organizador-de-arquivos | Python | Classificador de Arquivos |
| exigencia-imob-portal-notarial | Node | Analisador de exigências |
| consulta-selo-digital-tjsp *(fora dos prints)* | Python | Consulta de Selo Digital |
| pagina-inicial *(fora dos prints)* | ? | API "reportar link quebrado" |

---

## 2. CONTRATO DE INTEGRAÇÃO (o que o app faz e NÃO pode mudar)

O app libera o acesso emitindo um **token HMAC**. As ferramentas validam esse token.
Tudo assinado com a variável **`PORTAL_TOOL_ACCESS_SECRET`** (a MESMA nos dois lados).

### 2.1 Formato do token (`pn_token`)
```
<payloadB64url>.<assinatura>
```
- `payloadB64url` = base64url( JSON.stringify(payload) )
- `assinatura`   = HMAC_SHA256( payloadB64url, PORTAL_TOOL_ACCESS_SECRET ) em hex
- Payload mínimo:
  ```json
  { "slug": "<slug-da-ferramenta>", "exp": <unix_seconds>, "sub": "<id opcional>", "email": "<opcional>", "iat": <unix_seconds> }
  ```
- Validação (no site): assinatura confere (timing-safe) **E** `slug` == slug da rota **E** `exp` no futuro.

### 2.2 Fluxo servidor (server.js do site)
1. O app redireciona o assinante autenticado para
   `https://ferramentas.portalnotarial.com.br/<pagina>?pn_token=<token>`.
2. O site valida, cria o cookie **`pn_tool_access`** (HttpOnly, SameSite=Lax, Secure,
   `Max-Age = PORTAL_ACCESS_COOKIE_MAX_AGE` = 7200s) e redireciona para a URL limpa.
3. Sem token/cookie válido → redireciona para `PORTAL_APP_URL?origem=<url_atual>`.

### 2.3 Fluxo cliente (guard inline em cada HTML de ferramenta)
- Lê `?pn_token` → guarda em `sessionStorage["pn_tool_token_<slug>"]`.
- Chama **`GET {PORTAL_APP_URL}/api/tool-ticket/verify-get?slug=<slug>&token=<token>`**
  e espera resposta **`{ "ok": true }`**.

### 2.4 Endpoints que o `portal-notarial-app` PRECISA continuar fornecendo
1. **Emissão do `pn_token`**: para o assinante ativo, gerar o token HMAC e redirecionar
   para a ferramenta com `?pn_token=`.
2. **`GET /api/tool-ticket/verify-get?slug=&token=`** → `{ ok: true|false }`
   (valida HMAC + slug + exp).
- Ambos com o MESMO `PORTAL_TOOL_ACCESS_SECRET`.

> Resumindo para a migração: pode trocar Supabase, Stripe, banco e login à vontade —
> **desde que, ao final, o app continue (a) emitindo o `pn_token` e (b) respondendo o
> `verify-get` exatamente como acima.** Se isso mudar, as 10 ferramentas param.

### 2.5 Slugs válidos (têm que bater em todos os lugares)

**Páginas servidas pelo site Node** (`PROTECTED_ROUTES` do `server.js`):
```
aplicador-emolumentos, selo-digital-tjsp, gerador-orcamento, consulta-pep,
competencia-e-notariado, tarifas-conta-notarial, certidao-reprografica,
oficio-comparecimento, oficio-cartorios, oficio-bancos-inventario
```

**Ferramentas standalone (confirmados na migração — o app deve emitir o token com ESTE slug):**
```
itcmd                 -> ITCMD              (HMAC local)   itcmd.portalnotarial.com.br
ganho-de-capital      -> Ganho de Capital   (HMAC local)   ganhodecapital.portalnotarial.com.br
agenda-cartorios      -> Agenda Notarial    (HMAC local)   agenda.portalnotarial.com.br
classificador-arquivos-eletronicos -> Classificador (VERIFY REMOTO) classificadordearquivos.portalnotarial.com.br
```
> ⚠️ O **Classificador** valida por **verify remoto** (chama o `verify-get` do app); os demais
> validam o `pn_token` por **HMAC local**. A Calculadora Avançada foi migrada em sessão própria
> (confirmar o slug dela no repo `calculadoras`). Confirme cada slug com o `PORTAL_TOOL_SLUG` do
> `/etc/default/<tool>` no Contabo antes de emitir.

### 2.6 Variáveis de ambiente do site (para replicar no Contabo)
```
PORT=3000
NODE_ENV=production
PORTAL_AUTH_REQUIRED=True
PORTAL_APP_URL=https://app.portalnotarial.com.br
PORTAL_ACCESS_COOKIE_NAME=pn_tool_access      (default)
PORTAL_ACCESS_COOKIE_MAX_AGE=7200
PORTAL_TOOL_ACCESS_SECRET=<segredo — igual ao do app>
```

---

## 3. O que a sessão do `portal-notarial-app` deve fazer

**Frente B — Supabase → próprio**
- Substituir Supabase por PostgreSQL próprio (`DATABASE_URL`) + auth próprio (sessão/JWT).
- Recriar: **usuários, permissões/RBAC e relatórios** (hoje no Supabase).
- Migrar dados via `pg_dump`/`pg_restore`; senhas bcrypt do `auth.users` podem ser
  reaproveitadas ou forçar redefinição.

**Frente C — Stripe → Mercado Pago**
- Trocar Stripe por Mercado Pago **Assinaturas (preapproval) + webhooks**.
- Fluxo: pagamento aprovado (webhook) → marca assinante ativo → habilita emissão do `pn_token`.
- **Manter assinantes atuais:** Stripe não transfere para o MP → plano de **reautorização**
  (carência + e-mail). Ver Fase 7 do runbook.

**Primeiro passo (sem alterar nada):** mapear onde Supabase e Stripe são usados (arquivos,
tabelas, env vars, webhooks) e propor o plano antes de codar.

---

## 4. URLs cruzadas que o lado das Ferramentas vai ajustar (coordenar)
No repo `ferramentas-notariais`, estes arquivos chamam backends por URL e serão trocados
de `*.onrender.com` para os novos domínios do Contabo:
- `consulta-pep.html`      → `consulta-pep-backend`
- `consulta-selo-digital.html` → `consulta-selo-digital-tjsp`
- `links-uteis.html`       → `pagina-inicial`

---

## 5. Runbook completo
O passo a passo das 7 fases (paralelo + virada) está em `deploy/MIGRACAO.md` (repo
`ferramentas-notariais`). Recomenda-se colá-lo na sessão do app para seguir o mesmo plano.
