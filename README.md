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
