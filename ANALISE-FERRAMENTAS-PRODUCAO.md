# Análise das Ferramentas em Produção — Portal Notarial Pro

**Data:** 2026-06-24
**Escopo:** 11 ferramentas interativas + 2 backends Node + camada de proteção/infra.
**Método:** revisão estática arquivo a arquivo, com foco em produção (correção de cálculos com dinheiro real, bugs, segurança, LGPD, dependências externas e infraestrutura).

---

## Sumário executivo

A base de código é, em geral, **bem estruturada e cuidadosa com XSS** (uso consistente de `escapeHtml`/`textContent`). Os problemas mais graves não são de estilo, são de **correção financeira** e **conformidade/segurança de dados pessoais** — exatamente o que importa numa ferramenta notarial em produção.

### Os 5 pontos que exigem ação imediata

| # | Gravidade | Ferramenta | Problema |
|---|-----------|------------|----------|
| 1 | 🔴 Crítico | aplicador-de-emolumentos | "Gap de centavos" joga bases fracionárias (usufruto, hipoteca dividida, servidão) para a **faixa máxima (R$ 65.637,95)** — erro de até ~3.300%. |
| 2 | 🔴 Crítico | gerador-de-orcamentos | **Faixa "G" ausente** na tabela de escritura: imóveis de ~R$ 77 mil a ~R$ 115 mil são **superfaturados** (caem na faixa H). |
| 3 | 🔴 Crítico | consulta-pep (backend) | Backend **sem autenticação real** + **PII/LGPD**: CPF→nome→cargo expostos por API pública; `pep.csv` (23,9 MB) versionado no git. |
| 4 | 🟠 Alto | calculadora-tarifas | Mesmo padrão de gap: valores fora de faixa caem no **fallback da faixa mais cara**. |
| 5 | 🟠 Alto | **todas** | Tabelas de emolumentos "base 2026" hardcoded **sem governança de atualização** (obsolescência silenciosa todo ano) + **CDNs sem SRI**. |

---

## Achados transversais (afetam várias ferramentas)

### A) Bug de "gap de faixa" — padrão recorrente e perigoso
A lógica de enquadramento por faixa (`localizarFaixa`/`buscaFaixa`) compara apenas `valor <= item.ate`, ignorando o limite inferior. Como as faixas são contíguas com passo de R$ 0,01, **qualquer valor fracionário entre os centavos não casa com nenhuma faixa** e cai no fallback — que é a **última (mais cara) faixa**.

- **aplicador-de-emolumentos**: catastrófico — bases fracionárias são geradas pelo próprio código (usufruto = valor×2/3, hipoteca/qtd, servidão×0,20).
- **gerador-de-orcamentos**: agravado por um **buraco real** na tabela (faixa G ausente).
- **calculadora-tarifas-conta-notarial**: valores de lacuna caem na faixa 11 (a mais cara).
- **calculadora-escritura**: frágil pelo mesmo motivo, mas atualmente correto para valores em centavos.

**Correção recomendada (todas):** arredondar a base a 2 casas antes da busca; tratar `NaN` como erro explícito (não como fallback); adicionar *assert* de continuidade das tabelas (`tabela[i].de === tabela[i-1].ate + 0.01`).

### B) Tabelas hardcoded "2026" sem mecanismo de atualização
Os emolumentos de SP (Lei 11.331/2002) são reajustados anualmente. Estando embutidos no HTML, as calculadoras **ficam incorretas silenciosamente** todo início de ano. Recomenda-se: exibir data de vigência ao usuário, externalizar os valores para arquivo de dados versionado e criar rotina/lembrete anual.

### C) CDNs sem Subresource Integrity (SRI)
**Nenhum** `<script>`/fonte externo tem `integrity`. Pior caso: a fonte Carlito vem de `cdn.jsdelivr.net/gh/google/fonts@main` (branch móvel) nos geradores de PDF. Comprometimento de CDN = execução de JS arbitrário em ferramentas que manipulam documentos oficiais. Adicionar SRI + `crossorigin`, fixar versões/commits e, idealmente, auto-hospedar libs críticas (pdf-lib, fontkit, React).

### D) API de gate como ponto único de falha
Todas as ferramentas validam `pn_token` contra `app.portalnotarial.com.br/api/tool-ticket/verify-get` antes de exibir o conteúdo. Se essa API cair/lentificar, **a ferramenta fica inacessível** (fallback redireciona para fora após 8s) — mesmo as calculadoras que rodam 100% offline. Degradar graciosamente.

