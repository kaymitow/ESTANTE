"""Mede, neste computador, o auditor e o juiz que você escolher: o app estraga de propósito traduções boas e conta quantos erros cada um pega.

    python app/medir.py                              só as checagens automáticas (instantâneo, não usa a placa)
    python app/medir.py --auditor MODELO             também o auditor
    python app/medir.py --auditor MODELO --juiz MODELO [--certeza 0.7]     e o juiz: o erro continua de pé depois dele?

O teste vem com o app (app/teste_publico.json: 12 parágrafos escritos para isso, com tradução conferida; nenhum livro entra aqui).
Em cada parágrafo: a tradução boa como está (alerta aqui é falso alarme) e versões com UM erro plantado: frase tirada, frase de outro
parágrafo enfiada, número trocado, "não" tirado, frase deixada em inglês, palavra forte abrandada.
O resultado fica guardado em app/dados/medicoes.json (só neste computador) e é mostrado no fim.
ponytail: app/regua_erros.py (régua interna, com um livro da estante) faz o mesmo com outra base; juntar os dois quando um mudar.
"""
import argparse, json, random, re, sys, time
from pathlib import Path

import duplo

AQUI = Path(__file__).resolve().parent
BRANDAS = {'odeia': 'não aprecia', 'destruiu': 'modificou', 'desastre': 'inconveniente', 'humilhação': 'desconforto', 'estúpido': 'excessivo',
           'lixo': 'fraco', 'covarde': 'reservado', 'mentiu': 'se equivocou', 'mentiroso': 'impreciso', 'raiva': 'saudade', 'bêbado': 'cansado', 'arruinou': 'afetou'}
TIPOS = ('limpo', 'omissao', 'acrescimo', 'numero', 'negacao', 'idioma', 'suavizacao')


def casos(pares, rnd):
    """[(tipo, inglês, tradução)]: cada par limpo e com um erro de cada tipo que couber nele."""
    out = []
    for n, (en, br) in enumerate(pares):
        fr, fe = duplo.frases(br), duplo.frases(en)
        k = rnd.randrange(1, len(fr))
        out.append(('limpo', en, br))
        out.append(('omissao', en, ' '.join(fr[:k] + fr[k + 1:])))
        out.append(('acrescimo', en, ' '.join(fr[:k] + [duplo.frases(pares[(n + 5) % len(pares)][1])[0]] + fr[k:])))
        m = re.search(r'\b\d{2,}\b', br)
        if m and m[0] in en:
            out.append(('numero', en, br[:m.start()] + str(int(m[0]) + 7) + br[m.end():]))
        if ' não ' in br:
            out.append(('negacao', en, br.replace(' não ', ' ', 1)))
        if len(fe) == len(fr):
            out.append(('idioma', en, ' '.join(fr[:k] + [fe[k]] + fr[k + 1:])))
        for forte, branda in BRANDAS.items():
            if re.search(rf'\b{forte}\b', br):
                out.append(('suavizacao', en, re.sub(rf'\b{forte}\b', branda, br, count=1)))
                break
    return out


def mede(auditor=None, juiz=None, certeza=0, diz=print):
    """Roda o teste e devolve {'tipos': {tipo: [casos, checagens, auditor, algum, de pé depois do juiz]}, 'segundos', ...}."""
    pares = [(p['en'], p['pt']) for p in json.loads((AQUI / 'teste_publico.json').read_text(encoding='utf-8'))]
    lista, res, t0 = casos(pares, random.Random(7)), {t: [0, 0, 0, 0, 0] for t in TIPOS}, time.time()
    objecoes = []
    for k, (tipo, en, br) in enumerate(lista, 1):      # primeiro o auditor em todos, depois o juiz em todos: cada modelo é carregado uma vez só
        ch, aud = duplo.checagens(en, br, 'traduzir'), []
        if auditor:
            ok, pb = duplo.auditar(auditor, 'traduzir', en, br)
            aud = [] if ok else [p for p in (pb or ['(sem detalhe)']) if not p.startswith('estilo: ')]
        objecoes.append(ch + aud)
        r = res[tipo]
        r[0] += 1; r[1] += bool(ch); r[2] += bool(aud); r[3] += bool(ch + aud); r[4] += bool(ch + aud)
        diz(f'{k}/{len(lista)} {tipo}: checagens {len(ch)}, auditor {len(aud)}', flush=True)
    for k, ((tipo, en, br), obj) in enumerate(zip(lista, objecoes), 1):
        if juiz and obj:
            votos = duplo.julgar(juiz, 'traduzir', en, br, obj, certeza=certeza > 0)
            de_pe = any(v[0] or duplo.trava(p) or (v[2] is not None and v[2] < certeza) for p, v in zip(obj, votos))
            res[tipo][4] -= not de_pe
            diz(f"juiz {k}/{len(lista)} {tipo}: {'mantém' if de_pe else 'libera'}", flush=True)
    return {'quando': time.strftime('%Y-%m-%d %H:%M'), 'auditor': auditor, 'juiz': juiz, 'certeza': certeza, 'segundos': round(time.time() - t0), 'tipos': res}


def tabela(m):
    pct = lambda a, b: f'{a}/{b}' if b else '—'      # noqa: E731
    L = [f"auditor: {m['auditor'] or '—'} · juiz: {m['juiz'] or '—'}" + (f" (certeza mínima {m['certeza']})" if m['certeza'] else '') + f" · {m['segundos']} s",
         'Na linha "limpo" o ideal é 0 (alerta ali é falso alarme); nas outras, quanto mais, melhor.',
         f"{'caso':12}{'checagens':>11}{'auditor':>9}{'algum':>7}{'depois do juiz':>16}"]
    return '\n'.join(L + [f"{t:12}{pct(r[1], r[0]):>11}{pct(r[2], r[0]) if m['auditor'] else '—':>9}{pct(r[3], r[0]):>7}{pct(r[4], r[0]) if m['juiz'] else '—':>16}"
                          for t, r in m['tipos'].items() if r[0]])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--auditor'); ap.add_argument('--juiz'); ap.add_argument('--certeza', type=float, default=0)
    arg = ap.parse_args()
    m = mede(arg.auditor, arg.juiz, arg.certeza)
    arq = AQUI / 'dados' / 'medicoes.json'
    arq.parent.mkdir(exist_ok=True)
    arq.write_text(json.dumps((json.loads(arq.read_text(encoding='utf-8')) if arq.exists() else []) + [m], ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n' + tabela(m))
