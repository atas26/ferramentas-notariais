# Migração Render → Contabo (Docker) + trocar Supabase e Stripe

Estratégia: **construir tudo em paralelo no Contabo (staging) e virar a chave** (DNS)
só quando o fluxo ponta a ponta estiver testado. Zero downtime, e dá pra voltar atrás.

São 3 frentes independentes:
- **A. Infra:** Render → Contabo com Docker.
- **B. Supabase → próprio:** banco + usuários + permissões + relatórios.
- **C. Stripe → Mercado Pago:** assinatura recorrente.

> Repositórios envolvidos: `ferramentas-notariais` (este, site+guard+backend PEP),
> `portal-notarial-app` (login/assinatura — **aqui vivem Supabase e Stripe**),
> e os backends: calculadoras, itcmd-sp, ganho-de-capital, CPF-RF, agenda-cartorios,
> organizador-de-arquivos, exigencia-imob, consulta-selo-digital-tjsp, pagina-inicial.

---

## Inventário no Render (11 ativos)
| Serviço | Runtime | Repo | Vai virar |
|---|---|---|---|
| ferramentas-notariais | Node (verificar) | este | container `site` |
| consulta-pep-backend | Node | este (`backend/`) | container `consulta-pep` |
| portal-notarial-app | Node | portal-notarial-app | container `portal-app` (sem Supabase/Stripe) |
| calculadoras | Python | ? | container |
| calculadoras-db | PostgreSQL | — | container `db` (consolida com Supabase) |
| CPF-RF | Python | ? | container |
| ganho-de-capital | Python | ? | container |
| itcmd-sp | Python | ? | container |
| agenda-cartorios | Python | ? | container |
| organizador-de-arquivos | Python | ? | container |
| exigencia-imob-portal-notarial | Node | ? | container |
| **(fora dos prints)** consulta-selo-digital-tjsp | Python | ? | localizar (suspenso?) |
| **(fora dos prints)** pagina-inicial | ? | ? | localizar (suspenso?) |

---

## FASE 0 — Preparação (não toca produção)
1. No Contabo: instalar Docker + Docker Compose. Abrir portas 80/443.
2. Clonar os repositórios lado a lado (mesma pasta-mãe).
3. Criar `deploy/.env` (NÃO comitar) com os segredos colhidos do Render:
   ```
   DB_USER=portal
   DB_PASSWORD=<forte>
   DB_NAME=portal
   PORTAL_TOOL_ACCESS_SECRET=<MESMO valor do portal-notarial-app no Render>
   MERCADOPAGO_ACCESS_TOKEN=<sandbox por enquanto>
   ```
4. Subdomínios de **staging** (ex.: `staging-app.portalnotarial.com.br`,
   `staging-ferramentas...`) apontando para o IP do Contabo — para testar antes da virada.

> **Colher segredos:** no painel do Render, em cada serviço → *Environment*.
> Variáveis com `sync:false` (ex.: `PORTAL_TOOL_ACCESS_SECRET`) **só existem lá**.
> **Reative os serviços suspensos rapidinho** só para copiar essas variáveis.

---

## FASE 1 — Banco (Frente B, parte 1)
1. Subir só o Postgres: `docker compose -f deploy/docker-compose.yml up -d db`
2. **Reative o `calculadoras-db` no Render** e exporte:
   ```
   pg_dump "postgres://USER:PASS@HOST:PORT/DB" -Fc -f calculadoras.dump
   ```
3. Exporte o **Postgres do Supabase** (Supabase → Project Settings → Database → Connection string):
   ```
   pg_dump "postgres://...supabase..." -Fc -f supabase.dump
   ```
4. Restaure no banco novo (container `db`):
   ```
   pg_restore -d "postgres://portal:...@localhost:5432/portal" --no-owner calculadoras.dump
   pg_restore -d "postgres://portal:...@localhost:5432/portal" --no-owner supabase.dump
   ```
5. **Usuários/senhas:** o Supabase Auth guarda hashes bcrypt em `auth.users`.
   Dá para (a) reaproveitar os hashes no auth próprio, ou (b) forçar "redefinir senha"
   no primeiro login. Decidir na Frente B.