### E) Proteção é só "de entrega", contornável
O conteúdo é HTML estático. Após o gate, todo o HTML (lógica + dados embutidos) vai ao browser e pode ser salvo/redistribuído. O `pn_token` na URL é vulnerável a **replay** (sem nonce/jti) e vaza por logs/Referer antes do 302 que o remove. Dados realmente sensíveis precisam ficar server-side atrás de API autenticada.

### F) Peso de arquivos + `Cache-Control: no-store` em tudo
- `gerador-certidao-reprografica.html` = 1,26 MB (≈1,14 MB são duas fontes em base64).
- `oficios-bancos/index.html` (389 KB) e `oficios-outros-cartorios.html` (312 KB) = logo PNG em base64.

Com `no-store` aplicado a **todos** os estáticos (`server.js:207-214`), esse peso **retrafega a cada page-load**. Aplicar `no-store` só às rotas protegidas; servir assets com cache longo; externalizar fontes/logos.

---

## Análise por ferramenta

### 1. aplicador-de-emolumentos.html 🔴
Calculadora da Tabela I dos Tabelionatos de Notas/SP (base 2026), motor 100% local, XSS-safe.
- 🔴 **Gap de centavos → faixa máxima** (`:2622-2625`). Ex.: doação de imóvel R$ 100k com usufruto → base 66.666,66… → cobra R$ 65.637,95 em vez de ~R$ 1.907,60.
- 🟠 `NaN` também cai na faixa máxima (entrada inválida em multiplicações).
- 🟠 `parseBR` (`:2591`) ambíguo com ponto; só campos com máscara estão protegidos.
- 🟡 Soma de subtotais em float (arredondar por linha antes de somar); sem validação de base > 0; tabelas 2026 a conferir contra a norma oficial.
- 🟡 SRI/CSP ausentes; dependência da API de gate no caminho crítico.

### 2. gerador-de-orcamentos-notariais.html 🔴
Orçamento de escritura + tributo + registro; **PDF gerado em JS puro (sem libs)** — risco de CDN baixo.
- 🔴 **Faixa G ausente** em `TABELA_ESCRITURA` (`:2649-2650`): R$ 76.840,01–115.260,00 cai na H → superfaturamento.
- 🔴 Falta *assert* de continuidade das tabelas.
- 🟡 Tributo não arredondado antes de somar; `src` de logo não escapado em `innerHTML` (`:3526`,`:3568` — self-XSS, baixo); larguras de texto no PDF aproximadas.
- 🟢 Parsing BR correto, XSS tratado, funciona offline.

### 3. calculadora-escritura-tributo-registro-sp.html 🟠
Escritura + ITBI/ITCMD + registro.
- 🟠 Lógica de faixa ignora `de` (frágil, hoje correto); ITCMD fixo em 4% hardcoded (correto hoje em SP, mas sem aviso de revisão; não distingue base = valor venal de referência).
- 🟡 `parseMoeda` interpreta ponto como milhar (colagem de "1234.56" → erro 100×); validação visível ausente (o `#statusCalculo` existe mas é sempre limpo); aceita negativos.
- 🟢 Usa `escapeHtml`.

### 4. calculadora-tarifas-conta-notarial.html 🟠
Tarifa de conta notarial (11 faixas, vigência 01/04/2026).
- 🟠 Gap de 1 centavo entre faixas → fallback para a **faixa 11 (mais cara)**.
- 🟠 **Não funciona standalone**: depende em runtime da API `verify-get`; se cair, calculadora 100% inacessível (tela "Validando acesso…" até 8s).
- 🟢 Sem `innerHTML` (saída via `textContent`), sem XSS.

### 5. consulta-selo-digital.html 🟢/🟠
Validação de Selo Digital do TJSP. Leitura local de QR (pdf.js/jsQR/BarcodeDetector) + OCR (Tesseract); scraping delegado a backend próprio (`consulta-selo-digital-tjsp.onrender.com`) — **evita CORS corretamente**.
- 🟠 SRI ausente nas libs de processamento (jsdelivr); backend Render = ponto único, sem timeout no `fetch`.
- 🟡 **Auto-corrige silenciosamente o dígito verificador** lido por OCR (`:1591`) — pode validar selo errado; `href` vindo do backend não revalidado com `validarUrlOficial`; Tesseract em `@5` (tag flutuante); `validarUrlOficial` acoplado ao path atual do TJSP.
- 🟢 `textContent` em todas as inserções externas; validação estrita de host/URL; bom tratamento de erro e do caminho CAPTCHA.

