"""Prepara um EPUB para a conversão: recupera a estrutura que o arquivo só indica pelo estilo.

Muitos EPUBs não usam <h2> nem notas de verdade: o subtítulo é um <p class="sub-header"> em negrito, e a nota de rodapé
é um par de links que apontam um para o outro. Um conversor comum perde as duas coisas. Aqui, antes do Pandoc:
  - parágrafo de classe "com cara de título" (negrito, curto, pouco usado, ou com nome de título) vira <hN>;
  - cada par chamada ↔ nota vira uma marca ⟦nota:K⟧ no texto e ⟦def:K⟧ no começo da nota.
Depois do Pandoc, notas_e_links() troca as marcas por notas do Markdown ([^K] e [^K]: texto) e tira os links internos
do arquivo de origem (sumário, remissões), que não existem no livro novo. Nenhuma palavra do texto é alterada.

    python app/epub.py livro.epub      -> mostra o que foi reconhecido
"""
import os, re, statistics, sys, tempfile, zipfile
from pathlib import Path

NOME_TITULO = re.compile(r'(^|[-_ ])(sub-?)?(head(er|ing)?|title|titulo|chapter|capitulo|heading)([-_ ]|\d|$)', re.I)
ANCORA = re.compile(r'<a\b([^>]*)>(.*?)</a>', re.S | re.I)


def _attr(attrs, nome):
    m = re.search(rf'\b{nome}\s*=\s*"([^"]*)"', attrs, re.I)
    return m[1] if m else None


