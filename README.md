# portalnotarial.com.br

## Proteção Portal Notarial Pro

Esta versão cria um servidor Node/Express para proteger páginas específicas do site público:

```txt
/aplicador-de-emolumentos.html
/consulta-selo-digital.html
/gerador-de-orcamentos-notariais.html
```

Variáveis obrigatórias no Render:

```txt
PORTAL_AUTH_REQUIRED=True
PORTAL_APP_URL=https://app.portalnotarial.com.br
PORTAL_TOOL_ACCESS_SECRET=mesmo_valor_do_portal_notarial_app
PORTAL_ACCESS_COOKIE_MAX_AGE=7200
```

Importante: o bloqueio real só funciona se o domínio `portalnotarial.com.br` passar por este servidor Node. Se o domínio continuar servido como site estático sem backend, HTML estático não consegue impedir acesso direto de forma segura.


## Proteção Portal Notarial Pro v2

Além das três páginas já protegidas na versão anterior, esta versão inclui:

```txt
/consulta-pep.html
/competencia-e-notariado.html
/calculadora-tarifas-conta-notarial.html
/gerador-certidao-reprografica.html
/oficios-comparecimento.html
/oficios-outros-cartorios.html
/oficios-bancos/
```

Variáveis obrigatórias no Render:

```txt
PORTAL_AUTH_REQUIRED=True
PORTAL_APP_URL=https://app.portalnotarial.com.br
PORTAL_TOOL_ACCESS_SECRET=mesmo_valor_do_portal_notarial_app
PORTAL_ACCESS_COOKIE_MAX_AGE=7200
```


## Proteção Portal Notarial Pro v3

Esta versão mantém as rotas protegidas da v2 e ajusta a Home pública para produção:

- separa páginas públicas e Portal Notarial Pro;
- move as 15 ferramentas protegidas para o bloco Pro;
- deixa a Home com foco em assinatura e consulta normativa pública;
- atualiza `mapa-do-site.html`;
- atualiza `sitemap.xml` para listar apenas páginas públicas;
- preserva o backend Node/Express e as rotas protegidas já validadas.