### 6. consulta-pep.html + backend/server.js 🔴
Consulta PEP por CPF contra base do Siscoaf. Frontend chama `consulta-pep-backend.onrender.com`.
- 🔴 **Backend sem autenticação** — o guard é só client-side; qualquer um chama a API direto. PII exposta.
- 🔴 **LGPD**: sem base legal documentada, sem log de auditoria, sem minimização (retorna todos os campos). `pep.csv` (23,9 MB, 207k linhas) **versionado no git** (PII no histórico).
- 🔴 **Deploy não versionado**: o `render.yaml` deste repo implanta o servidor de proteção da raiz, **não** o backend PEP — config (CORS, rate limit) fora de IaC.
- 🟠 Risco de **OOM** no plano free (512 MB) ao carregar o índice em memória; cold start recarrega 23,9 MB → 503 nas primeiras chamadas.
- 🟠 Enumeração de CPF viável (rate limit 60/min/IP insuficiente); padding de zeros à esquerda "reconstrói" CPFs curtos de forma incorreta e perigosa.
- 🟡 CORS duplicado/conflitante e retorna `*` quando falta `Origin`; `/debug-base` e `/` vazam path absoluto, `baseErro`, contagens; `pagina` aceito mas ignorado (paginação fake).

### 7. competencia-e-notariado.html 🟢/🟠
Árvore de decisão (wizard) React (via `createElement`) sobre competência notarial do e-Notariado (Prov. CNJ 149/2023). Base jurídica hardcoded, bem citada e com avisos interpretativos honestos.
- 🟠 React/ReactDOM de `unpkg.com` **sem SRI** (registry comunitário, sem SLA); gate de API como ponto único.
- 🟡 **Botão "Voltar" não implementado** — `voltar()` existe (`:2038`) mas nenhum botão o chama; usuário só pode reiniciar do zero. Bastante **código morto** (`reiniciar()`, blocos `false &&`, `passos`/`totalEstimado`, `excertoAberto`).
- 🟢 Sem XSS (input só por botões; `innerHTML` apenas com strings estáticas).

### 8. gerador-certidao-reprografica.html 🟠
Certidão reprográfica em PDF/A-2b (pdf-lib + fontkit). XSS mitigado (`escaparHtml`).
- 🟠 **1,2 MB** = duas fontes Carlito em base64 (~1,14 MB) que só são usadas ao gerar PDF — trafegam a cada page-load (com `no-store`); ainda baixadas 2× (CDN p/ preview + base64 p/ PDF). SRI ausente; Carlito em `@main`.
- 🟠 **Download vs Impressão divergem**: `gerarPdfFinal` chama `montarPdfFinal(false)` (sem timbre) e `imprimirPdfFinal` usa o template — quase certamente não intencional.
- 🟡 `window.open`+`onload→print` pode não disparar; edição manual perde negrito/assinatura gráfica; `ignoreEncryption:true` silencioso; código morto (`URL_FONTE_CARLITO_*`).

### 9. oficios-comparecimento / oficios-outros-cartorios / oficios-bancos 🟠
Geradores de ofícios (pdf-lib + fontkit; bancos usa PDF.js + Tesseract/OCR). Mesma engine, muito duplicada.
- 🟠 **Duplicação massiva** da engine (PDF/print/template/validação) entre os 3 → consolidar em `oficios-core.js`/`oficios-base.css`.
- 🟠 Logo em **base64** infla outros-cartorios (312 KB) e bancos (389 KB); comparecimento já usa `<img src>` (faça igual nos outros).
- 🟠 SRI ausente em 4+ CDNs (pdf-lib, fontkit, PDF.js, Tesseract, Carlito `@main`); gate como ponto único.
- 🟡 PDF pode sair com placeholders `[CAMPO]` (validar saída, não só `required`); sem validações semânticas (`horaFim ≥ horaInicio`, óbito não futuro); `quebrarTexto` não trata palavra maior que a largura; edição manual perde negrito no comparecimento (bancos faz melhor); OCR autopreenche campos sem sinalizar baixa confiança.
- 🟢 `escaparHtml` presente (essencial — manter em qualquer refactor); datas sem bug de fuso; CPF com dígito verificador.