def _texto(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', html)).strip()


def prepara(epub):
    """Devolve (caminho de uma cópia temporária do EPUB, já preparada, e um resumo {titulos, notas})."""
    z = zipfile.ZipFile(epub)
    nomes = z.namelist()
    paginas = {n: z.read(n).decode('utf-8', 'replace') for n in nomes if n.lower().endswith(('.xhtml', '.html', '.htm'))}
    css = '\n'.join(z.read(n).decode('utf-8', 'replace') for n in nomes if n.lower().endswith('.css'))
    regra = {m[1]: m[2] for m in re.finditer(r'\.([\w-]+)\s*\{([^}]*)\}', css)}

    # --- notas: âncora A (id=x, href->y) e âncora B (id=y, href->x) apontam uma para a outra
    ancoras = {}                                              # id -> (arquivo, id de destino)
    for arq, html in paginas.items():
        for m in ANCORA.finditer(html):
            i, h = _attr(m[1], 'id'), _attr(m[1], 'href')
            if i and h and '#' in h and len(_texto(m[2])) <= 8:
                ancoras[i] = (arq, h.split('#', 1)[1])
    pares = {i for i, (_, d) in ancoras.items() if d in ancoras and ancoras[d][1] == i}
    numero, definicao = {}, set()                             # id da chamada -> K ; ids que são o começo da nota
    for arq, html in paginas.items():
        for m in re.finditer(r'<(p|div|li|aside)\b[^>]*>\s*(?:<(?!a\b)[^>]+>\s*)*<a\b([^>]*)>', html, re.I):
            i = _attr(m[2], 'id')
            if i in pares:
                definicao.add(i)
    for arq in sorted(paginas):                               # numera as chamadas na ordem em que aparecem
        for m in ANCORA.finditer(paginas[arq]):
            i = _attr(m[1], 'id')
            if i in pares and i not in definicao and ancoras[i][1] in definicao:
                numero[i] = len(numero) + 1

    def troca_ancora(m):
        i = _attr(m[1], 'id')
        if i in numero:
            return f'⟦nota:{numero[i]}⟧'
        if i in definicao and ancoras[i][1] in numero:
            return f'⟦def:{numero[ancoras[i][1]]}⟧'
        return m[0]

    # --- títulos: classes de parágrafo que só o estilo distingue
    usos = {}
    for html in paginas.values():
        for m in re.finditer(r'<p\b[^>]*\bclass="([^"]+)"[^>]*>(.*?)</p>', html, re.S | re.I):
            usos.setdefault(m[1].split()[0], []).append(len(_texto(m[2])))
    total = sum(len(v) for v in usos.values()) or 1
    candidatas = {}
    for classe, tam in usos.items():
        r = regra.get(classe, '')
        negrito = bool(re.search(r'font-weight:\s*(bold|[6-9]00)', r))
        curto = statistics.median(tam) <= 90 and max(tam) <= 220
        if curto and len(tam) / total <= 0.2 and (negrito or NOME_TITULO.search(classe)):
            em = re.search(r'font-size:\s*([\d.]+)', r)
            candidatas[classe] = float(em[1]) if em else 1.0
    fundo = max([int(n) for html in paginas.values() for n in re.findall(r'<h([1-6])\b', html, re.I)] or [0])
    ordem = sorted(candidatas, key=lambda c: -candidatas[c])
    nivel = {c: min(6, fundo + 1 + k) for k, c in enumerate(ordem)}

    def troca_p(m):
        classe = m[1].split()[0]
        return f'<h{nivel[classe]}>{m[2]}</h{nivel[classe]}>' if classe in nivel and _texto(m[2]) else m[0]

    fd, nome_tmp = tempfile.mkstemp(suffix='.epub')
    os.close(fd)
    tmp = Path(nome_tmp)
    with zipfile.ZipFile(tmp, 'w') as novo:
        novo.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        for n in nomes:
            if n == 'mimetype':
                continue
            dado = z.read(n)
            if n in paginas:
                html = ANCORA.sub(troca_ancora, paginas[n])
                html = re.sub(r'<p\b[^>]*\bclass="([^"]+)"[^>]*>(.*?)</p>', troca_p, html, flags=re.S | re.I)
                dado = html.encode('utf-8')
            novo.writestr(n, dado, compress_type=zipfile.ZIP_DEFLATED)
    return tmp, {'titulos': {c: (nivel[c], len(usos[c])) for c in ordem}, 'notas': len(numero)}


FB2 = 'http://www.gribuser.ru/xml/fictionbook/2.0'


def fb2_arruma(dados):
    """FB2 com texto solto fora das seções (o próprio Pandoc escreve assim quando o livro de origem não aninha os títulos, e o
    leitor de FB2 dele ignora esse texto: visto num livro de 194 mil caracteres que chegava com 388). O texto solto vira parágrafo
    e o que está depois de uma seção, no corpo, passa para dentro dela. Nenhuma palavra muda. Devolve (bytes, caracteres de texto)."""
    import xml.etree.ElementTree as ET
    ET.register_namespace('', FB2); ET.register_namespace('l', 'http://www.w3.org/1999/xlink')
    raiz = ET.fromstring(dados)
    q = lambda t: f'{{{FB2}}}{t}'      # noqa: E731

    def com_paragrafos(pai):
        """Filhos do elemento, com o texto solto (antes, entre e depois deles) já dentro de <p>."""
        saida, solto = [], pai.text
        pai.text = None
        for f in [None] + list(pai):
            if f is not None:
                saida.append(f); solto, f.tail = f.tail, None
            if solto and solto.strip():
                e = ET.Element(q('p')); e.text = solto.strip(); saida.append(e)
        return saida

    total = 0
    for corpo in raiz.iter(q('body')):
        for sec in list(corpo.iter(q('section'))):
            sec[:] = com_paragrafos(sec)
        filhos, secao = [], None
        for f in com_paragrafos(corpo):
            if f.tag == q('section'):
                secao = f; filhos.append(f)
            elif f.tag in (q('title'), q('epigraph'), q('image')) and secao is None:
                filhos.append(f)
            else:                          # parágrafo, poema, citação… fora de seção: vai para a seção de antes (ou abre uma)
                if secao is None:
                    secao = ET.Element(q('section')); filhos.append(secao)
                secao.append(f)
        corpo[:] = filhos
        total += len(''.join(corpo.itertext()))
    return ET.tostring(raiz, encoding='utf-8', xml_declaration=True), total


def mobi_titulos(html):
    """MOBI antigo não tem <h1>: o título de capítulo é um parágrafo só com <font size="N"><b>…</b></font>. Vira título de verdade
    (letra maior = nível mais alto); o texto não muda."""
    def troca(m):
        n, texto = int(m[1] or m[3]), m[2] or m[4]
        return f'<h{min(6, max(1, 8 - n))}>{texto}</h{min(6, max(1, 8 - n))}>' if n >= 4 and 0 < len(_texto(texto)) <= 200 else m[0]
    return re.sub(r'<p\b[^>]*>\s*(?:<font size="(\d)">\s*<b>(.*?)</b>\s*</font>|<b>\s*<font size="(\d)">(.*?)</font>\s*</b>)\s*</p>', troca, html, flags=re.S | re.I)


def notas_e_links(md):
    """Marcas -> notas do Markdown; links internos do arquivo de origem -> só o texto."""
    saida = []
    for linha in md.split('\n'):
        m = re.match(r'^(>\s*)?⟦def:(\d+)⟧\s*(.*)', linha)
        saida.append(f'[^{m[2]}]: {m[3]}' if m else linha)
    md = re.sub(r'\\?⟦nota:(\d+)\\?⟧', r'[^\1]', '\n'.join(saida))
    md = re.sub(r'⟦def:\d+⟧\s*', '', md)                                  # marca de nota fora do começo do parágrafo: só some
    # link para dentro do próprio EPUB (#âncora ou arquivo.html#âncora): fica o texto; endereços da internet não são tocados
    # (o texto do link pode trazer colchetes escapados ou um par de colchetes dentro, como em "Capítulo 6[1]")
    return re.sub(r'(?<!!)\[((?:[^\]\[\\]|\\.|\[(?:[^\]\[\\]|\\.)*\])*)\]\((?![a-z][a-z0-9+.-]*:)(?:[^()\s]|\([^()\s]*\))*\)', r'\1', md)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    assert notas_e_links('Texto⟦nota:3⟧ e [cap. 2](part2.html#x), [site](http://a.b/c) ![i](img/a.png)\n\n⟦def:3⟧ A nota.') == \
        'Texto[^3] e cap. 2, [site](http://a.b/c) ![i](img/a.png)\n\n[^3]: A nota.'
    torto = (f'<FictionBook xmlns="{FB2}"><body><title><p>T</p></title><section><title><p>Um</p></title>data solta</section>'
             '<p>Primeiro.</p>fora<p>Segundo.</p><section><p>Certo.</p></section><p>Terceiro.</p></body></FictionBook>').encode()
    certo, n = fb2_arruma(torto)
    certo = certo.decode('utf-8')
    assert '</section><p>' not in certo and '</section>fora' not in certo and n == len('TUmdata soltaPrimeiro.foraSegundo.Certo.Terceiro.'), certo
    assert certo.count('<section>') == 2 and '<p>data solta</p><p>Primeiro.</p><p>fora</p><p>Segundo.</p></section>' in certo and certo.endswith('<p>Terceiro.</p></section></body></FictionBook>'), certo
    assert fb2_arruma(certo.encode())[0].decode('utf-8') == certo                          # o que já está certo não muda
    assert mobi_titulos('<p align="center"><font size="4"><b>Part 1</b></font></p><p>Texto <b>forte</b>.</p><p><font size="2"><b>nota</b></font></p>') == \
        '<h4>Part 1</h4><p>Texto <b>forte</b>.</p><p><font size="2"><b>nota</b></font></p>'
    if len(sys.argv) > 1:
        tmp, resumo = prepara(sys.argv[1])
        print(resumo)
        tmp.unlink()
    print('ok')
