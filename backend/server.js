import express from "express";
import cors from "cors";
import rateLimit from "express-rate-limit";
import crypto from "crypto";
import fs from "fs";
import fsp from "fs/promises";
import path from "path";
import readline from "readline";
import { fileURLToPath } from "url";

const app = express();


const PEP_ALLOWED_ORIGINS = new Set([
  "https://portalnotarial.com.br",
  "https://www.portalnotarial.com.br",
  "https://ferramentas.portalnotarial.com.br",
  "https://app.portalnotarial.com.br",
  "http://localhost:3000",
  "http://localhost:5500",
  "http://127.0.0.1:5500"
]);

function resolvePepCorsOrigin(req) {
  const origin = req.headers.origin;

  if (!origin) {
    return "*";
  }

  if (PEP_ALLOWED_ORIGINS.has(origin)) {
    return origin;
  }

  return "";
}

app.use((req, res, next) => {
  const originalSetHeader = res.setHeader.bind(res);

  res.setHeader = function patchedSetHeader(name, value) {
    if (String(name).toLowerCase() === "access-control-allow-origin") {
      const allowedOrigin = resolvePepCorsOrigin(req);

      if (allowedOrigin) {
        return originalSetHeader("Access-Control-Allow-Origin", allowedOrigin);
      }

      return originalSetHeader("Access-Control-Allow-Origin", "null");
    }

    return originalSetHeader(name, value);
  };

  const allowedOrigin = resolvePepCorsOrigin(req);

  if (allowedOrigin) {
    res.setHeader("Access-Control-Allow-Origin", allowedOrigin);
  }

  res.setHeader("Vary", "Origin");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

  if (req.method === "OPTIONS") {
    return res.status(204).end();
  }

  return next();
});
const PORT = process.env.PORT || 3000;
const FRONTEND_ORIGIN = process.env.FRONTEND_ORIGIN || "*";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CSV_PATH = path.join(__dirname, "data", "pep.csv");

let indicePorCpfCompleto = new Map();

let totalRegistros = 0;
let totalCpfsIndexados = 0;
let baseStatus = "iniciando";
let baseErro = null;
let baseCarregadaEm = null;
let arquivoBase = "pep.csv";
let ultimaModificacaoArquivo = null;
let camposDetectados = [];

app.use(express.json());

app.use(
  cors({
    origin: FRONTEND_ORIGIN === "*" ? "*" : FRONTEND_ORIGIN
  })
);

app.use(
  rateLimit({
    windowMs: 60 * 1000,
    limit: 60,
    standardHeaders: true,
    legacyHeaders: false,
    message: {
      erro: "Muitas consultas em pouco tempo. Aguarde alguns instantes e tente novamente."
    }
  })
);

function somenteNumeros(valor) {
  return String(valor || "").replace(/\D/g, "");
}

function normalizarCpfBase(cpf) {
  const numeros = somenteNumeros(cpf);

  if (!numeros) {
    return "";
  }

  if (numeros.length > 11) {
    return numeros.slice(-11);
  }

  return numeros.padStart(11, "0");
}

function cpfValido(cpf) {
  const numeros = normalizarCpfBase(cpf);

  if (numeros.length !== 11) return false;
  if (/^(\d)\1{10}$/.test(numeros)) return false;

  let soma = 0;

  for (let i = 0; i < 9; i++) {
    soma += Number(numeros[i]) * (10 - i);
  }

  let digito1 = 11 - (soma % 11);
  if (digito1 >= 10) digito1 = 0;

  if (digito1 !== Number(numeros[9])) return false;

  soma = 0;

  for (let i = 0; i < 10; i++) {
    soma += Number(numeros[i]) * (11 - i);
  }

  let digito2 = 11 - (soma % 11);
  if (digito2 >= 10) digito2 = 0;

  return digito2 === Number(numeros[10]);
}

function formatarCpfParaExibicao(cpf) {
  const numeros = normalizarCpfBase(cpf);

  if (numeros.length !== 11) {
    return cpf || "";
  }

  return numeros.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, "$1.$2.$3-$4");
}

