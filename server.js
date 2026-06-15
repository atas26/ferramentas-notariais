import express from 'express';
import path from 'node:path';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const app = express();
const PORT = Number(process.env.PORT || 3000);

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

app.disable('x-powered-by');

function portalEnvBool(name, defaultValue = false) {
  const value = String(process.env[name] ?? '').trim().toLowerCase();

  if (!value) return defaultValue;
  return ['1', 'true', 'yes', 'sim', 'on'].includes(value);
}

function portalBase64UrlEncode(value) {
  return Buffer.from(value).toString('base64url');
}

function portalBase64UrlDecode(value) {
  return Buffer.from(value, 'base64url').toString('utf8');
}

function portalSignPayload(payloadB64, secret) {
  return crypto
    .createHmac('sha256', secret)
    .update(payloadB64)
    .digest('hex');
}

function portalSafeCompare(a, b) {
  const aBuffer = Buffer.from(String(a || ''));
  const bBuffer = Buffer.from(String(b || ''));

  if (aBuffer.length !== bBuffer.length) {
    return false;
  }

  return crypto.timingSafeEqual(aBuffer, bBuffer);
}

function portalCreateCookieToken(payload, secret, maxAgeSeconds) {
  const now = Math.floor(Date.now() / 1000);
  const cookiePayload = {
    slug: payload.slug,
    sub: payload.sub || '',
    email: payload.email || '',
    iat: now,
    exp: now + maxAgeSeconds,
    source: 'portal-tool-cookie'
  };

  const payloadB64 = portalBase64UrlEncode(JSON.stringify(cookiePayload));
  const signature = portalSignPayload(payloadB64, secret);

  return `${payloadB64}.${signature}`;
}

function portalVerifyToken(token, expectedSlug) {
  const secret = process.env.PORTAL_TOOL_ACCESS_SECRET || '';

  if (!secret || !token || !token.includes('.')) {
    return { ok: false };
  }

  try {
    const [payloadB64, receivedSignature] = token.split('.', 2);
    const expectedSignature = portalSignPayload(payloadB64, secret);

    if (!portalSafeCompare(receivedSignature, expectedSignature)) {
      return { ok: false };
    }

    const payload = JSON.parse(portalBase64UrlDecode(payloadB64));

    if (expectedSlug && payload.slug !== expectedSlug) {
      return { ok: false };
    }

    const exp = Number(payload.exp || 0);
    if (!exp || exp < Math.floor(Date.now() / 1000)) {
      return { ok: false };
    }

    return { ok: true, payload };
  } catch (_error) {
    return { ok: false };
  }
}

function portalParseCookies(req) {
  const header = String(req.headers.cookie || '');
  const cookies = {};

  for (const part of header.split(';')) {
    const [rawName, ...rawValue] = part.trim().split('=');
    if (!rawName) continue;
    cookies[rawName] = decodeURIComponent(rawValue.join('=') || '');
  }

  return cookies;
}

function portalSerializeCookie(name, value, maxAgeSeconds, req) {
  const secure = req.secure || req.headers['x-forwarded-proto'] === 'https';
  const attrs = [
    `${name}=${encodeURIComponent(value)}`,
    `Max-Age=${maxAgeSeconds}`,
    'Path=/',
    'HttpOnly',
    'SameSite=Lax'
  ];

  if (secure) {
    attrs.push('Secure');
  }

  return attrs.join('; ');
}

function portalIsAssetPath(pathname) {
  return /\.(css|js|mjs|map|png|jpg|jpeg|gif|webp|svg|ico|woff|woff2|ttf|eot)$/i.test(pathname);
}

function portalEnhancePublicIndexHtml(html) {
  let output = String(html || '');

  const cssTag = '<link rel="stylesheet" href="/public-index-categorias.css?v=1.0.0" />';
  const jsTag = '<script src="/public-index-categorias.js?v=1.0.0"></script>';

  if (!output.includes('/public-index-categorias.css')) {
    output = output.replace('</head>', `  ${cssTag}\n</head>`);
  }

  if (!output.includes('/public-index-categorias.js')) {
    output = output.replace('</body>', `  ${jsTag}\n</body>`);
  }

  return output;
}

