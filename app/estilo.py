"""Identidade visual por livro: colhe do arquivo de origem a capa, as fontes e o CSS, e guarda em <livro>/estilo/.

    python app/estilo.py <pasta-do-livro>      colhe de novo (o pipeline já faz isso no diagnóstico)

Fica em <livro>/estilo/:
  capa.<ext>      a capa do original
  fontes/         as fontes embutidas no original
  original.css    o CSS do original, só para consulta
  estilo.json     o que ferramentas/construir.py usa: capa, fonte dos títulos, fonte do texto
Tudo ali pode ser trocado à mão (outra capa, outra fonte); sem a pasta, o livro sai com o estilo padrão.
De EPUB colhe capa, fontes e CSS. De PDF e DOCX colhe o tamanho da página e o NOME da fonte do texto, trocada pela equivalente livre (nenhuma fonte é extraída).
"""
import json, posixpath, re, sys, zipfile
from pathlib import Path


def _fontes_da_familia(css, familia):
    """{regular|bold|italic|bolditalic: arquivo} a partir das regras @font-face do CSS original."""
    out = {}
    for bloco in re.findall(r'@font-face\s*\{(.*?)\}', css, re.S | re.I):
        fam = re.search(r'font-family:\s*["\']?([^;"\']+)', bloco, re.I)
        src = re.search(r'url\(\s*["\']?([^)"\']+)', bloco, re.I)
        if not fam or not src or fam[1].strip().lower() != familia.lower():
            continue
        negrito = bool(re.search(r'font-weight:\s*(bold|[6-9]00)', bloco, re.I))
        italico = bool(re.search(r'font-style:\s*(italic|oblique)', bloco, re.I))
        out[('bold' if negrito else '') + ('italic' if italico else '') or 'regular'] = posixpath.basename(src[1])
    return out


def _familia_de(css, seletores, familias):
    """Primeira família embutida usada numa regra cujo seletor casa com `seletores` (ex.: títulos)."""
    for sel, corpo in re.findall(r'([^{}@]+)\{([^{}]*)\}', re.sub(r'@font-face\s*\{.*?\}', '', css, flags=re.S | re.I)):
        if re.search(seletores, sel, re.I):
            ff = re.search(r'font-family:\s*([^;]+)', corpo, re.I)
            for f in familias:
                if ff and f.lower() in ff[1].lower():
                    return f
    return None


def colhe(p):
    """Lê o EPUB de origem do livro em p e grava a pasta estilo/. Devolve o dicionário gravado em estilo.json (ou None)."""
    epub = next(iter(sorted((p / 'fonte').glob('*.epub'))), None)
    if not epub:
        return None
    z = zipfile.ZipFile(epub)
    opf_nome = re.search(r'full-path="([^"]+)"', z.read('META-INF/container.xml').decode('utf-8', 'replace'))[1]
    opf = z.read(opf_nome).decode('utf-8', 'replace')
    itens = {m[2] if m[1] == 'id' else m[4]: (m[4] if m[1] == 'id' else m[2])          # id -> href, qualquer que seja a ordem dos atributos
             for m in re.finditer(r'<item\b[^>]*?\b(id|href)="([^"]+)"[^>]*?\b(id|href)="([^"]+)"', opf)}
    resolve = lambda href: posixpath.normpath(posixpath.join(posixpath.dirname(opf_nome), href))      # noqa: E731
    dest = p / 'estilo'
    (dest / 'fontes').mkdir(parents=True, exist_ok=True)
    est = {'origem': epub.name}

    capa_id = re.search(r'<meta[^>]*name="cover"[^>]*content="([^"]+)"', opf) or re.search(r'<meta[^>]*content="([^"]+)"[^>]*name="cover"', opf)
    capa = itens.get(capa_id[1]) if capa_id else None
    if not capa:
        m = re.search(r'<item\b[^>]*properties="[^"]*cover-image[^"]*"[^>]*>', opf)
        capa = re.search(r'href="([^"]+)"', m[0])[1] if m else None
    if capa and resolve(capa) in z.namelist():
        est['capa'] = 'capa' + Path(capa).suffix.lower()
        est['capa_origem'] = posixpath.basename(capa)          # para tirar a capa do meio do texto
        (dest / est['capa']).write_bytes(z.read(resolve(capa)))

    css = ''
    for href in itens.values():
        nome = resolve(href)
        if nome not in z.namelist():
            continue
        if href.lower().endswith(('.ttf', '.otf')):
            (dest / 'fontes' / posixpath.basename(href)).write_bytes(z.read(nome))
        elif href.lower().endswith('.css'):
            css += f'/* {href} */\n' + z.read(nome).decode('utf-8', 'replace') + '\n'
    if css:
        (dest / 'original.css').write_text(css, encoding='utf-8')
    familias = [f for f in dict.fromkeys(m.strip() for m in re.findall(r'@font-face\s*\{[^}]*?font-family:\s*["\']?([^;"\']+)', css, re.S | re.I))
                if all((dest / 'fontes' / a).exists() for a in _fontes_da_familia(css, f).values()) and _fontes_da_familia(css, f)]
    for chave, seletores in (('titulos', r'\bh[1-4]\b'), ('texto', r'(^|[\s,])(body|html|p|\*)\s*(,|$)')):
        fam = _familia_de(css, seletores, familias)
        if fam:
            est[chave] = {'familia': fam, **_fontes_da_familia(css, fam)}
    (dest / 'estilo.json').write_text(json.dumps(est, ensure_ascii=False, indent=1), encoding='utf-8')
    return est


