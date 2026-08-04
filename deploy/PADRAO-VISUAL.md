# Padrão Visual Portal Notarial — guia para uniformizar as páginas internas

Este guia reproduz o visual da **home** (`ferramentas-notariais/index.html`) nas demais páginas
(que vivem em outros repositórios). Cole este arquivo na sessão Claude de cada repositório e peça
para aplicar. As páginas internas são **ferramentas** (formulários/resultados), então aplique
**tokens + tipografia + header + botões + estética clean**; as "faixas de marketing" (hero, faixa
escura) são opcionais — o essencial é a identidade e a limpeza.

---

## 0. Pré-requisito: a fonte Inter (self-hosted)

O site usa **Inter** self-hosted (sem CDN). Copie a pasta `fonts/` do repo `ferramentas-notariais`
para o repo da ferramenta (2 arquivos):
```
fonts/inter-latin-wght-normal.woff2
fonts/inter-latin-wght-italic.woff2
```
E declare no topo do `<style>`:
```css
@font-face{ font-family:"Inter"; font-style:normal; font-weight:100 900; font-display:swap;
  src:url("fonts/inter-latin-wght-normal.woff2") format("woff2"); }
@font-face{ font-family:"Inter"; font-style:italic; font-weight:100 900; font-display:swap;
  src:url("fonts/inter-latin-wght-italic.woff2") format("woff2"); }
```
> Se a ferramenta serve estáticos de outra pasta (ex.: Django `/static/`), ajuste o caminho do `src`.

---

## 1. Tokens (cole no `:root`)

```css
:root{
  --azul:rgb(11,95,255);
  --azul-escuro:rgb(15,57,142);
  --verde:rgb(0,144,157);      /* semântico: "incluído/ok" costuma usar #0f9669 */
  --vermelho:rgb(232,57,70);
  --amarelo:rgb(217,165,30);
  --fundo:#ffffff;
  --fundo-2:#f4f7fb;           /* faixa clara / seções alternadas */
  --texto:#0a2540;
  --texto-2:#183657;
  --texto-suave:rgba(10,37,64,0.74);
  --texto-fraco:rgba(10,37,64,0.54);
  --linha:rgba(10,37,64,0.12); /* hairline (bordas finas, filetes) */
  --branco:#ffffff;
  --sombra:0 24px 80px rgba(10,37,64,0.10);
  --radius-lg:32px; --radius-md:24px;
  font-family:"Inter", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
  text-rendering:optimizeLegibility; font-feature-settings:"cv05" 1,"ss01" 1;
}
body{ margin:0; background:var(--fundo); color:var(--texto); line-height:1.55; }
```

---

## 2. Tipografia

- **Título principal (h1):** `font-weight:800; letter-spacing:-0.028em; line-height:1.05; text-wrap:balance;`
  tamanho fluido `clamp(34px, 4.35vw, 60px)`.
- **Título de seção:** `font-weight:800; letter-spacing:-0.022em; line-height:1.08; text-wrap:balance;`
  `clamp(30px, 3.8vw, 46px)`.
- **Eyebrow (rótulo acima do título):** `font-size:12px; font-weight:800; letter-spacing:0.16em;
  text-transform:uppercase; color:var(--azul);`
- **Texto/lead:** `color:var(--texto-suave); font-size:17px; line-height:1.65; text-wrap:pretty;`
  largura de leitura confortável (`max-width:60ch`).
- Números que se alinham em colunas: `font-variant-numeric:tabular-nums;`

---

## 3. Header / topbar padrão (o mais importante para uniformizar)

**Medidas oficiais:** logo **250px** de largura · barra **~90px** de altura (padding `14px 48px`) ·
fundo branco translúcido · filete embaixo.

**HTML** (copie o bloco do logo — inclusive o `<img>` com o SVG em base64 — de
`ferramentas-notariais/index.html`, dentro de `<nav>`, para manter o logo idêntico):
```html
<header class="site-header">
  <div class="nav-inner">
    <a class="brand site-logo" href="/" aria-label="Portal Notarial - Início">
      <img src="data:image/svg+xml;base64,COLE_O_MESMO_BASE64_DA_HOME" alt="Portal Notarial" width="300" height="73">
    </a>
    <div class="nav-right">
      <div class="primary-links" aria-label="Links principais">
        <a href="/sobre.html">Sobre</a>
        <a href="/contato.html">Contato</a>
        <a href="https://app.portalnotarial.com.br/" class="login-link">Entrar</a>
      </div>
    </div>
  </div>
</header>
```
**CSS:**
```css
.site-header{ position:sticky; top:0; z-index:50; width:100%;
  border-bottom:1px solid var(--linha); background:rgba(255,255,255,0.96); }
.nav-inner{ max-width:1320px; margin:0 auto; padding:14px 48px;
  display:flex; align-items:center; justify-content:space-between; gap:24px; }
.site-logo{ display:inline-flex; align-items:center; flex:0 0 auto; line-height:1; }
.site-logo img{ width:250px; height:auto; display:block; }
.nav-right{ display:flex; align-items:center; justify-content:flex-end; gap:24px; }
.primary-links{ display:flex; align-items:center; gap:16px; color:var(--texto-suave);
  font-size:13px; white-space:nowrap; }
.primary-links a{ color:var(--texto-suave); font-weight:700; padding:8px 0; text-decoration:none; }
.primary-links a:hover{ color:var(--texto); }
.primary-links .login-link{ min-height:38px; display:inline-flex; align-items:center; padding:0 14px;
  border-radius:999px; color:#fff; background:var(--azul); box-shadow:0 14px 34px rgba(11,95,255,0.22); }
.primary-links .login-link:hover{ color:#fff; background:var(--azul-escuro); }
@media (max-width:760px){ .nav-inner{ padding:12px 16px; } .site-logo img{ width:200px; } }
```

