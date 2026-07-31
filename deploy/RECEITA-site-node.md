# Receita — migrar o site Node (este repo, `ferramentas-notariais`) para o Contabo

Validada em **30/07/2026** (staging `ferramentas-teste.portalnotarial.com.br`). O site é Express
(`server.js`, `node server.js`), serve as páginas estáticas + o **guard do `pn_token`** (protege as
rotas em `PROTECTED_ROUTES`, incluindo a **Tarifas da Conta Notarial**). Padrão do Contabo:
**Apache + Node (porta TCP local) + certbot** — não Docker.

## Variáveis
```
DOMINIO_PROD=ferramentas.portalnotarial.com.br
SUB=ferramentas-teste.portalnotarial.com.br     # staging
DIR=/home/fernando/ferramentas
PORT=8090                                        # TCP local (só via Apache)
SVC=ferramentas
```

## 0) DNS (staging)
Registro **A**: `SUB` → **89.117.73.91**. (Se o certbot der NXDOMAIN, o DNS ainda não propagou —
`dig +short SUB` até aparecer o IP.)

## 1) Node 20 LTS (uma vez no servidor)
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node -v && npm -v      # espera v20.x / 10.x
```

## 2) Clonar + deps
```bash
cd /home/fernando
git clone -b main https://github.com/atas26/ferramentas-notariais.git ferramentas   # staging usou o branch da migração
cd ferramentas
npm install --omit=dev
```
> O `server.js` respeita `HOST` (bind em `127.0.0.1`) — ajuste introduzido para não expor a porta
> publicamente. Em produção final, clonar de `main` (após o merge).

## 3) Ambiente
```bash
sudo nano /etc/default/ferramentas
```
```
NODE_ENV=production
HOST=127.0.0.1
PORT=8090
PORTAL_AUTH_REQUIRED=True
PORTAL_APP_URL=https://app.portalnotarial.com.br
PORTAL_ACCESS_COOKIE_NAME=pn_tool_access
PORTAL_ACCESS_COOKIE_MAX_AGE=7200
PORTAL_TOOL_ACCESS_SECRET=<o MESMO do hub — copie de /etc/default/itcmd>
```
```bash
sudo chmod 640 /etc/default/ferramentas
sudo chown root:fernando /etc/default/ferramentas
```
> ⚠️ Sem o `PORTAL_TOOL_ACCESS_SECRET` correto, o guard redireciona tudo (302) mas **nenhum token
> é aceito**. Confirme que é idêntico ao do ITCMD:
> `diff <(sudo sed -n 's/^PORTAL_TOOL_ACCESS_SECRET=//p' /etc/default/ferramentas) <(sudo sed -n 's/^PORTAL_TOOL_ACCESS_SECRET=//p' /etc/default/itcmd)`

## 4) systemd
```bash
sudo tee /etc/systemd/system/ferramentas.service > /dev/null <<'EOF'
[Unit]
Description=node server (site Portal Notarial - ferramentas)
After=network.target

[Service]
User=fernando
Group=www-data
WorkingDirectory=/home/fernando/ferramentas
EnvironmentFile=/etc/default/ferramentas
ExecStart=/usr/bin/node server.js
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now ferramentas
sleep 3
sudo systemctl status ferramentas --no-pager | head -8
sudo ss -lntp | grep 8090                                   # deve escutar em 127.0.0.1:8090
curl -sS http://127.0.0.1:8090/api/portal-protection-health # {"ok":true,...}
```

## 5) Apache :80 (ACME + redirect) + certbot
```bash
sudo tee /etc/apache2/sites-available/ferramentas-teste.conf > /dev/null <<'EOF'
<VirtualHost *:80>
    ServerName ferramentas-teste.portalnotarial.com.br
    Alias /.well-known/acme-challenge/ /var/www/letsencrypt/.well-known/acme-challenge/
    <Directory /var/www/letsencrypt/.well-known/acme-challenge/>
        Require all granted
    </Directory>
    RewriteEngine On
    RewriteCond %{REQUEST_URI} !^/\.well-known/acme-challenge/
    RewriteRule ^ https://ferramentas-teste.portalnotarial.com.br%{REQUEST_URI} [R=301,L,NE]
