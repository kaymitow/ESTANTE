"""Gera acentos.csv.gz: palavras do português atual que só existem COM acento, para pôr o acento em grafia antiga sem modelo.

    python ferramentas/ortografia/dicionario.py caminho/para/pt_BR.dic

Fonte: dicionário VERO do LibreOffice (pt_BR.dic, de Raimundo Moura e equipe, LGPL 3 / MPL), baixado de
https://github.com/LibreOffice/dictionaries/tree/master/pt_BR. Só a lista derivada vai no projeto.

Entra no arquivo só o par sem ambiguidade: "politico" só vira "político" se "politico" não for, ele mesmo, palavra.
Ficam de fora, de propósito:
  - o que também existe sem acento (esta/está, e/é, pais/país);
  - o que pode ser forma de verbo (pratica/prática, publico/público, duvida/dúvida): se existe o verbo praticar, a forma
    "pratica" é legítima e o app não tem como saber qual das duas o autor escreveu. Essas ficam para o modelo e a revisão.
"""
import csv, gzip, re, sys, unicodedata
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sem = lambda s: ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')      # noqa: E731

palavras = set()
for linha in Path(sys.argv[1]).read_text(encoding='utf-8-sig').split('\n')[1:]:
    w = linha.split('/')[0].strip()
    if re.fullmatch(r'[a-zà-ÿ]+', w):          # só minúsculas simples: nomes próprios, siglas e compostos ficam de fora
        palavras.add(w)
def verbo(k):
    """k pode ser forma de um verbo do dicionário? (radical curto demais não conta: "sao" não é forma de "sair")"""
    r = re.sub(r'(as|os|es|am|em|a|o|e)$', '', k)
    return len(r) >= 3 and any(r + f in palavras for f in ('ar', 'er', 'ir'))


# o dicionário não lista contrações e outras palavrinhas de função: sem esta guarda, "dos" viraria "dôs" (plural de "dô")
FUNCAO = set('a o as os um uma uns umas de do da dos das em no na nos nas ao aos por pelo pela pelos pelas com sem sob sobre entre para pra que se e ou mas nem como quando onde '
             'me te lhe lhes nos vos meu minha teu tua seu sua seus suas nosso nossa este esta estes estas esse essa esses essas aquele aquela isto isso aquilo ele ela eles elas '
             'eu tu ja la ca so ate apos tambem porem pais esta estao sao tem vem ha'.split())
candidatos = {}
for w in palavras:
    k = sem(w)
    if k != w and len(k) > 2:
        candidatos.setdefault(k, set()).add(w)
pares = {'nao': 'não', 'sao': 'são', 'tambem': 'também', 'porem': 'porém', 'alem': 'além', 'ate': 'até', 'ja': 'já', 'so': 'só', 'la': 'lá', 'ha': 'há'}      # sem leitura sem acento em texto corrido
for k, ws in candidatos.items():
    if len(ws) == 1 and k not in palavras and k not in FUNCAO and len(k) >= 4 and not verbo(k):
        w = next(iter(ws))
        pares[k] = w
        # o dicionário só lista a forma base: feminino e plurais regulares entram pela mesma regra de não ambiguidade
        formas = [(k + 's', w + 's')] if w[-1] in 'aeio' else []
        if w.endswith('o'):
            formas += [(k[:-1] + 'a', w[:-1] + 'a'), (k[:-1] + 'as', w[:-1] + 'as')]
        for fk, fw in formas:
            if len(fk) >= 6 and fk not in palavras and fk not in candidatos and fk not in FUNCAO and not verbo(fk):
                pares.setdefault(fk, fw)
with gzip.open(AQUI / 'acentos.csv.gz', 'wt', encoding='utf-8', newline='\n') as f:
    out = csv.writer(f, delimiter=';', lineterminator='\n')
    out.writerow(['sem', 'com'])
    for k in sorted(pares):
        out.writerow([k, pares[k]])
print(len(palavras), 'palavras no dicionário;', len(pares), 'pares sem ambiguidade em acentos.csv.gz')
# as palavras-base, para regras.existe() saber se uma palavra é do português atual (as flexões são desfeitas lá)
with gzip.open(AQUI / 'lemas.txt.gz', 'wt', encoding='utf-8', newline='\n') as f:
    f.write('\n'.join(sorted(palavras)))
print('lemas.txt.gz:', (AQUI / 'lemas.txt.gz').stat().st_size // 1024, 'KB')
