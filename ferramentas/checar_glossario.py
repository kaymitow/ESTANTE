"""Checa a consistência terminológica de cada livro contra o glossário em CSV.

  python ferramentas/checar_glossario.py            # todos os livros
  python ferramentas/checar_glossario.py autor  # um livro

Lê livros/<livro>/revisao/glossario.csv (separador ";", UTF-8) com as colunas:
  fonte ; usar ; evitar ; exceto ; obs
- usar  : forma(s) decidida(s), separadas por "|". Contamos as ocorrências (o começo da palavra basta: "determinad" pega as flexões).
- evitar: variantes que NÃO devem aparecer, separadas por "|". Cada ocorrência é listada com o parágrafo.
- exceto: trechos (separados por "|") que, se aparecerem no parágrafo, tornam a variante legítima (ex.: "estatística" de verdade).
Ignora maiúsculas e acentos. Sai com código 1 se achar alguma variante a evitar.
Para registrar uma decisão nova: acrescente uma linha ao CSV (e a data/motivo na obs).
"""
import csv, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from buscar import RAIZ, sem_acento, unidades   # noqa: E402

sys.stdout.reconfigure(encoding='utf-8')


def padrao(termo):
    return re.compile(r'(?<![a-z])' + re.escape(sem_acento(termo.strip())))


def main():
    filtro = sys.argv[1].lower() if len(sys.argv) > 1 else ''
    problemas = 0
    for pasta in sorted((RAIZ / 'livros').iterdir()):
        csv_path = pasta / 'revisao' / 'glossario.csv'
        if not csv_path.exists() or filtro not in pasta.name.lower():
            continue
        linhas = list(csv.DictReader(csv_path.open(encoding='utf-8'), delimiter=';'))
        textos = [(sem_acento(t), r) for t, r in unidades(pasta / 'texto' / 'livro.md')]
        print(f'== {pasta.name} ({len(linhas)} termos) ==')
        for l in linhas:
            usar = [padrao(t) for t in l['usar'].split('|') if t.strip()]
            evitar = [(t.strip(), padrao(t)) for t in l['evitar'].split('|') if t.strip()]
            n_usar = sum(len(p.findall(t)) for t, _ in textos for p in usar)
            exc = [sem_acento(x.strip()) for x in (l.get('exceto') or '').split('|') if x.strip()]
            achados = [(v, r) for t, r in textos for v, p in evitar if p.search(t) and not any(x in t for x in exc)]
            marca = 'ok ' if not achados else 'ERRO'
            print(f'  [{marca}] {l["fonte"]:<42} usar «{l["usar"]}»: {n_usar}x' + (f' | evitar: {len(achados)}x' if evitar else ''))
            for v, r in achados:
                print(f'         variante «{v}» em: {r}')
            problemas += len(achados)
        print()
    print('Sem variantes proibidas.' if not problemas else f'{problemas} ocorrência(s) de variante a evitar.')
    sys.exit(1 if problemas else 0)


if __name__ == '__main__':
    main()
