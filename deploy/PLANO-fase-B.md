# Plano — Fase B: sair do Supabase e do Stripe (no app `portal-notarial-app`)

**Contexto:** a Fase A (Render → Contabo) está concluída — tudo roda no Contabo por
**lift-and-shift**, com o app ainda usando **Supabase** (auth + dados) e **Stripe** (cobrança).
A Fase B troca esses dois por soluções próprias. É **trabalho de código no repo `portal-notarial-app`**
(feito na sessão dele), não deploy. Fazer **B1 (Supabase→próprio) primeiro, B2 (Stripe→MP) depois**.

> **A favor:** só **2-3 assinantes** (amigos). Migração de dados = poucas linhas; reautorização de
> pagamento = uma mensagem pra cada. Risco baixo — mas ainda assim, testar antes de virar.

---

## Pré-requisitos (uma vez)
- **Postgres no Contabo:** provavelmente já existe (a Calculadora Avançada foi migrada com Postgres
  local). Conferir: `systemctl is-active postgresql` e `sudo -u postgres psql -c "\l"`. Se existir,
  criar um **banco dedicado** ao app (ex.: `portalapp`); se não, instalar o Postgres primeiro.
- **Backup do Supabase antes de tudo:** o Supabase é Postgres por baixo e expõe a connection string
  (painel → Settings → Database). `pg_dump` completo guardado fora do servidor.

---

## B1 — Supabase → Postgres/auth próprio

### 1. Inventário (mapear antes de codar)
No `server.js` do app, listar todo uso de Supabase:
- **Auth:** login, cadastro, sessão/refresh, reset de senha (Supabase Auth / `auth.users`).
- **Dados (PostgREST):** `supabase.from('<tabela>')...` — tabelas de **usuários, assinaturas,
  permissões/RBAC, eventos de uso/relatórios**. Anotar cada tabela e cada query.

### 2. Banco próprio
- Criar o schema espelhando as tabelas do Supabase (mesmas colunas usadas pelo app).
- **Migrar os dados:** `pg_dump` do Supabase → `pg_restore`/`psql` no Postgres do Contabo.
  Com 2-3 usuários, dá pra conferir linha a linha.

### 3. Camada de dados (código)
- Trocar `@supabase/supabase-js` por **`pg`** (node-postgres) com `DATABASE_URL`.
- Reescrever cada `supabase.from(...).select/insert/update/delete` em **SQL**.
- **RLS:** o Supabase aplicava Row Level Security; no Postgres próprio, o app passa a filtrar por
  usuário na query (o app já usa `service_role` hoje, então a maior parte já é server-side).

### 4. Auth própria
- Sessão via cookie assinado ou **JWT próprio**; senhas com **bcrypt**.
- As senhas do `auth.users` do Supabase são bcrypt — **podem ser reaproveitadas** (copiar o hash) ou,
  mais simples com 2-3 users, **forçar redefinição** (e-mail "defina sua nova senha").
- Reset de senha por e-mail (SMTP — mesma convenção das ferramentas).

### 5. NÃO MEXER (contrato de token)
- Manter idênticos: emissão do `pn_token` (HMAC) e `GET /api/tool-ticket/verify-get`.
- ⚠️ O **Classificador** chama o `verify-get` a cada acesso — não pode quebrar.

### 6. Validar (staging `app-teste`)
Login, sessão, painel/assinatura, permissões, relatórios de uso, emissão de token e `verify-get` —
tudo contra o Postgres próprio. Só então remover as env/deps do Supabase.

---

## B2 — Stripe → Mercado Pago (só depois do B1)

### 1. Gate: criar o plano no Mercado Pago
- Conta MP + **Assinatura (preapproval_plan)** com o valor do plano. Guardar `plan_id`.
- Credenciais **sandbox** primeiro (TEST-...), produção só na virada.

### 2. Código
- Trocar Stripe Checkout/Subscriptions por **MP preapproval** (criar assinatura → link de pagamento).
- **Webhook MP** (`/api/mercadopago-webhook`): evento de pagamento aprovado → marca assinante **ativo**
  → habilita emissão do `pn_token`. Validar a assinatura/origem do webhook.
- Mapear estados: ativo / pendente / cancelado / em atraso → mesmo gating que o Stripe fazia.

### 3. Migrar assinantes atuais (reautorização)
- Stripe **não transfere** para o MP. Com 2-3 amigos: mandar o link do MP, dar uma **carência**
  (`grace_until`) pra continuarem acessando enquanto reassinam, e desligar o Stripe quando todos migrarem.

### 4. Validar (sandbox → produção)
- E2E no sandbox: assinar → webhook → vira ativo → token → ferramenta abre.
- Cancelar → perde acesso após carência.
- Só então: credenciais de produção + webhook de produção no painel do MP + desligar o Stripe.

---

## Ordem de virada (resumo)
1. B1 completo e validado em `app-teste` (Postgres próprio no ar, Supabase ainda de reserva).
2. Vira o app pra usar só o Postgres próprio; observa alguns dias; então desativa o projeto Supabase.
3. B2 em sandbox → reautoriza os assinantes no MP → vira produção → desliga o Stripe.

## Riscos a vigiar
- **Cobrança silenciosa:** um webhook malconfigurado não dá erro visível — teste o fluxo de pagamento
  ponta a ponta antes de confiar.
- **Sessões/login:** trocar auth desloga todo mundo — avisar os assinantes.
- **Contrato de token:** qualquer mudança no `verify-get`/HMAC quebra as ferramentas (esp. Classificador).
