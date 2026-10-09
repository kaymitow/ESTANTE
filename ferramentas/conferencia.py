"""Páginas HTML de CONFERÊNCIA, para ler lado a lado com a fonte (abre no navegador).

  python ferramentas/conferencia.py livros/<livro>
      -> saida/conferencia-paralela.html   inglês | português, parágrafo a parágrafo, com busca
  python ferramentas/conferencia.py livros/<livro-em-scan>
      -> saida/conferencia-scan/index.html  imagem do scan | parágrafos que começam naquela página

O que cada uma exige:
- paralela: fonte/dados/source.json (texto-fonte estruturado) e revisao/dados/reviewed.json (tradução revisada).
- scan: fonte/<PDF> e os marcadores <!-- pg: ... --> do livro.md.
Os marcadores de página do scan são automáticos; parágrafos de baixa confiança saem destacados.
"""
import html, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from buscar import limpa   # noqa: E402

sys.stdout.reconfigure(encoding='utf-8')
CSS = """
:root{--fg:#1d1d1f;--bg:#fff;--mut:#666;--bd:#d8d8d8;--hl:#fff3b0;--warn:#fde2e2}
@media(prefers-color-scheme:dark){:root{--fg:#e8e8e8;--bg:#16181b;--mut:#9aa0a6;--bd:#33373d;--hl:#5a4d10;--warn:#4a2323}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 Georgia,serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--bd);padding:.6rem 1rem;z-index:5}
header input{width:min(28rem,100%);padding:.4rem .6rem;font:inherit;border:1px solid var(--bd);border-radius:6px;background:var(--bg);color:var(--fg)}
main{max-width:1200px;margin:0 auto;padding:0 1rem 4rem}
h2{margin:2rem 0 .5rem;font-size:1.25rem;border-bottom:1px solid var(--bd)}
.row{display:grid;grid-template-columns:3rem 1fr 1fr;gap:1rem;padding:.6rem 0;border-bottom:1px solid var(--bd)}
.n{color:var(--mut);font-weight:bold}
.row.hit{background:var(--hl)}
@media(max-width:800px){.row{grid-template-columns:2.5rem 1fr}.row .pt{grid-column:2}}
.pg{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1.2rem;padding:1rem 0;border-bottom:2px solid var(--bd)}
.pg img{width:100%;height:auto;border:1px solid var(--bd)}
.pg h3{margin:.2rem 0 .6rem;font-size:1rem;color:var(--mut)}
.pg p{margin:.4rem 0}
.baixa{background:var(--warn);padding:.2rem .4rem;border-radius:4px}
@media(max-width:800px){.pg{grid-template-columns:1fr}}
"""
JS = """
const q=document.getElementById('q');q&&q.addEventListener('input',()=>{
 const t=q.value.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();
 document.querySelectorAll('.row,.pg').forEach(r=>{
  const s=r.textContent.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();
  r.style.display=(!t||s.includes(t))?'':'none';r.classList.toggle('hit',!!t&&s.includes(t));});});
"""


def pagina(titulo, corpo, busca=True):
    cab = '<header><input id="q" type="search" placeholder="Buscar (ignora acentos e maiúsculas)…"></header>' if busca else ''
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(titulo)}</title><style>{CSS}</style></head><body>{cab}<main><h1>{html.escape(titulo)}</h1>{corpo}</main><script>{JS}</script></body></html>')


def paralela(livro):
    fonte = json.loads((livro / 'fonte/dados/source.json').read_text(encoding='utf-8'))
    pt = json.loads((livro / 'revisao/dados/reviewed.json').read_text(encoding='utf-8'))
    partes = ['<p>Inglês: PDF-fonte do projeto. Português: tradução revisada. Cite pelo número do parágrafo.</p>']
    for b in fonte['blocks']:
        if b['kind'] == 'paragraph':
            k, num = f"p{b['number']}", b['number']
        elif b['kind'] in ('heading', 'subheading'):
            k = f"h{b['source_pages'][0]}" if b['kind'] == 'heading' else b['id']
            partes.append(f"<h2>{html.escape(b['text'])} <small>— {html.escape(pt[k]['pt'])}</small></h2>")
            continue
        partes.append(f'<div class="row" id="{k}"><div class="n">{num}</div><div class="en">{html.escape(b["text"])}</div>'
                      f'<div class="pt">{html.escape(pt[k]["pt"])}</div></div>')
    partes.append('<h2>Notas</h2>')
    for n in fonte['notes']:
        k = f"n{n['number']}"
        partes.append(f'<div class="row" id="{k}"><div class="n">{n["number"]}</div><div class="en">{html.escape(n["text"])}</div>'
                      f'<div class="pt">{html.escape(pt[k]["pt"]).replace(chr(10), "<br>")}</div></div>')
    saida = livro / 'saida' / 'conferencia-paralela.html'
    saida.parent.mkdir(exist_ok=True)
    saida.write_text(pagina(fonte['title'] + ' — conferência paralela', ''.join(partes)), encoding='utf-8')
    print('ok ->', saida)


def scan(livro):
    import pymupdf
    pdf = next((livro / 'fonte').glob('*.pdf'))
    marcador = re.compile(r'<!-- pg: scan (\d+) · impressa (.*?) · confiança (\S+) ([\d.]+) -->')
    paginas, atual = {}, None
    for l in (livro / 'texto/livro.md').read_text(encoding='utf-8').split('\n'):
        m = marcador.match(l.strip())
        if m:
            atual = int(m[1]); paginas[atual] = {'imp': m[2], 'conf': m[3], 'sc': float(m[4]), 'ps': []}
            continue
        s = l.strip()
        if atual and s and not s.startswith(('#', '<!--', ':::', '|', '![')):
            paginas[atual]['ps'].append(limpa(s.lstrip('> ')))
    out = livro / 'saida' / 'conferencia-scan'
    (out / 'img').mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(pdf))
    partes = ['<p>À esquerda, o scan; à direita, os parágrafos do livro que <b>começam</b> nessa página (o último pode continuar na seguinte). '
              'Fundo rosado = baixa confiança no alinhamento automático.</p>']
    for n, d in sorted(paginas.items()):
        jpg = out / 'img' / f'scan-{n:03d}.jpg'
        if not jpg.exists():
            doc[n - 1].get_pixmap(dpi=100).save(str(jpg), jpg_quality=62)
        cls = ' class="baixa"' if d['conf'] == '?' else ''
        ps = ''.join(f'<p>{html.escape(p)}</p>' for p in d['ps'])
        partes.append(f'<section class="pg" id="s{n}"><div><img loading="lazy" src="img/{jpg.name}" alt="scan {n}"></div>'
                      f'<div><h3{cls}>scan {n} · página impressa {html.escape(d["imp"])} · similaridade {d["sc"]:.2f}</h3>{ps}</div></section>')
    (out / 'index.html').write_text(pagina(livro.name + ' — conferência com o scan', ''.join(partes)), encoding='utf-8')
    print('ok ->', out / 'index.html', f'({len(paginas)} páginas)')


if __name__ == '__main__':
    livro = Path(sys.argv[1]).resolve()
    if (livro / 'fonte/dados/source.json').exists() and (livro / 'revisao/dados/reviewed.json').exists():
        paralela(livro)
    elif list((livro / 'fonte').glob('*.pdf')):
        scan(livro)
    else:
        sys.exit('Nada a conferir: faltam fonte/dados/source.json (paralela) ou o PDF-fonte (scan).')
