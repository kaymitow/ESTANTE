"""Colação: compara o texto-fonte do projeto com OUTRA cópia do mesmo texto, parágrafo a parágrafo,
e lista as diferenças palavra por palavra. Serve para descobrir se uma cópia foi alterada.

  python ferramentas/colacionar.py livros/<livro> "livros/<livro>/fonte/outras-copias/arquivo.txt"

- Fonte do projeto: livros/<livro>/fonte/dados/source.json (parágrafos numerados).
- Outra cópia: texto simples em que os parágrafos começam por "N. " (como o Manifesto).
Escreve o relatório em livros/<livro>/revisao/colacao - <arquivo>.md.
Ignora: maiúsculas, pontuação, hifenização de fim de linha, espaçamento e cabeçalhos/notas colados
antes ou depois do parágrafo.
"""
import difflib, json, re, sys, unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')


def norm_palavras(t):
    """só palavras (letras, números, apóstrofo): aspas, travessões e pontuação não contam"""
    t = unicodedata.normalize('NFKC', t)
    t = re.sub(r'(\w)-[ \t]*\n[ \t]*(\w)', r'\1\2', t)       # suffe-(quebra de linha)ring -> suffering
    t = t.replace('’', "'").replace('‘', "'")
    return re.findall(r"[\w']+", t.lower())


def paragrafos_externos(texto, n_max):
    """Procura '1. ', '2. ' ... em ordem crescente; devolve {n: texto}."""
    pos, cur, marcas = 0, 1, []
    while cur <= n_max:
        m = re.compile(r'(?:^|\n)\s*%d\.\s' % cur).search(texto, pos)
        if m:
            marcas.append((cur, m.end())); pos = m.end()
        cur += 1                                  # número perdido no OCR: segue para o próximo
    achados = {}
    for (n, ini), prox in zip(marcas, marcas[1:] + [(None, len(texto))]):
        fim = prox[1] - len(str(prox[0])) - 4 if prox[0] else prox[1]
        achados[n] = texto[ini:max(ini, fim)]
    return achados


def main():
    livro = Path(sys.argv[1]).resolve(); outra = Path(sys.argv[2]).resolve()
    fonte = json.loads((livro / 'fonte/dados/source.json').read_text(encoding='utf-8'))
    nossos = {b['number']: b['text'] for b in fonte['blocks'] if b['kind'] == 'paragraph'}
    ext = paragrafos_externos(outra.read_text(encoding='utf-8', errors='replace'), max(nossos))
    iguais, difs, ausentes = 0, [], []
    for n, t in sorted(nossos.items()):
        if n not in ext:
            ausentes.append(n); continue
        a, b = norm_palavras(t), norm_palavras(ext[n])
        if a == b or ''.join(a) == ''.join(b):            # inclui palavra partida no OCR ("of ficials")
            iguais += 1; continue
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        cod = sm.get_opcodes(); ops = []
        for k, (op, i1, i2, j1, j2) in enumerate(cod):
            if op == 'equal': continue
            if op == 'insert' and (k == 0 or k == len(cod) - 1): continue   # cabeçalho/nota colado antes ou depois
            if ''.join(a[i1:i2]) == ''.join(b[j1:j2]): continue            # só espaçamento diferente
            ops.append((op, ' '.join(a[i1:i2]), ' '.join(b[j1:j2])))
        if not ops:
            iguais += 1; continue
        difs.append((n, round(sm.ratio(), 3), ops))
    rel = [f'# Colação — {livro.name}', '', f'Fonte do projeto: `fonte/dados/source.json` · Outra cópia: `{outra.name}`', '',
           f'- Parágrafos idênticos (após normalizar): **{iguais}** de {len(nossos)}',
           f'- Com diferença: **{len(difs)}**, das quais **{sum(any(o[0] != "insert" for o in d[2]) for d in difs)}** têm palavra trocada/omitida (as primeiras do relatório)',
           f'- Não localizados na outra cópia: **{len(ausentes)}** {ausentes[:30]}', '',
           '"projeto" = o que está no PDF-fonte do projeto; "outra" = a cópia comparada. Diferenças muito pequenas costumam ser erro de OCR da outra cópia.', '']
    # primeiro as trocas/omissões de palavras (as que importam); depois os trechos extras da outra cópia (cabeçalhos, citações de página)
    for n, r, ops in sorted(difs, key=lambda x: (not any(o[0] != 'insert' for o in x[2]), x[1])):
        rel.append(f'## Parágrafo {n} (semelhança {r})' + ('' if any(o[0] != 'insert' for o in ops) else ' — só texto extra na outra cópia'))
        for op, a, b in ops[:12]:
            rel.append(f'- {op}: projeto «{a}» ↔ outra «{b}»')
        if len(ops) > 12: rel.append(f'- … mais {len(ops) - 12} diferenças')
        rel.append('')
    saida = livro / 'revisao' / f'colacao - {outra.stem[:60]}.md'
    saida.write_text('\n'.join(rel), encoding='utf-8')
    print(f'{iguais}/{len(nossos)} idênticos; {len(difs)} com diferença; {len(ausentes)} ausentes -> {saida}')


if __name__ == '__main__':
    main()
