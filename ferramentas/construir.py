"""Gera EPUB e PDF de um livro a partir de texto/livro.md (Pandoc + MiKTeX/XeLaTeX).

  python ferramentas/construir.py livros/<pasta-do-livro> [epub|pdf|tudo|anotada|docx|odt|html|fb2|azw3|todos]

Saída em livros/<pasta-do-livro>/saida/. O Markdown é a única fonte do texto;
nada aqui altera palavras, só formata.
  anotada = edição à parte com "Notas do editor" (texto/anotacoes.md); ver ferramentas/anotar.py
"""
import json, os, shutil, subprocess, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FERR = Path(__file__).resolve().parent
EXTRA = [Path.home() / 'AppData/Local/Pandoc', Path.home() / 'AppData/Local/Programs/MiKTeX/miktex/bin/x64']
os.environ['PATH'] += os.pathsep + os.pathsep.join(map(str, EXTRA))
sys.path.insert(0, str(FERR))

# desliga extensões que mexeriam no texto: aspas "inteligentes", $matemática$, @citações, LaTeX cru
LEITOR = 'markdown-smart-tex_math_dollars-raw_tex-citations'


def pandoc(livro, md, args):
    cmd = ['pandoc', '-f', LEITOR, str(md), '--lua-filter', str(FERR / 'filtros/livro.lua'),
           '--resource-path', str(livro / 'texto'), '--standalone', '--toc', '--toc-depth=2'] + args
    print(' '.join(cmd[:4]), '...', args[-1])
    subprocess.run(cmd, check=True, cwd=livro / 'texto')


def estilo(livro):
    """Identidade do livro (capa e fontes colhidas do original por app/estilo.py), se houver: <livro>/estilo/estilo.json."""
    f = livro / 'estilo' / 'estilo.json'
    return json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}


def epub(livro, md, nome):
    est = estilo(livro)
    extra = []
    if est.get('capa'):
        extra += ['--epub-cover-image', str(livro / 'estilo' / est['capa'])]
    css = ''
    for chave, seletor in (('titulos', 'h1, h2, h3, h4, h5, h6'), ('texto', 'body')):
        fam = est.get(chave)
        for variante, arq in ((v, a) for v, a in (fam or {}).items() if v != 'familia'):
            extra += ['--epub-embed-font', str(livro / 'estilo' / 'fontes' / arq)]
            css += (f"@font-face {{ font-family: '{fam['familia']}'; font-weight: {'bold' if 'bold' in variante else 'normal'}; "
                    f"font-style: {'italic' if 'italic' in variante else 'normal'}; src: url('../fonts/{arq}'); }}\n")
        if fam:
            css += f"{seletor} {{ font-family: '{fam['familia']}', serif; }}\n"
    proprio = livro / 'estilo' / 'epub.css'            # CSS escrito à mão para este livro, se existir, vale por último
    if css:
        (livro / 'saida' / '.estilo.css').write_text(css, encoding='utf-8')
        extra += ['--css', str(livro / 'saida' / '.estilo.css')]
    if proprio.exists():
        extra += ['--css', str(proprio)]
    pandoc(livro, md, ['-t', 'epub3', '--css', str(FERR / 'estilo/epub.css')] + extra + ['--split-level=1',
                       '-o', str(livro / 'saida' / f'{nome}.epub')])


def simples(livro, md, nome, fmt):
    """DOCX, ODT, HTML (um arquivo só, com imagens embutidas) e FB2: saída direta do Pandoc, mesmo texto e mesmo filtro."""
    extra = ['--embed-resources', '--css', str(FERR / 'estilo/epub.css')] if fmt == 'html' else []
    pandoc(livro, md, ['-t', {'html': 'html5'}.get(fmt, fmt)] + extra + ['-o', str(livro / 'saida' / f'{nome}.{fmt}')])


