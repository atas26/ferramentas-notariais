import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin

import fitz
import requests
from bs4 import BeautifulSoup


GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "atas26")
GITHUB_REPO = os.getenv("GITHUB_REPO", "ferramentas-notariais")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
PARSER_VERSION = "cnj-hierarchy-v5"

TJSP_URL = os.getenv(
    "TJSP_URL",
    "https://api.tjsp.jus.br/Handlers/Handler/FileFetch.ashx?codigo=179577",
)

CNJ_PAGE_URL = os.getenv(
    "CNJ_PAGE_URL",
    "https://atos.cnj.jus.br/atos/detalhar/5243",
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 atualizador-normas-notariais/1.0"
}


def conferir_variaveis():
    if not GITHUB_TOKEN:
        print("Erro: variável GITHUB_TOKEN não configurada no Render.")
        sys.exit(1)


def baixar_arquivo(url):
    print(f"Baixando: {url}")
    resposta = requests.get(url, headers=HEADERS, timeout=180)
    resposta.raise_for_status()
    return resposta.content


def descobrir_pdf_compilado_cnj():
    print("Procurando o PDF de Texto Compilado do CNJ...")
    resposta = requests.get(CNJ_PAGE_URL, headers=HEADERS, timeout=120)
    resposta.raise_for_status()
    soup = BeautifulSoup(resposta.text, "html.parser")

    for link in soup.find_all("a"):
        texto = link.get_text(" ", strip=True)
        href = link.get("href", "")

        if "Texto Compilado" in texto and href:
            pdf_url = urljoin(CNJ_PAGE_URL, href)
            print(f"PDF compilado localizado: {pdf_url}")
            return pdf_url

    for link in soup.find_all("a"):
        href = link.get("href", "")
        if href.lower().endswith(".pdf"):
            pdf_url = urljoin(CNJ_PAGE_URL, href)
            print(f"PDF localizado por extensão: {pdf_url}")
            return pdf_url

    raise RuntimeError("Não foi possível localizar o link Texto Compilado na página do CNJ.")


