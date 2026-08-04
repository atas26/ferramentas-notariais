# Handoff — do repositório `ferramentas-notariais` para a sessão do `portal-notarial-app`

Este documento é o **mapeamento feito pelo lado das Ferramentas** para orientar a
migração (Render → Contabo) e a troca de **Supabase → próprio** e **Stripe → Mercado Pago**,
que serão implementadas no repositório `portal-notarial-app`.

O ponto mais importante está na seção **"CONTRATO DE INTEGRAÇÃO"**: é o que o app usa
para liberar o acesso às ferramentas. **Isso não pode quebrar na migração.**

---

## 0. STATUS ATUAL (atualizado — leia primeiro)

**MIGRAÇÃO CONCLUÍDA (31/07/2026).** Todas as ferramentas, o site **e o app** já estão no
Contabo, em produção. O Render foi **suspenso** (fora as 3 ferramentas paradas). O app foi
migrado por **lift-and-shift (opção A)**: saiu do Render **mantendo Supabase + Stripe**.

### App no Contabo — como está e cuidados
- **Local:** `/home/fernando/portal-app` · **serviço:** `portal-app.service` (systemd) ·
  **porta:** `127.0.0.1:8091` (atrás do Apache, vhost `app.conf`/`app-le-ssl.conf`) ·
  **domínio:** `app.portalnotarial.com.br` (A → 89.117.73.91).
- **Node 22** foi necessário: o `@supabase/supabase-js` (realtime) exige **WebSocket nativo**,
  que só existe no Node ≥ 22 (no Node 20 o boot quebra com "Node.js 20 detected without native WebSocket").
- **Patches:** o `package.json start` roda 16 `scripts/apply-*-patch.mjs` que **editam o `server.js`
  a cada boot**. Rodar isso em loop **corrompe o `server.js`** (um patch não é idempotente). Por isso
  o systemd roda **`node server.js` direto**, com os 16 patches aplicados **UMA vez** na instalação.
  ⚠️ **Se atualizar o app (`git pull`): `git checkout -- server.js`, reaplicar os 16 patches na ordem
  do `start`, reaplicar o bind `127.0.0.1` (`sed`), e só então reiniciar.**
- **Bind travado em `127.0.0.1`** (edição local no `server.js`: `app.listen(PORT, '127.0.0.1', ...)`)
  para não expor a porta publicamente. Idealmente virar suporte a `HOST` no repo do app.
- **Env:** `/etc/default/portal-app` (640 root:fernando) — Supabase + Stripe + `PORTAL_TOOL_ACCESS_SECRET`
  (o mesmo do hub) + `PORTAL_TOOL_ALLOWED_ORIGINS` com os domínios novos. `APP_URL=https://app.portalnotarial.com.br`.
- **Stripe webhook:** `https://app.portalnotarial.com.br/api/stripe-webhook` — como o domínio não mudou,
  o Stripe já entrega no Contabo (nenhuma mudança no painel do Stripe).

### O que AINDA falta (projeto B — dedicado, sem pressa)
Trocar **Supabase → Postgres/auth próprio** e **Stripe → Mercado Pago** (preapproval + webhooks).
Isso é reescrita de código no repo do app (não estava feito — o código ainda é Supabase+Stripe).
Fazer com gates: plano no MP, E2E sandbox, `pg_dump` do Supabase, reautorização dos assinantes.

### Domínios já no Contabo (89.117.73.91) — tudo em produção
- `app.portalnotarial.com.br` (**o hub** — este app)
- `itcmd.portalnotarial.com.br` (ITCMD) · `ganhodecapital.portalnotarial.com.br` (Ganho)
- `classificadordearquivos.portalnotarial.com.br` (Classificador) · `agenda.portalnotarial.com.br` (Agenda)
- `calculadora.portalnotarial.com.br` (Calculadora Avançada)
- **Site:** `portalnotarial.com.br` (apex) + `www` + `ferramentas` → Node no Contabo, **guard ativo**
- Padrão do servidor: **Apache + Gunicorn/Node (socket ou porta local) + certbot**. Redis já ativo. Sem Docker.
- Segredo `PORTAL_TOOL_ACCESS_SECRET` idêntico no app e em todas as ferramentas.

**Ainda no Render (suspensos, migração futura):** `cpf-rf`, `triagem`, `verificador`, e o backend
da Consulta PEP (`backend/` deste repo, com `pep.csv`/LGPD).

### ⚠️ Dependências que não podem quebrar (valem pra sempre)
1. **O Classificador faz VERIFY REMOTO** em `https://app.portalnotarial.com.br/api/tool-ticket/verify-get`
   a cada acesso. Se esse endpoint sair do ar ou mudar de contrato, **o Classificador para na hora**.
   Mantenha o endpoint e o segredo idênticos em qualquer mudança futura (inclusive no projeto B).
2. Todas as ferramentas dependem do app emitir o `pn_token` — se o app cair, nada abre.

### Receita de deploy já validada (no repo `ferramentas-notariais`)
- `deploy/RECEITA-site-node.md` (Node) e `deploy/RECEITA-tool-python.md` (Django/Gunicorn). O app seguiu
  o molde do site Node (systemd + Apache `ProxyPass` p/ porta local + `X-Forwarded-Proto https` + certbot),
  com os cuidados extras da Seção "App no Contabo" acima (Node 22, patches uma vez, bind 127.0.0.1).

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
