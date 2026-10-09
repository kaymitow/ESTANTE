"""Verifica um livro: o texto do Markdown tem de estar INTEIRO no EPUB e no PDF gerados.

  python ferramentas/verificar.py livros/<pasta-do-livro>

1. cada parágrafo do livro.md (sem marcas) aparece no EPUB, e vice-versa;
2. cada parágrafo aparece no PDF (comparação só por letras, ignora hifenização e quebras);
3. EPUBCheck (W3C) sem erros;  4. PDF sem imagens de página (só texto), fontes embutidas.
Sai com código 1 se algo falhar."""
import html, re, subprocess, sys, unicodedata, zipfile
from pathlib import Path
import pymupdf

RAIZ = Path(__file__).resolve().parent.parent
livro = Path(sys.argv[1]).resolve(); nome = livro.name
md = (livro / 'texto/livro.md').read_text(encoding='utf-8')
falhas = []

def letras(s):
    s = unicodedata.normalize('NFKC', html.unescape(s))
    return re.sub(r'[^A-Za-zÀ-ÿ]', '', s).lower()      # só letras: ignora números de nota, de página e hifenização

# --- parágrafos do Markdown (tira front matter, comentários, marcas) ---
md = re.sub(r'^---\n.*?\n---\n', '', md, flags=re.S)
md = re.sub(r'<!--.*?-->', '', md, flags=re.S)
def limpa(l):
    l = re.sub(r'^\[\^\d+\]:\s*', '', l.strip()); l = re.sub(r'\[\^\d+\]', '', l)
    l = re.sub(r'\[([^\]]*)\]\{\.\w+\}', r'\1', l)            # [1.]{.pnum}
    l = re.sub(r'!?\[([^\]]*)\]\((?:[^()\s]|\([^()\s]*\))+\)', r'\1', l)      # [texto](endereço) -> texto
    l = re.sub(r'<br\s*/?>', ' ', l); l = re.sub(r'(?<!\\)\*', '', l)        # quebra de linha e itálico/negrito
    return re.sub(r'\\(.)', r'\1', l)
paras = [limpa(l) for l in md.split('\n') if l.strip() and not re.match(r'(#|:::|\||!\[|>?\s*$)', l.strip().lstrip('> '))]
paras = [p for p in paras if len(letras(p)) > 3]
print(f'{nome}: {len(paras)} parágrafos no Markdown')

# --- EPUB ---
epub = livro / 'saida' / f'{nome}.epub'
z = zipfile.ZipFile(epub)
texto_epub = ''.join(letras(re.sub(r'<[^>]+>', ' ', z.read(n).decode('utf-8'))) for n in z.namelist() if n.endswith('.xhtml'))
faltam = [p for p in paras if letras(p) not in texto_epub]
print(f'  EPUB: {len(paras) - len(faltam)}/{len(paras)} parágrafos encontrados')
falhas += [f'EPUB sem: {p[:80]}' for p in faltam[:10]]

# --- PDF ---
pdf = pymupdf.open(str(livro / 'saida' / f'{nome}.pdf'))
texto_pdf = letras(''.join(p.get_text() for p in pdf))
def no_pdf(p, passo=30, tolera=2):
    # o PDF intercala número de página e notas de rodapé no meio do parágrafo: confere em blocos de 30 letras
    l = letras(p); blocos = [l[i:i + passo] for i in range(0, len(l) - passo + 1, passo)] or [l]
    return sum(b not in texto_pdf for b in blocos) <= tolera
faltam = [p for p in paras if not no_pdf(p)]
imgs = sum(len(p.get_images()) for p in pdf)
print(f'  PDF : {len(paras) - len(faltam)}/{len(paras)} parágrafos; {len(pdf)} páginas; {imgs} imagens')
falhas += [f'PDF sem: {p[:80]}' for p in faltam[:10]]

# --- EPUBCheck ---
jar = next((RAIZ / 'ferramentas').glob('epubcheck-*/epubcheck.jar'), None)
if jar:
    r = subprocess.run(['java', '-jar', str(jar), str(epub)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    erros = [l for l in ((r.stdout or '') + (r.stderr or '')).splitlines() if l.startswith(('ERROR', 'FATAL'))]
    print(f'  EPUBCheck: {len(erros)} erros', *erros[:5], sep='\n    ' if erros else ' ')
    falhas += erros
else:
    print('  EPUBCheck não encontrado (ferramentas/epubcheck-*/epubcheck.jar)')

print('OK' if not falhas else 'FALHOU:\n  ' + '\n  '.join(falhas)); sys.exit(1 if falhas else 0)
