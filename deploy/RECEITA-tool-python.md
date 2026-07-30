# Receita — migrar uma ferramenta Python (Django/Gunicorn) para o Contabo

Validada no **piloto ITCMD** (30/07/2026). O servidor Contabo usa **Apache + Gunicorn (socket) + certbot**
— não Docker. Cada ferramenta segue estes passos. Troque as variáveis do topo.

## Variáveis (exemplo: Ganho de Capital)
```
TOOL=ganho                                   # nome curto
REPO=https://github.com/atas26/ganho-de-capital.git
SLUG=ganho-de-capital                        # PORTAL_TOOL_SLUG (confirmar no código do tool)
SUB=ganho-teste.portalnotarial.com.br        # subdomínio de STAGING (não o de produção!)
DIR=/home/fernando/ganho
SOCK=/run/gunicorn/gunicorn_${TOOL}.sock
SVC=gunicorn_${TOOL}
WSGI=calculadora.wsgi:application            # CONFIRMAR por repo (ver passo 2)
```

## 0) DNS (staging)
No painel do domínio, criar registro **A**: `SUB` → **89.117.73.91** (IP do Contabo).
> Nunca apague o CNAME de produção (`itcmd`, `ganho`, etc.) agora — isso é a virada (cutover).

## 1) Clonar + ambiente Python
```bash
cd /home/fernando
git clone $REPO $TOOL
cd $TOOL
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

## 2) Conferir estrutura (define o WSGI e comandos de dados)
```bash
ls -la
find . -maxdepth 3 \( -name wsgi.py -o -name manage.py \)
ls */management/commands/ 2>/dev/null    # comandos de import de dados (ex.: import_juros_itcmd)
```
- Se `manage.py` está na raiz e o pacote do projeto é `X/` (com `wsgi.py`) → `WSGI=X.wsgi:application`, sem `--chdir`.
- Anote comandos de dados a rodar no passo 4.

## 3) Segredos / config
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"   # DJANGO_SECRET_KEY
sudo nano /etc/default/$TOOL
```
Conteúdo (o `PORTAL_TOOL_ACCESS_SECRET` = o MESMO do Render/app; copie do painel):
```
PORTAL_TOOL_ACCESS_SECRET=<mesmo do app>
PORTAL_AUTH_REQUIRED=True
PORTAL_APP_URL=https://app.portalnotarial.com.br
PORTAL_TOOL_SLUG=<SLUG>
PORTAL_ACCESS_COOKIE_NAME=pn_tool_access
PORTAL_ACCESS_COOKIE_MAX_AGE=7200
DJANGO_SECRET_KEY=<gerada>
DEBUG=False
ALLOWED_HOSTS=<SUB>
CSRF_TRUSTED_ORIGINS=https://<SUB>
SECURE_SSL_REDIRECT=False
DJANGO_SETTINGS_MODULE=<pacote>.settings
```
```bash
sudo chmod 640 /etc/default/$TOOL
sudo chown root:fernando /etc/default/$TOOL
```

## 4) Banco + dados + estáticos
```bash
cd $DIR && source venv/bin/activate
set -a; . /etc/default/$TOOL; set +a
python manage.py migrate --noinput
# rode aqui os comandos de dados do passo 2 (ex.: python manage.py import_juros_itcmd)
python manage.py collectstatic --noinput
```

## 5) Pasta do socket (já configurada uma vez — vale para todos)
```bash
# feito no piloto; só rode de novo se necessário:
echo 'd /run/gunicorn 0775 fernando www-data -' | sudo tee /etc/tmpfiles.d/gunicorn.conf
sudo systemd-tmpfiles --create /etc/tmpfiles.d/gunicorn.conf
```

## 6) Serviço systemd
```bash
sudo tee /etc/systemd/system/$SVC.service > /dev/null <<EOF
[Unit]
Description=gunicorn daemon for $TOOL
After=network.target

[Service]
User=fernando
Group=www-data
WorkingDirectory=$DIR
EnvironmentFile=/etc/default/$TOOL
ExecStart=$DIR/venv/bin/gunicorn --workers 3 --timeout 600 --bind unix:$SOCK $WSGI

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now $SVC
sleep 3 && sudo systemctl status $SVC --no-pager | head -8
curl -sS -I --unix-socket $SOCK -H "Host: $SUB" http://localhost/    # espera 302 -> login
```

## 7) Apache :80 (ACME + redirect) + certbot
```bash
sudo tee /etc/apache2/sites-available/$TOOL-teste.conf > /dev/null <<EOF
<VirtualHost *:80>
    ServerName $SUB
    Alias /.well-known/acme-challenge/ /var/www/letsencrypt/.well-known/acme-challenge/
    <Directory /var/www/letsencrypt/.well-known/acme-challenge/>
        Require all granted
    </Directory>
    RewriteEngine On
    RewriteCond %{REQUEST_URI} !^/\.well-known/acme-challenge/
    RewriteRule ^ https://$SUB%{REQUEST_URI} [R=301,L,NE]
</VirtualHost>
EOF
sudo a2ensite $TOOL-teste.conf
sudo apache2ctl configtest && sudo systemctl reload apache2
sudo certbot certonly --webroot -w /var/www/letsencrypt -d $SUB
```

## 8) Apache :443 (SSL + proxy pro socket)
```bash
sudo tee /etc/apache2/sites-available/$TOOL-teste-le-ssl.conf > /dev/null <<EOF
<IfModule mod_ssl.c>
<VirtualHost *:443>
    ServerName $SUB
    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/$SUB/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/$SUB/privkey.pem
    Include /etc/letsencrypt/options-ssl-apache.conf
    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"
    ProxyTimeout 600
    ProxyPass / unix:$SOCK|http://localhost/ timeout=600 keepalive=On
    ProxyPassReverse / http://localhost/
</VirtualHost>
</IfModule>
EOF
sudo a2ensite $TOOL-teste-le-ssl.conf
sudo apache2ctl configtest && sudo systemctl reload apache2
curl -sS -I https://$SUB/          # espera 302 https -> login
```

## 9) Prova ponta a ponta (abre a ferramenta pro assinante)
```bash
python3 - <<'PY'
import json, base64, hmac, hashlib, time, os
env={}
for line in open("/etc/default/TOOLNAME"):   # troque TOOLNAME
    line=line.strip()
    if line and not line.startswith("#") and "=" in line:
        k,v=line.split("=",1); env[k]=v
secret=env["PORTAL_TOOL_ACCESS_SECRET"].encode()
now=int(time.time())
payload={"slug":env["PORTAL_TOOL_SLUG"],"exp":now+600,"iat":now}
b64=base64.urlsafe_b64encode(json.dumps(payload,separators=(",",":")).encode()).rstrip(b"=").decode()
sig=hmac.new(secret,b64.encode(),hashlib.sha256).hexdigest()
print("https://"+env["ALLOWED_HOSTS"]+"/?pn_token="+b64+"."+sig)
PY
```
Abrir a URL no navegador → a ferramenta deve renderizar (não redirecionar).

## Cutover (por ferramenta, no fim)
1. App aponta o tool para o novo domínio.
2. Trocar o DNS de produção (CNAME→A) para o Contabo.
3. Desligar o serviço no Render.

## Observações
- Cada tool pode ter comandos de dados próprios (passo 2/4) e nome de pacote WSGI diferente.
- Ferramentas com Postgres/Celery/Redis (ex.: a Calculadora Avançada) exigem passos extras (banco + worker + broker) — tratar caso a caso.