function normalizarCabecalho(texto) {
  return String(texto || "")
    .replace(/^\uFEFF/, "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function separarLinhaCsv(linha, delimitador) {
  const campos = [];
  let atual = "";
  let dentroDeAspas = false;

  for (let i = 0; i < linha.length; i++) {
    const caractere = linha[i];
    const proximo = linha[i + 1];

    if (caractere === '"') {
      if (dentroDeAspas && proximo === '"') {
        atual += '"';
        i++;
      } else {
        dentroDeAspas = !dentroDeAspas;
      }
      continue;
    }

    if (caractere === delimitador && !dentroDeAspas) {
      campos.push(atual.trim());
      atual = "";
      continue;
    }

    atual += caractere;
  }

  campos.push(atual.trim());

  return campos;
}

function detectarDelimitador(linhaCabecalho) {
  const porPontoEVirgula = separarLinhaCsv(linhaCabecalho, ";").length;
  const porVirgula = separarLinhaCsv(linhaCabecalho, ",").length;

  return porPontoEVirgula >= porVirgula ? ";" : ",";
}

function obterValor(objeto, nomesPossiveis) {
  for (const nome of nomesPossiveis) {
    if (
      objeto &&
      objeto[nome] !== undefined &&
      objeto[nome] !== null &&
      String(objeto[nome]).trim() !== ""
    ) {
      return String(objeto[nome]).trim();
    }
  }

  return "";
}

function transformarRegistro(linha) {
  const cpfOriginal = obterValor(linha, ["cpf_pep", "cpf", "_coluna_0"]);
  const cpfNormalizado = normalizarCpfBase(cpfOriginal);

  const nome = obterValor(linha, ["nome_pep", "nome", "_coluna_1"]);
  const siglaFuncao = obterValor(linha, ["sigla_funcao_pep", "sigla_funcao", "_coluna_2"]);
  const descricaoFuncao = obterValor(linha, ["descricao_funcao_pep", "descricao_funcao", "_coluna_3"]);
  const nivelFuncao = obterValor(linha, ["nivel_funcao_pep", "nivel_funcao", "_coluna_4"]);
  const nomeOrgao = obterValor(linha, ["nome_orgao_pep", "nome_orgao", "_coluna_5"]);
  const dataInicioExercicio = obterValor(linha, ["dt_inicio_exercicio", "data_inicio_exercicio", "_coluna_6"]);
  const dataFimExercicio = obterValor(linha, ["dt_fim_exercicio", "data_fim_exercicio", "_coluna_7"]);
  const dataFimCarencia = obterValor(linha, ["dt_final_carencia", "dt_fim_carencia", "data_fim_carencia", "_coluna_8"]);
  const atualizacao = obterValor(linha, ["atualizacao", "_coluna_9"]);

  return {
    cpf: formatarCpfParaExibicao(cpfNormalizado),
    cpf_original_arquivo: cpfOriginal,
    cpf_normalizado: cpfNormalizado,
    nome,
    sigla_funcao: siglaFuncao,
    descricao_funcao: descricaoFuncao,
    nivel_funcao: nivelFuncao,
    nome_orgao: nomeOrgao,
    dt_inicio_exercicio: dataInicioExercicio,
    dt_fim_exercicio: dataFimExercicio,
    dt_fim_carencia: dataFimCarencia,
    atualizacao
  };
}

function adicionarAoIndice(indice, chave, registro) {
  if (!chave) {
    return;
  }

  if (!indice.has(chave)) {
    indice.set(chave, []);
  }

  indice.get(chave).push(registro);
}

function converterDataParaOrdenacao(data) {
  const texto = String(data || "").trim();

  if (!texto || texto.toLowerCase() === "não informada" || texto.toLowerCase() === "na") {
    return 0;
  }

  const partes = texto.split("/");

  if (partes.length !== 3) {
    return 0;
  }

  const dia = Number(partes[0]);
  const mes = Number(partes[1]);
  const ano = Number(partes[2]);

  if (!dia || !mes || !ano) {
    return 0;
  }

  return new Date(ano, mes - 1, dia).getTime();
}

function ordenarPorFimCarenciaDecrescente(lista) {
  return [...lista].sort((a, b) => {
    const dataA = converterDataParaOrdenacao(a.dt_fim_carencia);
    const dataB = converterDataParaOrdenacao(b.dt_fim_carencia);

    return dataB - dataA;
  });
}

async function carregarBasePep() {
  try {
    baseStatus = "carregando";
    baseErro = null;

    await fsp.access(CSV_PATH);

    const infoArquivo = await fsp.stat(CSV_PATH);

    arquivoBase = path.basename(CSV_PATH);
    ultimaModificacaoArquivo = infoArquivo.mtime.toISOString();

    const stream = fs.createReadStream(CSV_PATH, {
      encoding: "utf8"
    });

    const leitor = readline.createInterface({
      input: stream,
      crlfDelay: Infinity
    });

    let cabecalhos = null;
    let delimitador = ";";

    const novoIndiceCpfCompleto = new Map();

    let contadorRegistros = 0;

    for await (const linhaOriginal of leitor) {
      const linha = String(linhaOriginal || "").trim();

      if (!linha) {
        continue;
      }

      if (!cabecalhos) {
        delimitador = detectarDelimitador(linha);
        cabecalhos = separarLinhaCsv(linha, delimitador).map(normalizarCabecalho);
        camposDetectados = cabecalhos;

        if (!cabecalhos.includes("cpf_pep") && !cabecalhos.includes("cpf")) {
          throw new Error(
            `Campo CPF não localizado no cabeçalho do CSV. Campos detectados: ${cabecalhos.join(", ")}`
          );
        }

        continue;
      }

      const valores = separarLinhaCsv(linha, delimitador);
      const objeto = {};

      for (let i = 0; i < cabecalhos.length; i++) {
        objeto[cabecalhos[i]] = valores[i] || "";
        objeto[`_coluna_${i}`] = valores[i] || "";
      }

      const registro = transformarRegistro(objeto);
      const cpfNormalizado = registro.cpf_normalizado;

      contadorRegistros++;

      if (cpfNormalizado.length === 11) {
        adicionarAoIndice(novoIndiceCpfCompleto, cpfNormalizado, {
          ...registro,
          tipo_correspondencia: "cpf_completo"
        });
      }
    }

    indicePorCpfCompleto = novoIndiceCpfCompleto;

    totalRegistros = contadorRegistros;
    totalCpfsIndexados = novoIndiceCpfCompleto.size;

    baseCarregadaEm = new Date().toISOString();
    baseStatus = "pronta";

    console.log("Base PEP carregada.");
    console.log(`Arquivo: ${arquivoBase}`);
    console.log(`Registros lidos: ${totalRegistros}`);
    console.log(`CPFs indexados: ${totalCpfsIndexados}`);
  } catch (erro) {
    baseStatus = "erro";
    baseErro = erro.message;
    totalRegistros = 0;
    totalCpfsIndexados = 0;
    indicePorCpfCompleto = new Map();

    console.error("Erro ao carregar a base PEP:", erro);
  }
}

// =====================================================================
// Controle de acesso (LGPD): valida o token HMAC emitido pelo Portal.
// Gated por env: só é exigido quando PEP_AUTH_REQUIRED estiver ligado
// (default desligado, para não interromper o serviço já em produção).
// Use o MESMO PORTAL_TOOL_ACCESS_SECRET do Portal/servidor de proteção.
// =====================================================================
function pepBase64UrlDecode(value) {
  return Buffer.from(value, "base64url").toString("utf8");
}

function pepAssinar(payloadB64, secret) {
  return crypto.createHmac("sha256", secret).update(payloadB64).digest("hex");
}

function pepCompararSeguro(a, b) {
  const bufA = Buffer.from(String(a || ""));
  const bufB = Buffer.from(String(b || ""));
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

function pepVerificarToken(token, slugEsperado) {
  const secret = process.env.PORTAL_TOOL_ACCESS_SECRET || "";
  if (!secret || !token || !token.includes(".")) return false;
  try {
    const [payloadB64, assinatura] = token.split(".", 2);
    if (!pepCompararSeguro(assinatura, pepAssinar(payloadB64, secret))) return false;
    const payload = JSON.parse(pepBase64UrlDecode(payloadB64));
    if (slugEsperado && payload.slug !== slugEsperado) return false;
    const exp = Number(payload.exp || 0);
    if (!exp || exp < Math.floor(Date.now() / 1000)) return false;
    return true;
  } catch (_erro) {
    return false;
  }
}

function extrairTokenDaRequisicao(req) {
  const auth = String(req.headers.authorization || "");
  if (auth.toLowerCase().startsWith("bearer ")) return auth.slice(7).trim();
  if (req.query && req.query.pn_token) return String(req.query.pn_token);
  return "";
}

function exigirAcessoPep(req, res, next) {
  const authRequired = ["1", "true", "yes", "sim", "on"].includes(
    String(process.env.PEP_AUTH_REQUIRED || "").trim().toLowerCase()
  );
  if (!authRequired) return next();

  const slugEsperado = process.env.PEP_TOOL_SLUG || "consulta-pep";
  const token = extrairTokenDaRequisicao(req);

  if (!pepVerificarToken(token, slugEsperado)) {
    return res.status(401).json({ erro: "Acesso não autorizado. Abra a ferramenta pelo Portal Notarial." });
  }
  return next();
}

app.get("/", (req, res) => {
  // Status mínimo; não expõe caminho do arquivo, mensagem de erro interna,
  // campos detectados nem contagens (evita reconhecimento e vazamento operacional).
  res.json({
    status: "online",
    servico: "Consulta PEP por CPF",
    fonte: "Arquivo PEP do Siscoaf",
    baseStatus
  });
});

app.get("/api/pep", exigirAcessoPep, (req, res) => {
  try {
    if (baseStatus === "carregando" || baseStatus === "iniciando") {
      return res.status(503).json({
        erro: "Base PEP ainda está sendo carregada. Tente novamente em alguns instantes.",
        baseStatus
      });
    }

    if (baseStatus === "erro") {
      return res.status(500).json({
        erro: "Base PEP não foi carregada no servidor."
      });
    }

    const cpf = normalizarCpfBase(req.query.cpf);
    const pagina = String(req.query.pagina || "1").trim();

    if (!cpf) {
      return res.status(400).json({
        erro: "Informe o CPF para consulta."
      });
    }

    if (!cpfValido(cpf)) {
      return res.status(400).json({
        erro: "CPF inválido. Confira os números informados."
      });
    }

    let resultado = indicePorCpfCompleto.get(cpf) || [];
    resultado = ordenarPorFimCarenciaDecrescente(resultado);

    return res.json({
      fonte: "Arquivo PEP do Siscoaf",
      modoConsulta: "base CSV oficial carregada no backend",
      observacao: "Os CPFs do arquivo foram normalizados para 11 dígitos, com zeros à esquerda quando necessário.",
      consultaRealizadaEm: new Date().toISOString(),
      baseCarregadaEm,
      ultimaModificacaoArquivo,
      arquivoBase,
      parametroPesquisado: {
        cpf
      },
      tipoConsulta: "cpf_completo",
      ordenacao: "Fim da carência em ordem decrescente",
      pagina,
      resultado
    });
  } catch (erro) {
    console.error("Erro interno ao consultar PEP:", erro);
    return res.status(500).json({
      erro: "Erro interno ao consultar PEP."
    });
  }
});

app.listen(PORT, () => {
  console.log(`Servidor iniciado na porta ${PORT}.`);
  carregarBasePep();
});