</VirtualHost>
EOF
sudo a2ensite ferramentas-teste.conf
sudo apache2ctl configtest && sudo systemctl reload apache2
sudo certbot certonly --webroot -w /var/www/letsencrypt -d ferramentas-teste.portalnotarial.com.br
```

## 6) Apache :443 (SSL + proxy pra porta TCP)
```bash
sudo tee /etc/apache2/sites-available/ferramentas-teste-le-ssl.conf > /dev/null <<'EOF'
<IfModule mod_ssl.c>
<VirtualHost *:443>
    ServerName ferramentas-teste.portalnotarial.com.br
    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/ferramentas-teste.portalnotarial.com.br/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/ferramentas-teste.portalnotarial.com.br/privkey.pem
    Include /etc/letsencrypt/options-ssl-apache.conf
    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"
    ProxyPass / http://127.0.0.1:8090/ timeout=120 keepalive=On
    ProxyPassReverse / http://127.0.0.1:8090/
</VirtualHost>
</IfModule>
EOF
sudo a2ensite ferramentas-teste-le-ssl.conf
sudo apache2ctl configtest && sudo systemctl reload apache2
curl -sS -o /dev/null -w "%{http_code}\n" https://SUB/                                  # 200 (home)
curl -sS -o /dev/null -w "%{http_code}\n" https://SUB/calculadora-tarifas-conta-notarial.html  # 302 (protegida)
```
> `RequestHeader set X-Forwarded-Proto "https"` é essencial: o `server.js` usa isso (com
> `trust proxy`) pra marcar o cookie como `Secure` e reconhecer o HTTPS real.

## 7) Prova ponta a ponta (token da Tarifas, slug `tarifas-conta-notarial`)
```bash
URL=$(python3 - <<'PY'
import json, base64, hmac, hashlib, time
secret=None
for line in open("/etc/default/ferramentas"):
    if line.startswith("PORTAL_TOOL_ACCESS_SECRET="):
        secret=line.split("=",1)[1].strip().encode(); break
now=int(time.time())
payload={"slug":"tarifas-conta-notarial","exp":now+600,"sub":"teste","email":"teste@portalnotarial.com.br","iat":now}
b64=base64.urlsafe_b64encode(json.dumps(payload,separators=(",",":")).encode()).rstrip(b"=").decode()
sig=hmac.new(secret,b64.encode(),hashlib.sha256).hexdigest()   # site usa assinatura HEX
print(f"https://ferramentas-teste.portalnotarial.com.br/calculadora-tarifas-conta-notarial.html?pn_token={b64}.{sig}")
PY
)
curl -sS -L -c /tmp/pn_cj.txt -o /dev/null -w "%{http_code}\n" "$URL"   # 200 no final
grep -o "pn_tool_access" /tmp/pn_cj.txt && echo "cookie OK"
```
Abrir a URL no navegador → a Calculadora de Tarifas deve renderizar.

## Cutover (no fim, junto com as demais)
1. Reapontar o clone para `main` (`git fetch && git checkout main && git pull && npm install --omit=dev && sudo systemctl restart ferramentas`).
2. Rodar `bash deploy/cutover-urls.sh` para trocar os backends `*.onrender.com` (consulta-pep, selo, links-úteis) pelos domínios do Contabo — **só quando esses backends já estiverem no ar no Contabo**.
3. Trocar o DNS de produção `ferramentas.portalnotarial.com.br` (CNAME→Render) para **A → 89.117.73.91**, criar o vhost de produção (mesmos arquivos, trocando `-teste`), rodar certbot pro domínio de produção.
4. Desligar o serviço no Render.

## Observações
- O `backend/` (Consulta PEP) é um **segundo serviço** Node com o `pep.csv` (23 MB, fora do Git/LGPD).
  Migrar à parte quando for a vez da Consulta PEP (não é das 6 prioritárias).