def azw3(livro, md, nome):
    """Kindle antigo: converte o EPUB já gerado com o ebook-convert do Calibre, se estiver instalado. (Kindle atual lê EPUB.)"""
    conv = shutil.which('ebook-convert') or next((str(c) for c in [Path('C:/Program Files/Calibre2/ebook-convert.exe')] if c.exists()), None)
    if not conv:
        sys.exit('AZW3 precisa do Calibre instalado (ebook-convert). O Kindle atual aceita o EPUB direto.')
    if not (livro / 'saida' / f'{nome}.epub').exists():
        epub(livro, md, nome)
    subprocess.run([conv, str(livro / 'saida' / f'{nome}.epub'), str(livro / 'saida' / f'{nome}.azw3')], check=True)


def motor_pdf():
    """Argumentos do Pandoc para o motor de PDF: XeLaTeX (MiKTeX) se estiver instalado; senão o Tectonic, um executável só, em ferramentas/bin
    ou no PATH. O Tectonic busca os pacotes na internet quando faltam: aqui ele roda só com o que já está guardado (--only-cached), para o
    app não ir à rede por conta própria. Quem guarda os pacotes é "construir.py --preparar-tectonic", passo declarado do instalador.
    ESTANTE_PDF=tectonic força o Tectonic mesmo havendo XeLaTeX."""
    tect = shutil.which('tectonic') or next((str(c) for c in [FERR / 'bin' / 'tectonic.exe'] if c.exists()), None)
    if tect and (os.environ.get('ESTANTE_PDF') == 'tectonic' or not shutil.which('xelatex')):
        return [f'--pdf-engine={tect}'] + ([] if os.environ.get('ESTANTE_TECTONIC_REDE') else ['--pdf-engine-opt=--only-cached'])
    return ['--pdf-engine=xelatex']


TECTONIC = ('https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-x86_64-pc-windows-msvc.zip',
            'f61ce51f0b0ade1015b7de7ef368541c5424e9756ecbd0d7af97d6d48030845f')
AMOSTRA = """---
title: Amostra
author: Estante
lang: pt-BR
---

# Capítulo

Um parágrafo com *itálico*, **negrito**, travessão — e nota.[^1]

> Uma citação em bloco.

![Figura](ponto.png)

| a | b |
|---|---|
| 1 | 2 |

## Seção

1. Item numerado
2. Outro item

[^1]: Texto da nota.
"""


def preparar_tectonic():
    """Passo do instalador (o único momento em que o Tectonic usa a rede): baixa o executável, confere o hash e gera um livro de amostra,
    o que guarda no computador os pacotes de que os livros precisam. Depois disso o PDF é gerado só com o que ficou guardado."""
    import hashlib, io, tempfile, urllib.request, zipfile
    exe = FERR / 'bin' / 'tectonic.exe'
    if not exe.exists() and not shutil.which('tectonic'):
        dados = urllib.request.urlopen(TECTONIC[0], timeout=120).read()
        if hashlib.sha256(dados).hexdigest() != TECTONIC[1]:
            sys.exit('o arquivo do Tectonic não confere com o hash esperado: nada foi instalado')
        exe.parent.mkdir(exist_ok=True)
        exe.write_bytes(zipfile.ZipFile(io.BytesIO(dados)).read('tectonic.exe'))
    os.environ.update(ESTANTE_PDF='tectonic', ESTANTE_TECTONIC_REDE='1')
    with tempfile.TemporaryDirectory() as t:
        livro = Path(t) / 'amostra'
        import base64
        ponto = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
        for d in ('texto', 'saida', 'estilo'):
            (livro / d).mkdir(parents=True)
        (livro / 'texto' / 'livro.md').write_text(AMOSTRA, encoding='utf-8')
        (livro / 'texto' / 'ponto.png').write_bytes(ponto); (livro / 'estilo' / 'capa.png').write_bytes(ponto)
        (livro / 'config.json').write_text('{"quebra_secao": true}', encoding='utf-8')
        # uma passada por família de letra que o app pode escolher: cada fonte só fica guardada depois de usada uma vez
        for gyre in ('pagella', 'termes', 'schola', 'bonum', 'heros'):
            (livro / 'estilo' / 'estilo.json').write_text(json.dumps({'capa': 'capa.png', 'texto_tex': {k: f'texgyre{gyre}-{k}.otf' for k in ('regular', 'bold', 'italic', 'bolditalic')}}), encoding='utf-8')
            pdf(livro, livro / 'texto' / 'livro.md', 'amostra')
        assert (livro / 'saida' / 'amostra.pdf').stat().st_size > 5000
    print('Tectonic pronto: os pacotes de PDF estão guardados neste computador.')