### 10. server.js (proteção) + render.yaml + infra 🟠
HMAC-SHA256 token→cookie. Pontos bons: segredo fora do repo, `timingSafeEqual`, cookie `HttpOnly`+`SameSite=Lax`, `x-powered-by` off.
- 🟠 Proteção é só "de entrega" (ver achado E); **replay de `pn_token`** (sem nonce/jti); token vaza por URL/Referer.
- 🟡 `/api/portal-protection-health` expõe a lista de rotas protegidas; cookie sem prefixo `__Host-`/`trust proxy`; **fail-open** se env desligar a proteção; sem `helmet`/CSP/HSTS.
- 🟡 Render free (cold start), `no-store` global (banda), `autoDeploy` direto p/ produção sem CI, `npm install` (não `npm ci`).
- 🟢 `sitemap.xml` não expõe ferramentas pagas. Sugestão: `Disallow` explícito das rotas protegidas no `robots.txt`.

---

## Status das correções aplicadas (esta branch)

### ✅ Corrigido e validado
- **Cálculo por faixa (dinheiro real)** — `aplicador`, `gerador-orcamentos`, `calc-tarifas`, `calc-escritura`: faixa G inserida no gerador (R$ 2.264,49, confirmada por referência cruzada); lógica de teto + arredondamento a centavos + guarda de NaN/negativo. Validado com testes.
- **competencia** — botão "Voltar" habilitado (perguntas e resultado); código morto removido.
- **server.js** — health-check não vaza rotas; `trust proxy` + cookie `Secure` em produção; cache escopado (assets cacheáveis, conteúdo protegido `no-store`). Fluxo de proteção testado.
- **pep-backend** — removido `/debug-base`; `/` e erros 500 não vazam caminho/exceção interna.
- **certidao** — download e impressão agora idênticos (ambos aplicam o timbre); código morto removido.
- **selo-digital** — `href` do link oficial revalidado (`urlOficialSegura`) contra `javascript:`/host externo.
- **oficios** — validações de hora (comparecimento) e data de óbito (bancos).

### ✅ Corrigido e validado (2ª rodada)
- **SRI** — `integrity`+`crossorigin` nas libs fixadas (pdf-lib, fontkit, jsQR, react, react-dom); hashes computados dos tarballs oficiais do npm.
- **PEP — autenticação server-side** — validação de token HMAC no backend, *gated* por `PEP_AUTH_REQUIRED` (default off, para não derrubar produção); frontend encaminha o token. Ativação requer setar a env no serviço PEP.
- **Redução de peso** — logos base64 dos ofícios externalizados (outros-cartórios 381→70 KB; bancos 511→123 KB) e fontes Carlito da certidão externalizadas (1,26 MB→160 KB). Todos cacheáveis.

### ⏳ Pendente — exige DECISÃO sua
1. **PEP — remover `pep.csv` do git + purgar histórico** — destrutivo e dependente da infra do serviço PEP (se ele faz deploy a partir do git, removê-lo quebra a base). Precisa da sua confirmação e do plano de provisionamento do CSV.
2. **PEP — ativar a auth** — setar `PEP_AUTH_REQUIRED=true` e `PORTAL_TOOL_ACCESS_SECRET` no serviço do backend PEP; + base legal/log de auditoria/minimização (LGPD).
3. **selo-digital — auto-correção silenciosa do dígito verificador no OCR** — já existe um gate de confirmação manual; mudar isso altera o comportamento da conferência. **Recomendo** tornar o aviso mais enfático em vez de remover. Aguardo sua decisão.

### ⏳ Pendente — refatoração/governança (sem urgência)
4. **Tesseract `@5` e Carlito `@main`** — fixar versão antes de aplicar SRI (sub-recursos dinâmicos).
5. **Governança das tabelas 2026** — exibir vigência + processo de atualização anual + externalizar valores.
6. **Consolidar a engine duplicada dos 3 ofícios** (`oficios-core.js`).
7. **PEP — anti-enumeração** (rate limit por token + CAPTCHA) e **CSP** nas páginas com scripts de terceiros.

---

## Plano de ação sugerido (ordem de prioridade)

1. **Corrigir os bugs de faixa (dinheiro real)** — aplicador, gerador-de-orcamentos (faixa G), tarifas: arredondar base, tratar NaN, assert de continuidade. **Antes de qualquer outra coisa.**
2. **Backend PEP / LGPD** — autenticar server-side, remover `pep.csv` do git e purgar histórico, log de auditoria, minimização, versionar a IaC.
3. **Governança das tabelas 2026** — vigência visível + processo de atualização anual + externalizar dados.
4. **SRI + fixar versões** em todas as CDNs; auto-hospedar libs críticas.
5. **Reduzir peso** — externalizar fontes (certidão) e logos (ofícios); `no-store` só nas rotas protegidas.
6. **Resiliência do gate** — degradar graciosamente quando a API de verificação cair.
7. **Limpezas** — código morto (competência), botão Voltar, download vs impressão (certidão), consolidar engine dos ofícios.
