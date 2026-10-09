"""Busca com citação: procura palavras nos livros e devolve onde estão (seção, parágrafo, página).

  python ferramentas/buscar.py "livre-arbítrio"
  python ferramentas/buscar.py liberdade vontade         # todas as palavras no mesmo parágrafo
  python ferramentas/buscar.py "determinis" --livro <parte-do-nome>
  python ferramentas/buscar.py -r "propriedade (particular|privada)"   # expressão regular
  python ferramentas/buscar.py "estadística" --contar      # só quantas vezes, por livro

Ignora maiúsculas e acentos. Cada resultado traz o que dá para citar:
texto original -> número do parágrafo (ou nota); scan -> seção + página do scan/impressa
(os marcadores de página do scan são automáticos: confira no scan antes de citar).
"""
import argparse, re, sys, unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding='utf-8')


def sem_acento(s):
    """minúsculas sem acento; mantém o mesmo comprimento para podermos marcar o trecho no original."""
    out = []
    for c in s:
        d = unicodedata.normalize('NFD', c)
        out.append(d[0].lower() if d else c.lower())
    return ''.join(out)


def limpa(l):
    l = re.sub(r'\[\^\d+\]', '', l)
    l = re.sub(r'\[([^\]]*)\]\{\.\w+\}', r'\1', l)
    l = re.sub(r'\*+', '', l)
    return re.sub(r'\\(.)', r'\1', l).strip()


def unidades(md_path):
    """Gera (texto, rótulo) para cada parágrafo e nota do livro.md."""
    h1 = h2 = ''
    pagina = ''
    texto = re.sub(r'^---\n.*?\n---\n', '', md_path.read_text(encoding='utf-8'), flags=re.S)
    for linha in texto.split('\n'):
        s = linha.strip()
        if not s:
            continue
        m = re.match(r'(#{1,3}) (.*?)(\s*\{.*\})?$', s)
        if m:
            nivel, t = len(m[1]), limpa(m[2])
            if nivel == 1: h1, h2 = t, ''
            else: h2 = t
            continue
        m = re.match(r'<!-- pg: scan (\d+) · impressa (.*?) · confiança', s)
        if m:
            pagina = f'scan {m[1]}, impressa {m[2]}'
            continue
        if s.startswith(('<!--', ':::', '|', '![', '>')) and not s.startswith('> '):
            continue
        s = s.lstrip('> ').strip()
        rot = ' › '.join(x for x in (h1, h2) if x)
        n = re.match(r'\[(\d+)\.\]\{\.pnum\}', s)
        f = re.match(r'\[\^(\d+)\]:', s)
        if n: rot += f' · parágrafo {n[1]}'
        elif f: rot = f'nota {f[1]}'
        if pagina and not f: rot += f' · {pagina}'
        yield limpa(re.sub(r'^\[\^\d+\]:\s*', '', s)), rot


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('termos', nargs='+')
    ap.add_argument('-r', '--regex', action='store_true', help='o primeiro termo é uma expressão regular')
    ap.add_argument('--livro', help='parte do nome da pasta do livro')
    ap.add_argument('--contar', action='store_true', help='só conta as ocorrências')
    ap.add_argument('--largura', type=int, default=160, help='caracteres de contexto (padrão 160)')
    a = ap.parse_args()
    padroes = [re.compile(sem_acento(a.termos[0]) if not a.regex else a.termos[0])] if a.regex else \
              [re.compile(re.escape(sem_acento(t))) for t in a.termos]
    total = 0
    for pasta in sorted((RAIZ / 'livros').iterdir()):
        md = pasta / 'texto' / 'livro.md'
        if not md.exists() or (a.livro and a.livro.lower() not in pasta.name.lower()):
            continue
        achados = 0
        for texto, rotulo in unidades(md):
            base = sem_acento(texto)
            if not all(p.search(base) for p in padroes):
                continue
            ocorr = sum(len(p.findall(base)) for p in padroes[:1])
            achados += ocorr
            if a.contar:
                continue
            m = padroes[0].search(base)
            ini = max(0, m.start() - a.largura // 2); fim = min(len(texto), m.end() + a.largura // 2)
            trecho = texto[ini:m.start()] + '«' + texto[m.start():m.end()] + '»' + texto[m.end():fim]
            print(f'[{pasta.name}] {rotulo}\n    {"…" if ini else ""}{trecho}{"…" if fim < len(texto) else ""}\n')
        print(f'== {pasta.name}: {achados} ocorrência(s) ==\n' if a.contar else f'-- {pasta.name}: {achados} ocorrência(s) --\n')
        total += achados
    if not total:
        print('Nada encontrado.')


if __name__ == '__main__':
    main()