def pdf(livro, md, nome, pacote=''):
    cfg = {'divisao_topo': 'chapter', 'quebra_secao': False}
    if (livro / 'config.json').exists():
        cfg.update(json.loads((livro / 'config.json').read_text(encoding='utf-8')))
    antes, extra = (['-H', str(FERR / 'estilo/quebra-secao.tex')] if cfg['quebra_secao'] else []), []
    est, tex = estilo(livro), pacote       # pacote: linhas de preâmbulo que este alvo precisa (ex.: paracol)
    pasta = (livro / 'estilo').as_posix()
    if est.get('titulos'):          # títulos na fonte do original
        t = est['titulos']
        opc = ','.join(f'{o}={t[k]}' for k, o in (('bold', 'BoldFont'), ('italic', 'ItalicFont'), ('bolditalic', 'BoldItalicFont')) if k in t)
        tex += (f"\\newfontfamily\\fontetitulos[Path={pasta}/fontes/{',' + opc if opc else ''}]{{{t.get('regular') or next(iter(v for k, v in t.items() if k != 'familia'))}}}\n"
                "\\titleformat{\\chapter}[display]{\\fontetitulos\\centering\\LARGE\\bfseries}{}{0pt}{}\n"
                "\\titleformat{\\section}{\\fontetitulos\\Large\\bfseries\\centering}{}{0pt}{}\n"
                "\\titleformat{\\subsection}{\\fontetitulos\\large\\bfseries\\centering}{}{0pt}{}\n"
                "\\titleformat{\\subsubsection}{\\fontetitulos\\normalsize\\bfseries\\itshape\\centering}{}{0pt}{}\n"
                "\\renewcommand{\\fontedorosto}{\\fontetitulos}\n")
    if est.get('capa'):             # capa do original como primeira página, inteira
        tex += ("\\usepackage{graphicx}\\usepackage{eso-pic}\\let\\cleardoublepage\\clearpage\n"      # sem página em branco numerada depois da capa
                "\\AtBeginDocument{\\AddToShipoutPictureBG*{\\AtPageCenter{\\makebox(0,0){\\includegraphics[width=\\paperwidth,height=\\paperheight,keepaspectratio]"
                f"{{{pasta}/{est['capa']}}}}}}}}}\\thispagestyle{{empty}}\\null\\clearpage}}\n")
    if tex:
        (livro / 'saida' / '.estilo.tex').write_text(tex, encoding='utf-8')
        extra += ['-H', str(livro / 'saida' / '.estilo.tex')]
    corpo = ['-V', 'mainfont=texgyrepagella-regular.otf',
             '-V', 'mainfontoptions=BoldFont=texgyrepagella-bold.otf,ItalicFont=texgyrepagella-italic.otf,BoldItalicFont=texgyrepagella-bolditalic.otf']
    tx = est.get('texto') or {}
    if tx.get('regular') and (livro / 'estilo' / 'fontes' / tx['regular']).is_file():       # fonte do texto escolhida para este livro
        # quando só há o arquivo regular, negrito e itálico são simulados: a ênfase do autor tem de continuar aparecendo
        op = [f"Path={(livro / 'estilo' / 'fontes').as_posix()}/"] + [f"{k}Font={tx.get(c) or tx['regular']}" for k, c in (('Bold', 'bold'), ('Italic', 'italic'), ('BoldItalic', 'bolditalic'))]
        op += ([] if tx.get('bold') else ['BoldFeatures={FakeBold=1.4}']) + ([] if tx.get('italic') else ['ItalicFeatures={FakeSlant=0.18}'])
        corpo = ['-V', f"mainfont={tx['regular']}", '-V', 'mainfontoptions=' + ','.join(op)]
    elif est.get('texto_tex'):      # fonte livre equivalente à do original (colhida pelo nome; vem com o TeX)
        t = est['texto_tex']
        corpo = ['-V', f"mainfont={t['regular']}", '-V', f"mainfontoptions=BoldFont={t['bold']},ItalicFont={t['italic']},BoldItalicFont={t['bolditalic']}"]
    larg, alt = est.get('pagina') or (6, 9)      # tamanho da página do original, em polegadas; as margens acompanham na mesma proporção
    proprio = livro / 'estilo' / 'livro.tex'            # LaTeX escrito à mão para este livro, se existir, vale por último
    if proprio.exists():
        extra += ['-H', str(proprio)]
    motor = motor_pdf()
    try:
        _pdf(livro, md, nome, antes, motor, cfg, extra, corpo, larg, alt)
    except subprocess.CalledProcessError:
        if '--pdf-engine-opt=--only-cached' in motor:
            sys.exit('O Tectonic não achou um pacote entre os que estão guardados neste computador. Ele não vai à internet sozinho: '
                     'rode "python ferramentas/construir.py --preparar-tectonic" (usa a rede) e gere de novo.')
        raise