# nome da fonte do original -> família livre equivalente que vem com o TeX (TeX Gyre). Nenhuma fonte é tirada do arquivo: só o nome é lido.
EQUIVALENTES = (('times|roman|liberation serif|nimbus rom|georgia|cambria', 'termes'), ('palatino|pagella|book antiqua|garamond|minion|caslon|sabon|bembo|baskerville|goudy|jenson', 'pagella'),
                ('century|schoolbook', 'schola'), ('bookman', 'bonum'), ('helvetica|arial|calibri|verdana|sans|univers|frutiger|gothic', 'heros'))


def _tex(nome):
    """Arquivos da família TeX Gyre equivalente ao nome de fonte dado, ou None se não há equivalente claro."""
    for padrao, gyre in EQUIVALENTES:
        if re.search(padrao, nome or '', re.I):
            return {'familia': f'TeX Gyre {gyre.capitalize()}', **{k: f'texgyre{gyre}-{k}.otf' for k in ('regular', 'bold', 'italic', 'bolditalic')}}
    return None


def colhe_medidas(p):
    """De PDF e DOCX de origem: o tamanho da página (em polegadas) e a fonte do texto, trocada pela equivalente livre. Junta ao estilo.json."""
    est, dest = le(p), p / 'estilo'
    pdf = next(iter(sorted((p / 'fonte').glob('*.pdf'))), None)
    docx = next(iter(sorted((p / 'fonte').glob('*.docx'))), None)
    largura = altura = nome = None
    if pdf:
        import pymupdf
        doc = pymupdf.open(str(pdf))
        meio = [doc[i] for i in range(len(doc) // 4, max(len(doc) // 4 + 1, min(len(doc), len(doc) // 4 + 30)))]
        lados = sorted((round(pg.rect.width / 72, 2), round(pg.rect.height / 72, 2)) for pg in meio)
        largura, altura = lados[len(lados) // 2]
        uso = {}
        for pg in meio:
            for b in pg.get_text('dict')['blocks']:
                for l in b.get('lines', []):
                    for sp in l['spans']:
                        uso[sp['font']] = uso.get(sp['font'], 0) + len(sp['text'])
        nome = max(uso, key=uso.get) if uso else None
    elif docx:
        z = zipfile.ZipFile(docx)
        m = re.search(r'<w:pgSz\b[^>]*?w:w="(\d+)"[^>]*?w:h="(\d+)"', z.read('word/document.xml').decode('utf-8', 'replace'))
        if m:
            largura, altura = round(int(m[1]) / 1440, 2), round(int(m[2]) / 1440, 2)
        fonte = re.search(r'<w:rFonts\b[^>]*?w:ascii="([^"]+)"', z.read('word/styles.xml').decode('utf-8', 'replace')) if 'word/styles.xml' in z.namelist() else None
        nome = fonte[1] if fonte else None
    else:
        return est
    est.setdefault('origem', (pdf or docx).name)
    if largura and 4 <= largura <= 8.5 and 6 <= altura <= 11.7:      # fora disso (cartaz, slide) o livro sai no tamanho padrão
        est['pagina'] = [largura, altura]
    if nome:
        est['fonte_original'] = re.sub(r'^[A-Z]{6}\+', '', nome)      # tira o prefixo de subconjunto do PDF (ABCDEF+Garamond)
        if _tex(nome):
            est['texto_tex'] = _tex(nome)
    dest.mkdir(exist_ok=True)
    (dest / 'estilo.json').write_text(json.dumps(est, ensure_ascii=False, indent=1), encoding='utf-8')
    return est


def le(p):
    f = p / 'estilo' / 'estilo.json'
    return json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    assert _tex('ABCDEF+TimesNewRomanPSMT')['regular'] == 'texgyretermes-regular.otf' and _tex('Garamond-Italic')['familia'] == 'TeX Gyre Pagella' and _tex('ZapfDingbats') is None
    alvo = Path(sys.argv[1])
    print(json.dumps(colhe(alvo if alvo.exists() else Path(__file__).resolve().parent.parent / 'livros' / sys.argv[1]), ensure_ascii=False, indent=1))