const PROTECTED_ROUTES = new Map([
  ['/aplicador-de-emolumentos.html', 'aplicador-emolumentos'],
  ['/aplicador-de-emolumentos', 'aplicador-emolumentos'],
  ['/consulta-selo-digital.html', 'selo-digital-tjsp'],
  ['/consulta-selo-digital', 'selo-digital-tjsp'],
  ['/gerador-de-orcamentos-notariais.html', 'gerador-orcamento'],
  ['/gerador-de-orcamentos-notariais', 'gerador-orcamento'],
  ['/consulta-pep.html', 'consulta-pep'],
  ['/consulta-pep', 'consulta-pep'],
  ['/competencia-e-notariado.html', 'competencia-e-notariado'],
  ['/competencia-e-notariado', 'competencia-e-notariado'],
  ['/calculadora-tarifas-conta-notarial.html', 'tarifas-conta-notarial'],
  ['/calculadora-tarifas-conta-notarial', 'tarifas-conta-notarial'],
  ['/gerador-certidao-reprografica.html', 'certidao-reprografica'],
  ['/gerador-certidao-reprografica', 'certidao-reprografica'],
  ['/oficios-comparecimento.html', 'oficio-comparecimento'],
  ['/oficios-comparecimento', 'oficio-comparecimento'],
  ['/oficios-outros-cartorios.html', 'oficio-cartorios'],
  ['/oficios-outros-cartorios', 'oficio-cartorios'],
  ['/oficios-bancos', 'oficio-bancos-inventario'],
  ['/oficios-bancos/', 'oficio-bancos-inventario'],
  ['/oficios-bancos/index.html', 'oficio-bancos-inventario']
]);

function portalProtectedStaticMiddleware(req, res, next) {
  const authRequired = portalEnvBool('PORTAL_AUTH_REQUIRED', process.env.NODE_ENV === 'production');

  if (!authRequired) {
    return next();
  }

  const pathname = req.path || '/';
  const expectedSlug = PROTECTED_ROUTES.get(pathname);

  if (!expectedSlug) {
    return next();
  }

  const appUrl = (process.env.PORTAL_APP_URL || 'https://app.portalnotarial.com.br').replace(/\/+$/, '');
  const cookieName = process.env.PORTAL_ACCESS_COOKIE_NAME || 'pn_tool_access';
  const cookieMaxAge = Number(process.env.PORTAL_ACCESS_COOKIE_MAX_AGE || 7200);

  const queryToken = String(req.query?.pn_token || '');
  const queryResult = portalVerifyToken(queryToken, expectedSlug);

  if (queryResult.ok) {
    const redirectUrl = new URL(`${req.protocol}://${req.get('host')}${req.originalUrl}`);
    redirectUrl.searchParams.delete('pn_token');

    const cookieToken = portalCreateCookieToken(queryResult.payload, process.env.PORTAL_TOOL_ACCESS_SECRET || '', cookieMaxAge);
    res.setHeader('Set-Cookie', portalSerializeCookie(cookieName, cookieToken, cookieMaxAge, req));

    return res.redirect(302, redirectUrl.pathname + redirectUrl.search);
  }

  const cookies = portalParseCookies(req);
  const cookieResult = portalVerifyToken(cookies[cookieName], expectedSlug);

  if (cookieResult.ok) {
    return next();
  }

  const redirectTarget = `${appUrl}?origem=${encodeURIComponent(`${req.protocol}://${req.get('host')}${req.originalUrl}`)}`;
  return res.redirect(302, redirectTarget);
}

app.get('/api/portal-protection-health', (_req, res) => {
  res.json({
    ok: true,
    service: 'ferramentas-notariais',
    protectedRoutes: Array.from(PROTECTED_ROUTES.keys()),
    portalToolSecretConfigured: Boolean(process.env.PORTAL_TOOL_ACCESS_SECRET)
  });
});

app.use(portalProtectedStaticMiddleware);

app.get(['/', '/index.html'], async (_req, res, next) => {
  try {
    const html = await fs.readFile(path.join(__dirname, 'index.html'), 'utf8');
    res.type('html').send(portalEnhancePublicIndexHtml(html));
  } catch (error) {
    next(error);
  }
});

app.use(express.static(__dirname, {
  etag: false,
  lastModified: false,
  maxAge: 0,
  setHeaders: (res) => {
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
  }
}));

app.get(['/sobre', '/sobre.html'], (_req, res) => {
  res.sendFile(path.join(__dirname, 'sobre.html'));
});

app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Portal Notarial público iniciado na porta ${PORT}.`);
});