def extrair_texto_pdf(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    partes = []

    for pagina in doc:
        partes.append(pagina.get_text("text"))

    return "\n".join(partes)


def limpar_linha(linha):
    linha = linha.replace("\u00ad", "")
    linha = linha.replace("\x02", "")
    linha = linha.strip()
    linha = re.sub(r"\s+", " ", linha)
    return linha


def linha_inutil_sp(linha):
    if not linha:
        return True

    if re.match(r"^Cap\.\s*[–-]\s*[XVI]+$", linha):
        return True

    if re.match(r"^\d+$", linha):
        return True

    if linha in {
        "PROVIMENTO Nº 58/89",
        "Sumário",
        "CORREGEDORIA GERAL DA JUSTIÇA DO ESTADO DE SÃO PAULO",
    }:
        return True

    return False


def parece_nota_sp(linha):
    return bool(
        re.match(
            r"^\d{1,4}\s+(Prov\.|Provs\.|L\.|Lei|LC|DL|D\.|CJE|RITJ|Proc\.|Com\.|Res\.|Art\.)",
            linha,
        )
    )


def formatar_paragrafos(linhas):
    paragrafos = []
    atual = ""

    inicios = (
        "§",
        "Parágrafo único",
        "I ",
        "II ",
        "III ",
        "IV ",
        "V ",
        "VI ",
        "VII ",
        "VIII ",
        "IX ",
        "X ",
        "XI ",
        "XII ",
        "XIII ",
        "XIV ",
        "XV ",
        "a)",
        "b)",
        "c)",
        "d)",
        "e)",
        "f)",
        "g)",
        "h)",
        "i)",
        "j)",
        "k)",
        "l)",
        "m)",
        "n)",
    )

    for linha in linhas:
        linha = limpar_linha(linha)

        if not linha:
            if atual:
                paragrafos.append(atual)
                atual = ""
            continue

        if linha.startswith(inicios):
            if atual:
                paragrafos.append(atual)
            atual = linha
            continue

        if atual:
            atual += " " + linha
        else:
            atual = linha

    if atual:
        paragrafos.append(atual)

    return "\n\n".join(paragrafos)


CAPITULOS_SP = {
    "XIII": "Capítulo XIII\nDisposições gerais\nFunção correcional\nLivros\nClassificadores\nEmolumentos",
    "XIV": "Capítulo XIV\nPessoal dos serviços extrajudiciais",
    "XV": "Capítulo XV\nTabelionato de Protesto",
    "XVI": "Capítulo XVI\nTabelionato de Notas",
    "XVII": "Capítulo XVII\nRegistro Civil das Pessoas Naturais",
    "XVIII": "Capítulo XVIII\nRegistro Civil das Pessoas Jurídicas",
    "XIX": "Capítulo XIX\nRegistro de Títulos e Documentos",
    "XX": "Capítulo XX\nRegistro de Imóveis",
}

AREAS_SP = {
    "XIII": "Disposições gerais",
    "XIV": "Pessoal dos serviços extrajudiciais",
    "XV": "Tabelionato de Protesto",
    "XVI": "Tabelionato de Notas",
    "XVII": "Registro Civil das Pessoas Naturais",
    "XVIII": "Registro Civil das Pessoas Jurídicas",
    "XIX": "Registro de Títulos e Documentos",
    "XX": "Registro de Imóveis",
}

ORDEM_SP = {
    "XIII": 100000,
    "XIV": 200000,
    "XV": 300000,
    "XVI": 400000,
    "XVII": 500000,
    "XVIII": 600000,
    "XIX": 700000,
    "XX": 800000,
}


def numero_item(linha):
    achou = re.match(r"^(\d+[A-Z]?(?:\.\d+)*\.?)\s+", linha)
    if not achou:
        return None

    return achou.group(1).rstrip(".")


def valor_item(numero):
    partes = re.findall(r"\d+", numero)

    if not partes:
        return 0

    valor = int(partes[0])
    divisor = 1000

    for parte in partes[1:]:
        valor += int(parte) / divisor
        divisor *= 1000

    return valor


def parse_sp(texto):
    print("Organizando Normas da Corregedoria de São Paulo...")

    artigos = []
    capitulo_atual = None
    secao_atual = ""
    item_atual = None

    for bruto in texto.splitlines():
        linha = limpar_linha(bruto)

        if linha_inutil_sp(linha):
            continue

        achou_capitulo = re.match(r"^CAPÍTULO\s+([XVI]+)", linha, re.I)
        if achou_capitulo:
            romano = achou_capitulo.group(1).upper()
            if romano in CAPITULOS_SP:
                capitulo_atual = romano
                secao_atual = ""
            continue

        if re.match(r"^SEÇÃO\s+[IVXLCDM]+", linha, re.I) or re.match(r"^Subseção\s+[IVXLCDM]+", linha, re.I):
            secao_atual = linha.title()
            continue

        if not capitulo_atual:
            continue

        if parece_nota_sp(linha):
            if item_atual is not None:
                item_atual["notas"].append(linha)
            continue

        numero = numero_item(linha)

        if numero:
            if item_atual is not None:
                item_atual["texto"] = formatar_paragrafos(item_atual.pop("_linhas"))
                artigos.append(item_atual)

            ordem = ORDEM_SP[capitulo_atual] + valor_item(numero)
            item_id = f"sp-cap-{capitulo_atual.lower()}-item-{numero.lower().replace('.', '-')}"

            item_atual = {
                "id": item_id,
                "numero": f"Cap. {capitulo_atual}, item {numero}",
                "ordem": ordem,
                "tipo": "item",
                "capitulo": CAPITULOS_SP[capitulo_atual],
                "secao": secao_atual,
                "areas": [AREAS_SP[capitulo_atual]],
                "temas": [],
                "norma": True,
                "notas": [],
                "_linhas": [linha],
            }

        elif item_atual is not None:
            item_atual["_linhas"].append(linha)

    if item_atual is not None:
        item_atual["texto"] = formatar_paragrafos(item_atual.pop("_linhas"))
        artigos.append(item_atual)

    return artigos


def classificar_area_cnj(texto):
    base = texto.lower()
    areas = []

    if any(x in base for x in ["tabelião de notas", "tabelionato de notas", "ato notarial", "escritura pública", "ata notarial", "e-notariado"]):
        areas.append("Tabelionato de Notas")

    if "registro civil das pessoas naturais" in base:
        areas.append("Registro Civil das Pessoas Naturais")

    if "registro de imóveis" in base or "registrador de imóveis" in base:
        areas.append("Registro de Imóveis")

    if "protesto" in base:
        areas.append("Tabelionato de Protesto")

    if "registro de títulos e documentos" in base or "registro civil das pessoas jurídicas" in base:
        areas.append("Registro de Títulos e Documentos e Civil das Pessoas Jurídicas")

    if "apostil" in base:
        areas.append("Apostilamento")

    if any(x in base for x in ["proteção de dados", "lgpd", "sistema eletrônico", "certificado digital", "tecnologia"]):
        areas.append("Tecnologia e proteção de dados")

    if not areas:
        areas.append("Disposições gerais")

    return sorted(set(areas))


def ordem_artigo(numero):
    achou = re.match(r"(\d+)(?:-?([A-Z]))?", numero.upper())

    if not achou:
        return 0

    base = int(achou.group(1))
    letra = achou.group(2)

    if letra:
        return base + (ord(letra) - 64) / 100

    return base


def eh_linha_de_hierarquia_cnj(linha):
    return bool(
        re.match(r"^PARTE\s+(GERAL|ESPECIAL)\s*$", linha, re.I)
        or re.match(r"^LIVRO\s+[IVXLCDM]+\b", linha, re.I)
        or re.match(r"^T[ÍI]TULO\s+[IVXLCDM]+\b", linha, re.I)
        or re.match(r"^CAP[ÍI]TULO\s+[IVXLCDM]+\b", linha, re.I)
        or re.match(r"^Seç[ãa]o\s+[IVXLCDM]+\b", linha, re.I)
        or re.match(r"^Subseç[ãa]o\s+[IVXLCDM]+\b", linha, re.I)
    )


def eh_titulo_descritivo_cnj(linha):
    if not linha:
        return False

    texto = str(linha or "").strip()

    if re.match(r"^Art\.\s*\d+", texto):
        return False

    if eh_linha_de_hierarquia_cnj(texto):
        return False

    if re.match(r"^PARTE\s+(?!GERAL\s*$|ESPECIAL\s*$).+", texto, re.I):
        return False

    if re.match(r"^\d+$", texto):
        return False

    if len(texto) > 120:
        return False

    return True


def combinar_heading(numero, titulo):
    numero = str(numero or "").strip()
    titulo = str(titulo or "").strip()
    if numero and titulo:
        return f"{numero} - {titulo}"
    return numero or titulo


def estrutura_cnj(h):
    linhas = []

    def add(text, tipo):
        text = str(text or "").strip()
        if text:
            linhas.append({"text": text, "type": tipo})

    add(h.get("parte"), "upper")
    add(h.get("livro"), "upper")
    add(h.get("livroTitulo"), "title")
    add(h.get("titulo"), "upper")
    add(h.get("tituloTitulo"), "title")
    add(h.get("capituloNumero"), "upper")
    add(h.get("capituloTitulo"), "title")
    add(h.get("secao"), "section")
    add(h.get("secaoTitulo"), "section-title")
    add(h.get("subsecao"), "section")
    add(h.get("subsecaoTitulo"), "section-title")
    return linhas


def parse_cnj(texto):
    print("Organizando Código Nacional de Normas...")

    artigos = []
    artigo_atual = None
    iniciar = False
    pendente = None

    h = {
        "parte": "",
        "livro": "",
        "livroTitulo": "",
        "titulo": "",
        "tituloTitulo": "",
        "capituloNumero": "",
        "capituloTitulo": "",
        "secao": "",
        "secaoTitulo": "",
        "subsecao": "",
        "subsecaoTitulo": "",
    }

    def fechar_artigo():
        nonlocal artigo_atual
        if artigo_atual is None:
            return
        artigo_atual["texto"] = formatar_paragrafos(artigo_atual.pop("_linhas"))
        artigo_atual["areas"] = classificar_area_cnj(
            artigo_atual["texto"] + " " + " ".join(x.get("text", "") for x in artigo_atual.get("estrutura", []))
        )
        artigos.append(artigo_atual)
        artigo_atual = None

    for bruto in texto.splitlines():
        linha = limpar_linha(bruto)

        if not linha:
            continue

        if not iniciar:
            if re.match(r"^PARTE\s+GERAL\b", linha, re.I):
                iniciar = True
            else:
                continue

        if re.match(r"^PARTE\s+(GERAL|ESPECIAL)\s*$", linha, re.I):
            fechar_artigo()
            h.update({
                "parte": linha.upper(),
                "livro": "",
                "livroTitulo": "",
                "titulo": "",
                "tituloTitulo": "",
                "capituloNumero": "",
                "capituloTitulo": "",
                "secao": "",
                "secaoTitulo": "",
                "subsecao": "",
                "subsecaoTitulo": "",
            })
            pendente = None
            continue

        m = re.match(r"^(LIVRO\s+[IVXLCDM]+)\b\s*(.*)$", linha, re.I)
        if m:
            fechar_artigo()
            h["livro"] = m.group(1).upper()
            h["livroTitulo"] = m.group(2).strip().upper()
            h["titulo"] = ""
            h["tituloTitulo"] = ""
            h["capituloNumero"] = ""
            h["capituloTitulo"] = ""
            h["secao"] = ""
            h["secaoTitulo"] = ""
            h["subsecao"] = ""
            h["subsecaoTitulo"] = ""
            pendente = "livro" if not h["livroTitulo"] else None
            continue

        m = re.match(r"^(T[ÍI]TULO\s+[IVXLCDM]+)\b\s*(.*)$", linha, re.I)
        if m:
            fechar_artigo()
            h["titulo"] = m.group(1).upper().replace("TITULO", "TÍTULO")
            h["tituloTitulo"] = m.group(2).strip().upper()
            h["capituloNumero"] = ""
            h["capituloTitulo"] = ""
            h["secao"] = ""
            h["secaoTitulo"] = ""
            h["subsecao"] = ""
            h["subsecaoTitulo"] = ""
            pendente = "titulo" if not h["tituloTitulo"] else None
            continue

        m = re.match(r"^(CAP[ÍI]TULO\s+[IVXLCDM]+)\b\s*(.*)$", linha, re.I)
        if m:
            fechar_artigo()
            h["capituloNumero"] = m.group(1).upper().replace("CAPITULO", "CAPÍTULO")
            h["capituloTitulo"] = m.group(2).strip().upper()
            h["secao"] = ""
            h["secaoTitulo"] = ""
            h["subsecao"] = ""
            h["subsecaoTitulo"] = ""
            pendente = "capitulo" if not h["capituloTitulo"] else None
            continue

        m = re.match(r"^(Seç[ãa]o\s+[IVXLCDM]+)\b\s*(.*)$", linha, re.I)
        if m:
            fechar_artigo()
            h["secao"] = m.group(1).replace("secao", "Seção").replace("Seçao", "Seção")
            h["secaoTitulo"] = m.group(2).strip()
            h["subsecao"] = ""
            h["subsecaoTitulo"] = ""
            pendente = "secao" if not h["secaoTitulo"] else None
            continue

        m = re.match(r"^(Subseç[ãa]o\s+[IVXLCDM]+)\b\s*(.*)$", linha, re.I)
        if m:
            fechar_artigo()
            h["subsecao"] = m.group(1).replace("subsecao", "Subseção").replace("Subseçao", "Subseção")
            h["subsecaoTitulo"] = m.group(2).strip()
            pendente = "subsecao" if not h["subsecaoTitulo"] else None
            continue

        if pendente:
            if eh_titulo_descritivo_cnj(linha):
                if pendente == "livro":
                    h["livroTitulo"] = linha.upper()
                elif pendente == "titulo":
                    h["tituloTitulo"] = linha.upper()
                elif pendente == "capitulo":
                    h["capituloTitulo"] = linha.upper()
                elif pendente == "secao":
                    h["secaoTitulo"] = linha
                elif pendente == "subsecao":
                    h["subsecaoTitulo"] = linha
                pendente = None
                continue
            pendente = None

        achou_artigo = re.match(r"^Art\.\s*(\d+)(?:\s*[-–]\s*([A-Z]))?(?:\.|º|\.º)?\s*(.*)", linha)

        if achou_artigo:
            fechar_artigo()

            numero_base = achou_artigo.group(1)
            letra = (achou_artigo.group(2) or "").upper()
            numero = f"{numero_base}-{letra}" if letra else numero_base
            ordem = ordem_artigo(numero)
            capitulo = combinar_heading(h.get("capituloNumero"), h.get("capituloTitulo")) or "Código Nacional de Normas"

            artigo_atual = {
                "id": f"cnj-art-{numero.lower()}",
                "numero": f"Art. {numero}",
                "ordem": ordem,
                "tipo": "artigo",
                "capitulo": capitulo,
                "secao": h.get("secao", ""),
                "areas": [],
                "temas": [],
                "norma": True,
                "notas": [],
                "parte": h.get("parte", ""),
                "livro": h.get("livro", ""),
                "livroTitulo": h.get("livroTitulo", ""),
                "titulo": h.get("titulo", ""),
                "tituloTitulo": h.get("tituloTitulo", ""),
                "capituloNumero": h.get("capituloNumero", ""),
                "capituloTitulo": h.get("capituloTitulo", ""),
                "secaoTitulo": h.get("secaoTitulo", ""),
                "subsecao": h.get("subsecao", ""),
                "subsecaoTitulo": h.get("subsecaoTitulo", ""),
                "estrutura": estrutura_cnj(h),
                "_linhas": [linha],
            }

        elif artigo_atual is not None:
            artigo_atual["_linhas"].append(linha)

    fechar_artigo()

    if artigos and artigos[0]["texto"].lower().startswith("art. 1.º fica aprovado"):
        artigos = [a for a in artigos if not a["texto"].lower().startswith("art. 1.º fica aprovado")]

    return artigos



# Parser revisado para as Normas CGJ-SP.
# Motivo: o texto extraído em fluxo simples mistura notas de rodapé e listas internas.
# Esta versão usa coordenadas do PDF para separar corpo, notas e cabeçalhos.
def parse_sp_pdf(pdf_bytes):
    print("Organizando Normas da Corregedoria de São Paulo com parser por coordenadas...")

    def is_header_footer_sp_coord(t):
        if re.match(r"^Cap\.\s*[–-]\s*[XVI]+$", t):
            return True
        if re.match(r"^\d+$", t):
            return True
        if t in {
            "PROVIMENTO Nº 58/89",
            "Sumário",
            "CORREGEDORIA GERAL DA JUSTIÇA DO ESTADO DE SÃO PAULO",
        }:
            return True
        return False

    def is_section_line_sp_coord(t):
        return bool(
            re.match(r"^(SEÇÃO|Seção)\s+[IVXLCDM]+\b", t, re.I)
            or re.match(r"^(Subseção|SUBSEÇÃO|Sub subseção)\s+[IVXLCDM]+\b", t, re.I)
        )

    def item_num_sp_coord(t):
        m = re.match(r"^(\d+(?:\.[A-Z])?(?:\.[0-9A-Z]+)*\.?|\d+[A-Z](?:\.\d+)*)\s+", t)
        if not m:
            return None
        n = m.group(1).rstrip(".")
        prefix = m.group(1)
        if "." not in prefix and not re.match(r"^\d+[A-Z]$", n):
            return None
        return n

    def val_item_sp_coord(n):
        vals = []
        for part in re.split(r"\.", n):
            m = re.match(r"^(\d+)([A-Z])?$", part)
            if m:
                v = int(m.group(1))
                if m.group(2):
                    v += (ord(m.group(2)) - 64) / 100
                vals.append(v)
            elif re.match(r"^[A-Z]$", part):
                vals.append((ord(part) - 64) / 100)
        if not vals:
            return 0
        v = vals[0]
        divisor = 1000
        for x in vals[1:]:
            v += x / divisor
            divisor *= 1000
        return v

    def ref_nums_sp_coord(text):
        refs = set()
        # Captura chamadas de nota no corpo do item. Evita confundir o número inicial do item
        # e números de sublistas como "1 - finalidade do tratamento".
        for m in re.finditer(
            r"(?<!^)(?<![\d./-])(\d{1,4})(?!\.[A-Z0-9])(?=(?:[ \t]*\n\n)|\s*(?:[.;:,)]|$))",
            text,
        ):
            if m.start(1) <= 1:
                continue
            refs.add(str(int(m.group(1))))
        return refs

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_notes = {}
    artigos = []
    capitulo_atual = None
    secao_atual = ""
    item_atual = None
    pending_sec = None
    pending_chap_title = False
    last_top_by_cap = {}

    def fechar_item():
        nonlocal item_atual
        if not item_atual:
            return
        item_atual["texto"] = formatar_paragrafos(item_atual.pop("_linhas"))
        item_atual.pop("_num", None)
        artigos.append(item_atual)
        item_atual = None

    for page_index in range(20, len(doc)):
        linhas = []
        for bloco in doc[page_index].get_text("dict").get("blocks", []):
            for linha_pdf in bloco.get("lines", []):
                texto_linha = limpar_linha(" ".join(span.get("text", "") for span in linha_pdf.get("spans", [])))
                if texto_linha:
                    linhas.append((linha_pdf["bbox"][1], linha_pdf["bbox"][0], texto_linha))

        linhas.sort(key=lambda z: z[0])

        foot_start = None
        for y, x, linha in linhas:
            if (
                y > 650
                and re.match(r"^\d{1,4}\s+\S", linha)
                and not re.match(r"^\d+\.", linha)
                and not re.match(r"^\d+$", linha)
            ):
                foot_start = y
                break

        corpo = []
        rodape = []
        for y, x, linha in linhas:
            if is_header_footer_sp_coord(linha):
                continue
            if foot_start is not None and y >= foot_start - 1:
                rodape.append(linha)
            elif y < 785:
                corpo.append((x, linha))

        nota_atual = None
        for linha in rodape:
            m = re.match(r"^(\d{1,4})\s+(.*)", linha)
            if m and not re.match(r"^\d+\.", linha):
                nota_atual = str(int(m.group(1)))
                all_notes[nota_atual] = m.group(2).strip()
            elif nota_atual:
                all_notes[nota_atual] += " " + linha

        for x, linha in corpo:
            achou_capitulo = re.match(r"^CAPÍTULO\s+([XVI]+)\b", linha, re.I)
            if achou_capitulo:
                romano = achou_capitulo.group(1).upper()
                if romano in CAPITULOS_SP:
                    fechar_item()
                    capitulo_atual = romano
                    secao_atual = ""
                    pending_sec = None
                    pending_chap_title = True
                continue

            if not capitulo_atual:
                continue

            if is_section_line_sp_coord(linha):
                fechar_item()
                pending_sec = linha.title()
                secao_atual = pending_sec
                continue

            numero = item_num_sp_coord(linha)

            if pending_sec and not numero:
                if len(linha) < 120:
                    secao_atual = pending_sec + "\n" + linha.title()
                    pending_sec = None
                    continue

            if pending_chap_title and not numero:
                continue

            if numero:
                top_match = re.match(r"^(\d+)", numero)
                top = int(top_match.group(1)) if top_match else 0
                last_top = last_top_by_cap.get(capitulo_atual, 0)
                current_num = item_atual.get("_num") if item_atual else ""
                current_top_match = re.match(r"^(\d+)", current_num) if current_num else None
                current_top = int(current_top_match.group(1)) if current_top_match else 0

                is_subitem_of_current = bool(
                    item_atual
                    and top == current_top
                    and (
                        numero.startswith(current_num + ".")
                        or re.match(rf"^{current_top}\.[A-Z](?:\.|$)", numero)
                    )
                )
                is_top_level_start = ("." not in numero and x < 150) or re.match(r"^\d+\.[A-Z]$", numero)

                accept_new_item = False
                if last_top == 0:
                    accept_new_item = True
                elif is_subitem_of_current:
                    accept_new_item = True
                elif top > last_top and is_top_level_start:
                    accept_new_item = True
                elif top == last_top and re.match(r"^\d+\.[A-Z]$", numero):
                    accept_new_item = True

                if not accept_new_item and item_atual is not None:
                    item_atual["_linhas"].append(linha)
                    continue

                if "." not in numero or re.match(r"^\d+\.[A-Z]$", numero):
                    last_top_by_cap[capitulo_atual] = max(last_top, top)

                fechar_item()
                pending_chap_title = False
                pending_sec = None
                item_id = f"sp-cap-{capitulo_atual.lower()}-item-{numero.lower().replace('.', '-')}"

                item_atual = {
                    "id": item_id,
                    "numero": f"Cap. {capitulo_atual}, item {numero}",
                    "ordem": ORDEM_SP[capitulo_atual] + val_item_sp_coord(numero),
                    "tipo": "item",
                    "capitulo": CAPITULOS_SP[capitulo_atual],
                    "secao": secao_atual,
                    "areas": [AREAS_SP[capitulo_atual]],
                    "temas": [],
                    "norma": True,
                    "notas": [],
                    "_num": numero,
                    "_linhas": [linha],
                }

            elif item_atual is not None:
                if re.match(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 ,;()\-/]+$", linha) and len(linha) < 140:
                    continue
                item_atual["_linhas"].append(linha)

    fechar_item()

    for artigo in artigos:
        refs = ref_nums_sp_coord(artigo.get("texto", ""))
        artigo["notas"] = [
            f"{n} {all_notes[n]}"
            for n in sorted(refs, key=lambda v: int(v))
            if n in all_notes
        ]

    return artigos

def github_get_file(path):
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    resposta = requests.get(
        url,
        headers=headers,
        params={"ref": GITHUB_BRANCH},
        timeout=60,
    )

    if resposta.status_code == 404:
        return None

    resposta.raise_for_status()
    return resposta.json()


def github_put_file(path, content_bytes, message, existing_sha=None):
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
        "branch": GITHUB_BRANCH,
    }

    if existing_sha:
        payload["sha"] = existing_sha

    resposta = requests.put(url, headers=headers, json=payload, timeout=120)
    resposta.raise_for_status()
    return resposta.json()