def _pdf(livro, md, nome, antes, motor, cfg, extra, corpo, larg, alt):
    pandoc(livro, md, antes + motor + [f"--top-level-division={cfg['divisao_topo']}",
           '-H', str(FERR / 'estilo/cabecalho.tex')] + extra + [
           '-V', 'documentclass=book', '-V', 'classoption=openany', '-V', 'fontsize=11pt',
           '-V', f'geometry:paperwidth={larg}in', '-V', f'geometry:paperheight={alt}in',
           '-V', f'geometry:inner={larg * .15:.2f}in', '-V', f'geometry:outer={larg * .117:.2f}in', '-V', f'geometry:top={alt * .089:.2f}in', '-V', f'geometry:bottom={alt * .1:.2f}in',
           *corpo,
           '-V', 'linkcolor=black', '-V', 'urlcolor=black',
           '-o', str(livro / 'saida' / f'{nome}.pdf')])


if __name__ == '__main__':
    if sys.argv[1] == '--preparar-tectonic':
        sys.exit(preparar_tectonic())
    livro = Path(sys.argv[1]).resolve()
    alvo = sys.argv[2] if len(sys.argv) > 2 else 'tudo'
    nome = livro.name
    (livro / 'saida').mkdir(exist_ok=True)
    md = livro / 'texto' / 'livro.md'
    if alvo == 'anotada':
        import anotar
        md = anotar.mesclar(livro)
        nome += '-anotada'
        alvo = 'tudo'
    if alvo == 'bilingue':          # original e tradução no mesmo volume: EPUB, HTML e Word (ver ferramentas/bilingue.py)
        import bilingue
        md = livro / 'saida' / 'bilingue.md'
        md.write_text(bilingue.monta(livro)[0], encoding='utf-8', newline='\n')
        nome += '-bilingue'
        alvo = 'bilingue-formatos'
    if alvo == 'bilingue-colunas':     # PDF: original e tradução lado a lado (paracol); precisa do pacote guardado (--preparar-tectonic)
        import bilingue
        md = livro / 'saida' / 'bilingue-colunas.md'
        md.write_text(bilingue.monta(livro, colunas=True)[0], encoding='utf-8', newline='\n')
        nome += '-bilingue-colunas'
        pdf(livro, md, nome, pacote='\\usepackage{paracol}\n')
        alvo = 'nada'
    try:
        if alvo == 'bilingue-formatos':
            epub(livro, md, nome)
            for fmt in ('docx', 'html'):
                simples(livro, md, nome, fmt)
        if alvo in ('epub', 'tudo', 'todos'):
            epub(livro, md, nome)
        if alvo in ('pdf', 'tudo', 'todos'):
            pdf(livro, md, nome)
        for fmt in ('docx', 'odt', 'html', 'fb2'):
            if alvo in (fmt, 'todos'):
                simples(livro, md, nome, fmt)
        if alvo == 'azw3':
            azw3(livro, md, nome)
    finally:
        if md.name == '.livro-anotado.md':
            md.unlink(missing_ok=True)
