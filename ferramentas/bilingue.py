"""Edição bilíngue: original e tradução no mesmo volume, para conferir na hora.

  python ferramentas/bilingue.py livros/<pasta-do-livro>     gera saida/bilingue.md (depois o construir.py faz o EPUB, HTML e Word)

Cada bloco da fonte vira o original (em citação, em cinza nos formatos que mostram cor) e, embaixo, a tradução aceita. Bloco ainda
não aceito aparece com "tradução ainda não aceita", e a folha de rosto diz quantos blocos já têm tradução aceita. Imagem sai uma vez.
Só lê a fonte e o rascunho; não altera nada no livro.
"""
import json, sys
from pathlib import Path


def _ler(p: Path) -> dict:
    return json.loads(p.read_text(encoding='utf-8'))


def monta(livro: Path, colunas: bool = False) -> tuple[str, int, int]:
    """Markdown da edição bilíngue e a cobertura: (texto, blocos com tradução aceita, blocos no rascunho).
    colunas=True: cada par vai num \\begin{paracol}{2} (original à esquerda, em cinza e menor; tradução à direita), para o PDF.
    Nesse modo o Markdown leva LaTeX cru, por isso o construtor lê com o leitor que deixa o LaTeX passar."""
    fonte = _ler(livro / 'fonte/dados/source.json')
    rasc = _ler(livro / 'revisao/dados/rascunho.json')
    orig_por_id = {b['id']: (b.get('text') or '').strip() for b in fonte['blocks']}
    aceitos = sum(bool(b.get('aceito')) for b in rasc['blocos'])
    total = len(rasc['blocos'])
    out = ['---', f"title: \"{fonte.get('title') or livro.name}\"", f"author: \"{fonte.get('author') or ''}\"", 'lang: pt-BR', '---', '',
           f"*Original e tradução. A tradução aceita cobre {aceitos} de {total} blocos.*", '']
    for b in rasc['blocos']:
        original = orig_por_id.get(b['id'], '')
        if b['tipo'] == 'imagem':
            out += [b.get('resultado') or original, '']
            continue
        aceito = bool(b.get('aceito'))
        traduzido = (b.get('texto') or b.get('resultado') or '').strip() if aceito else ''
        if colunas:
            # LaTeX em blocos explícitos ({=latex}), não colado ao texto: o Pandoc lê o texto normal e o paracol separa as colunas
            pendente = '*tradução ainda não aceita*'      # dentro de parágrafo: Markdown, não LaTeX (o LaTeX sairia como texto)
            if b['tipo'] == 'titulo':
                esq, dir_ = f'**{original}**', (f'**{traduzido}**' if aceito else pendente)
                out += ['```{=latex}', '\\begin{paracol}{2}', '```', '', esq, '', '```{=latex}', '\\switchcolumn', '```', '', dir_, '', '```{=latex}', '\\end{paracol}', '```', '']
            else:
                out += ['```{=latex}', '\\begin{paracol}{2}', '\\begingroup\\small\\color{gray}', '```', '', original, '',
                        '```{=latex}', '\\endgroup', '\\switchcolumn', '```', '', traduzido if aceito else pendente, '', '```{=latex}', '\\end{paracol}', '```', '']
        elif b['tipo'] == 'titulo':
            out += [f"{'#' * (b.get('nivel') or 1)} {traduzido or original}", '', f"> *{original}*" if traduzido else '', '']
        else:
            out += [f"> {original}", '', traduzido if aceito else '*tradução ainda não aceita*', '']
    return '\n'.join(out), aceitos, total


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    livro = Path(sys.argv[1]).resolve()
    texto, aceitos, total = monta(livro)
    (livro / 'saida').mkdir(exist_ok=True)
    (livro / 'saida' / 'bilingue.md').write_text(texto, encoding='utf-8', newline='\n')
    print(f'bilingue: {aceitos} de {total} blocos com tradução aceita -> saida/bilingue.md')
