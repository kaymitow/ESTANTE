"""OCR de PDF escaneado ou pasta de imagens, página a página, com Tesseract.

  python ferramentas/ocr.py livros/<livro>/fonte/arquivo.pdf livros/<livro>/ocr/teste --lang por --paginas 8-12
  python ferramentas/ocr.py scan.pdf saida --lang deu+Fraktur --dpi 400 --contraste      # alemão em letra gótica
  python ferramentas/ocr.py pasta-de-imagens saida --lang eng

Idiomas disponíveis em ferramentas/tessdata: por, eng, deu, Fraktur (letra gótica). Combine com "+".
Saída: pagina-NNN.txt (uma por página) e texto.txt (todas, separadas por "=== página N ===").
O OCR é APOIO: todo trecho precisa ser conferido contra o scan antes de entrar em texto/livro.md
(veja .agents/skills/book-translator-ptbr/references/ocr-policy.md).
Dicas: --psm 4 (colunas simples, padrão), --psm 6 (bloco único), --psm 11 (texto esparso);
--contraste ajuda em fotos de página escura; --limiar 150 binariza (preto e branco).
"""
import argparse, os, re, subprocess, sys, tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TESSDATA = RAIZ / 'ferramentas' / 'tessdata'
CANDIDATOS = [Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe'), Path(r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'),
              Path.home() / 'Tesseract-OCR' / 'tesseract.exe']
sys.stdout.reconfigure(encoding='utf-8')


def acha_tesseract():
    for c in CANDIDATOS:
        if c.exists():
            return str(c)
    import shutil
    achado = shutil.which('tesseract')
    if achado:
        return achado
    sys.exit('Tesseract não encontrado. Instale com ferramentas/instaladores/tesseract-ocr-w64-setup-*.exe')


def faixa(txt, total):
    if not txt:
        return list(range(1, total + 1))
    out = []
    for parte in txt.split(','):
        a, _, b = parte.partition('-')
        out += list(range(int(a), int(b or a) + 1))
    return [p for p in out if 1 <= p <= total]


def imagens(entrada, paginas_txt, dpi):
    """Gera (número da página, caminho do PNG) a partir de um PDF ou de uma pasta de imagens."""
    tmp = Path(tempfile.mkdtemp(prefix='ocr_'))
    if entrada.is_dir():
        arqs = sorted(p for p in entrada.iterdir() if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.tif', '.tiff'))
        for n in faixa(paginas_txt, len(arqs)):
            yield n, arqs[n - 1]
        return
    import pymupdf
    doc = pymupdf.open(str(entrada))
    for n in faixa(paginas_txt, len(doc)):
        png = tmp / f'p{n:04d}.png'
        doc[n - 1].get_pixmap(dpi=dpi).save(str(png))
        yield n, png


def prepara(png, contraste, limiar):
    if not (contraste or limiar):
        return png
    from PIL import Image, ImageOps
    im = ImageOps.grayscale(Image.open(png))
    if contraste:
        im = ImageOps.autocontrast(im, cutoff=2)
    if limiar:
        im = im.point(lambda v: 255 if v > limiar else 0)
    novo = Path(str(png) + '.prep.png')
    im.save(novo)
    return novo


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('entrada'); ap.add_argument('saida')
    ap.add_argument('--lang', default='por'); ap.add_argument('--dpi', type=int, default=300)
    ap.add_argument('--paginas', help='ex.: 1-5,9 (padrão: todas)')
    ap.add_argument('--psm', default='4'); ap.add_argument('--contraste', action='store_true')
    ap.add_argument('--limiar', type=int, default=0)
    ap.add_argument('--hocr', action='store_true', help='grava também pagina-NNN.hocr (posição das palavras)')
    a = ap.parse_args()
    tess = acha_tesseract()
    saida = Path(a.saida); saida.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TESSDATA_PREFIX=str(TESSDATA))
    tudo = []
    for n, png in imagens(Path(a.entrada), a.paginas, a.dpi):
        img = prepara(png, a.contraste, a.limiar)
        base = saida / f'pagina-{n:03d}'
        cmd = [tess, str(img), str(base), '-l', a.lang, '--psm', a.psm, '--tessdata-dir', str(TESSDATA)] + (['hocr', 'txt'] if a.hocr else ['txt'])
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, encoding='utf-8', errors='replace')
        if r.returncode:
            sys.exit(f'Falha na página {n}: {r.stderr[-300:]}')
        txt = base.with_suffix('.txt').read_text(encoding='utf-8', errors='replace')
        tudo.append(f'=== página {n} ===\n{txt.strip()}\n')
        print(f'página {n}: {len(txt)} caracteres')
    (saida / 'texto.txt').write_text('\n'.join(tudo), encoding='utf-8')
    print('ok ->', saida / 'texto.txt')


if __name__ == '__main__':
    main()