---

## FASE 2 — Auth próprio (Frente B, parte 2) — no `portal-notarial-app`
1. Remover SDK do Supabase; ler/gravar usuários direto no Postgres (`DATABASE_URL`).
2. Sessão/login próprio (JWT ou cookie de sessão). Recriar **permissões/RBAC**
   (tabela de papéis) e as **queries de relatórios** que hoje usam o Supabase.
3. Manter a emissão do **token de acesso às ferramentas** igual (HMAC com
   `PORTAL_TOOL_ACCESS_SECRET`) — o guard deste repo continua funcionando sem mudança.
4. Testar signup/login/relatórios no staging.

---

## FASE 3 — Mercado Pago (Frente C) — no `portal-notarial-app`
1. Criar aplicação no Mercado Pago; usar **Assinaturas (preapproval)**.
2. Implementar: criar assinatura → redirecionar pro checkout MP → receber **webhook**
   de pagamento aprovado → marcar assinante ativo no banco → liberar emissão do token.
3. Remover Stripe (checkout + webhooks + SDK).
4. Testar com **credenciais de sandbox** do MP (cartões de teste).

---

## FASE 4 — Ferramentas em Docker (Frente A)
1. Criar um `Dockerfile` por serviço (Node: `node:20-alpine`; Python: `python:3.12-slim`
   + `pip install -r requirements.txt`). Para o backend PEP deste repo, criar
   `backend/Dockerfile`.
2. Preencher os blocos comentados em `deploy/docker-compose.yml` (um por serviço).
3. Ajustar as **URLs cruzadas**: nos HTML/JS, trocar `*.onrender.com` pelos novos
   domínios (ex.: `consulta-pep-backend.onrender.com` → `pep.portalnotarial.com.br`).
   Neste repo: `consulta-pep.html`, `consulta-selo-digital.html`, `links-uteis.html`.
4. `docker compose up -d --build` e conferir cada container de pé.

---

## FASE 5 — Teste ponta a ponta (staging)
Fluxo completo, tudo no Contabo:
cadastro → pagar no MP (sandbox) → virar assinante → abrir uma ferramenta
(o guard valida o token) → gerar um PDF/relatório. Só avança se passar 100%.

---

## FASE 6 — Virada (cutover)
1. Janela curta: **congelar** cadastros/pagamentos novos no ambiente antigo.
2. **Último `pg_dump` incremental** do Supabase/Render → restaurar no Contabo.
3. Baixar o **TTL do DNS** (fazer isso 24h antes) e então **apontar os domínios**
   (`app` e `ferramentas`) para o IP do Contabo.
4. Ativar **Mercado Pago em produção**; desativar cobranças do Stripe.
5. Deixar o Render ligado ~48h como rede de segurança; depois desligar.

---

## FASE 7 — Assinantes atuais (⚠️ não é automático)
Assinaturas do **Stripe NÃO migram** para o Mercado Pago — cada cliente precisa
**reautorizar** o pagamento (novo cadastro de cartão/Pix no MP).
1. Extrair a lista de assinantes ativos do Stripe.
2. **Período de carência** (ex.: 30 dias) mantendo o acesso liberado no banco novo.
3. E-mail pedindo para reativar a assinatura pelo novo checkout do MP.
4. Ao fim da carência, quem não reativou perde o acesso.

---

## Checklist rápido de segredos/dados a colher do Render (antes de desligar)
- [ ] `PORTAL_TOOL_ACCESS_SECRET` (e demais env `sync:false`)
- [ ] Connection string do Supabase + dump do banco
- [ ] Dump do `calculadoras-db`
- [ ] Chaves/segredos de cada backend (APIs de terceiros)
- [ ] Qualquer arquivo em disco que não esteja no Git (atenção: disco free = efêmero)
- [ ] Lista de assinantes ativos do Stripe

## LGPD
- `backend/data/pep.csv` (23 MB, dado pessoal): tirar do Git, guardar só no servidor,
  fora da pasta pública. Mesmo cuidado com base de óbito (CPF-RF).