---

## 4. Botões

```css
.button{ min-height:50px; display:inline-flex; align-items:center; justify-content:center;
  padding:0 18px; border-radius:15px; border:1px solid var(--linha); background:#fff; color:var(--texto);
  font-size:14px; font-weight:800; text-decoration:none;
  transition:transform .18s ease, box-shadow .18s ease, background .18s ease; }
.button:hover{ transform:translateY(-1px); box-shadow:0 18px 40px rgba(10,37,64,0.10); }
.button.primary{ color:#fff; border-color:var(--azul); background:var(--azul);
  box-shadow:0 18px 38px rgba(11,95,255,0.24); }
.button.primary:hover{ background:var(--azul-escuro); }
```
Pílula (CTA/topbar): `border-radius:999px`. Preço em destaque: **cor azul** (`color:var(--azul)`).

---

## 5. Estética clean (o "espírito" da home) — aplicar nas ferramentas

1. **Nada de caixotões.** Evite cards com sombra pesada e fundo cinza. Prefira **fundo transparente
   + borda hairline** (`border:1px solid var(--linha)`), ou **sem borda** com respiro.
   ```css
   .card{ background:transparent; border:1px solid var(--linha); border-radius:18px; padding:22px;
     box-shadow:none; transition:border-color .2s, background .2s, transform .2s; }
   .card:hover{ transform:translateY(-2px); border-color:rgba(11,95,255,.45); background:rgba(11,95,255,.045); }
   ```
2. **Seções separadas por filete ou por faixa de cor**, não por bordas de caixa.
   - Filete: `border-top:1px solid var(--linha)` entre blocos.
   - Faixa (opcional): fundo `#f5f7fb` alternando com branco; e uma faixa **escura** de destaque
     (`background:radial-gradient(120% 120% at 80% 0%, #12325a, #0a1a2f 58%)`, texto branco) quando fizer sentido.
3. **Cabeçalho de bloco centralizado** (eyebrow + título + subtítulo), muito respiro (padding vertical 72–92px).
4. **Respiro e largura de leitura**: títulos `max-width:22ch`, textos `max-width:60ch`, centralizados com `margin:0 auto`.
5. **Formulários (o que mais aparece nas ferramentas):** campos com borda hairline, `border-radius:12–14px`,
   foco visível em azul (`box-shadow:0 0 0 3px rgba(11,95,255,.18)`), rótulos em `font-weight:700`.

---

## 6. Cores de estado (semânticas — separadas do azul de marca)

- **Incluído / sucesso:** verde `#0f9669` (ex.: pílula "Incluído no plano" com bolinha).
- **Alerta:** amarelo `#d9a51e`. **Erro:** vermelho `#e83946`.
- Use estas **só** para status; o **azul** (`--azul`) é o destaque/marca.

---

## 7. Rodapé (padrão)

Filete no topo, texto `--texto-fraco`, links de Sobre/Contato/Termos/Privacidade/Aviso legal.
```css
footer{ border-top:1px solid var(--linha); padding:26px 0; font-size:12.5px; color:var(--texto-fraco); }
```

---

## 8. Checklist por página interna
- [ ] Fonte Inter self-hosted (pasta `fonts/` + `@font-face`), caminho ajustado ao servidor de estáticos.
- [ ] Tokens `:root` colados; `body` com fundo/cor/`line-height`.
- [ ] Header padrão (logo 250px, barra ~90px, nav Sobre/Contato + botão **Entrar** azul).
- [ ] Tipografia (h1/título/eyebrow/lead) conforme item 2.
- [ ] Botões conforme item 4; preço em azul.
- [ ] Estética clean: sem caixotões; hairlines/filetes; respiro; leitura confortável.
- [ ] Cores de estado só para status.
- [ ] Rodapé padrão.
- [ ] Testar responsivo (mobile: logo 200px, padding lateral menor).

---

## 9. Prompt pronto (cole na sessão de cada repositório da ferramenta)
> Aplique o **Padrão Visual Portal Notarial** nesta página, seguindo o guia `deploy/PADRAO-VISUAL.md`
> (que vou colar). Mantenha a funcionalidade intacta. Passos: (1) copiar a pasta `fonts/` e declarar
> `@font-face` do Inter; (2) colar os tokens `:root` e ajustar o `body`; (3) trocar o header pelo padrão
> (logo 250px, barra ~90px, nav Sobre/Contato + botão Entrar azul, usando o MESMO SVG do logo da home);
> (4) aplicar a tipografia (h1/título/eyebrow/lead) e os botões; (5) deixar a estética clean — remover
> caixotões/sombras pesadas, usar borda hairline e filetes, dar respiro; (6) preço/CTA em azul; cores de
> estado (verde/amarelo/vermelho) só para status. Não invente logo próprio — use o SVG do Portal Notarial.