def json_antigo_tem_mesmo_hash(path, novo_hash, parser_version=None):
    existente = github_get_file(path)

    if not existente:
        return False, None

    try:
        conteudo = base64.b64decode(existente["content"]).decode("utf-8")
        payload = json.loads(conteudo)
        return payload.get("sha256") == novo_hash and (not parser_version or payload.get("parserVersion") == parser_version), existente["sha"]
    except Exception:
        return False, existente["sha"]


def atualizar_base(nome, source_url, target_path, pdf_bytes, artigos, parser_version=None):
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    mesmo_hash, file_sha = json_antigo_tem_mesmo_hash(target_path, sha256, parser_version)

    if mesmo_hash:
        print(f"{nome}: sem alteração. Nenhum commit será feito.")
        return

    if len(artigos) < 20:
        raise RuntimeError(f"{nome}: poucos itens extraídos. Conferir extração antes de publicar.")

    payload = {
        "source": source_url,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "sha256": sha256,
        "totalItems": len(artigos),
        "parserVersion": parser_version or "default",
        "articles": artigos,
    }

    content_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    github_put_file(
        target_path,
        content_bytes,
        f"Atualiza {nome} em {datetime.now().strftime('%d/%m/%Y')}",
        existing_sha=file_sha,
    )

    print(f"{nome}: atualizado com {len(artigos)} itens.")


def main():
    conferir_variaveis()

    print("Iniciando atualização das normas.")

    pdf_sp = baixar_arquivo(TJSP_URL)
    artigos_sp = parse_sp_pdf(pdf_sp)

    atualizar_base(
        "Normas CGJ-SP",
        TJSP_URL,
        "dados/normas-sp.json",
        pdf_sp,
        artigos_sp,
        parser_version="sp-pymupdf-footnotes-v3-hierarchy-lines",
    )

    cnj_pdf_url = descobrir_pdf_compilado_cnj()
    pdf_cnj = baixar_arquivo(cnj_pdf_url)
    texto_cnj = extrair_texto_pdf(pdf_cnj)
    artigos_cnj = parse_cnj(texto_cnj)

    # O parserVersion permite republicar o JSON quando o formato da extração muda, mesmo se o PDF não mudou.
    atualizar_base(
        "Código Nacional de Normas",
        cnj_pdf_url,
        "dados/normas-nacional.json",
        pdf_cnj,
        artigos_cnj,
        parser_version=PARSER_VERSION,
    )

    print("Rotina concluída.")


if __name__ == "__main__":
    main()
