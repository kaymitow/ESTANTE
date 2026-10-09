"""Teste do aceite na revisão, sem usar os modelos: cria um livro de teste com um rascunho feito à mão.

    python app/teste_revisao.py          (servidor rodando; apaga o livro de teste no fim)
"""
import json, re, shutil, subprocess, sys, urllib.error, urllib.parse, urllib.request
from pathlib import Path

import pymupdf

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:' + __import__('os').environ.get('ESTANTE_PORTA', '8765')
RAIZ = Path(__file__).resolve().parent.parent
def repo():      # histórico da biblioteca (ver extras.repo); só existe depois do primeiro livro
    return RAIZ / 'livros' if (RAIZ / 'livros' / '.git').exists() else RAIZ


def req(u, data=None):
    r = urllib.request.Request(B + u, json.dumps(data).encode() if isinstance(data, dict) else data, {'Content-Type': 'application/json'})
    try:
        return 200, json.load(urllib.request.urlopen(r, timeout=60))
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def commits():
    return int(subprocess.run(['git', 'rev-list', '--count', 'HEAD'], cwd=repo(), capture_output=True, text=True).stdout)


doc = pymupdf.open()
for _ in range(3):
    doc.new_page()
q = urllib.parse.urlencode({'titulo': 'teste revisao', 'autor': 'zz', 'idioma': 'en', 'arquivo': 'x.pdf'})
livro = req('/api/importar?' + q, doc.tobytes())[1]['id']
p = RAIZ / 'livros' / livro
md = p / 'texto' / 'livro.md'
try:
    antes = md.read_bytes()
    bl = [{'id': f'b{k}', 'tipo': t, 'paginas': pg, 'fonte': f'fonte {k}', 'resultado': r, 'status': s, 'problemas': [], 'conversa': [], 'aceito': False}
          for k, (t, pg, r, s) in enumerate([('titulo', [1], 'Introduction', 'revisar'), ('paragrafo', [1], '1. Primeiro parágrafo.', 'aprovado'),
                                             ('paragrafo', [1, 2], '2. Segundo parágrafo.', 'revisar'), ('paragrafo', [2], '3. Terceiro parágrafo.', 'aprovado'),
                                             ('paragrafo', [3], 'a) Quarto, com *asterisco*.', 'aprovado')])]
    (p / 'revisao/dados/rascunho.json').write_text(json.dumps({'livro': livro, 'tarefa': 'traduzir', 'blocos': bl}, ensure_ascii=False), encoding='utf-8')
    assert md.read_bytes() == antes

    n = commits()
    c, r = req(f'/api/revisao/{livro}/aceitar', {'ids': ['b3']})
    assert c == 200 and r['aceitos'] == 1 and commits() == n + 1, (c, r)
    assert '[3.]{.pnum} Terceiro parágrafo.' in md.read_text(encoding='utf-8')

    # edição manual (como a Conferência faz) tem de sobreviver aos próximos aceites
    md.write_text(md.read_text(encoding='utf-8').replace('Terceiro parágrafo.', 'Terceiro parágrafo, EDITADO À MÃO.'), encoding='utf-8', newline='\n')
    c, r = req(f'/api/revisao/{livro}/aceitar', {'aprovados': True})
    assert c == 200 and r['aceitos'] == 3 and commits() == n + 2, (c, r)
    c, r = req(f'/api/revisao/{livro}/aceitar', {'ids': ['b0'], 'texto': 'Introdução'})
    assert c == 200, r
    t = md.read_text(encoding='utf-8')
    corpo = [l for l in t.split('\n')[5:] if l]
    assert corpo == ['<!-- pg: scan 1 · impressa ? · confiança ok 1.00 -->', '# Introdução', '[1.]{.pnum} Primeiro parágrafo.',
                     '<!-- pg: scan 2 · impressa ? · confiança ok 1.00 -->', '[3.]{.pnum} Terceiro parágrafo, EDITADO À MÃO.',
                     '<!-- pg: scan 3 · impressa ? · confiança ok 1.00 -->', 'a\\) Quarto, com \\*asterisco\\*.'], corpo
    assert all(re.fullmatch(r'<!-- pg: scan (\d+) · impressa (.*?) · confiança (\S+) ([\d.]+) -->', l) for l in corpo if l.startswith('<!--'))

    c, r = req(f'/api/revisao/{livro}/aceitar', {'ids': ['b4'], 'desfazer': True})
    assert c == 200 and r['aceitos'] == 3 and 'Quarto' not in md.read_text(encoding='utf-8'), r
    assert req(f'/api/revisao/{livro}/aceitar', {'ids': ['nao-existe']})[0] == 400
    # texto com marca de link pela metade não entra no livro
    c, r = req(f'/api/revisao/{livro}/aceitar', {'ids': ['b4'], 'texto': 'Quarto, com <a1>link quebrado.'})
    assert c == 400 and '<a1>' in r['detail'] and 'link quebrado' not in md.read_text(encoding='utf-8'), (c, r)
    # mudar o tipo: título vira parágrafo (bloco aceito: regrava o livro); parágrafo fora do livro vira título (só o rascunho muda)
    c, r = req(f'/api/revisao/{livro}/aceitar', {'ids': ['b0'], 'nivel': 0})
    assert c == 200 and '\nIntrodução\n' in md.read_text(encoding='utf-8') and '# Introdução' not in md.read_text(encoding='utf-8'), r
    antes_md = md.read_bytes()
    assert req(f'/api/revisao/{livro}/aceitar', {'ids': ['b2'], 'nivel': 2})[0] == 200 and md.read_bytes() == antes_md
    assert req(f'/api/revisao/{livro}/aceitar', {'ids': ['b2']})[0] == 200 and '## 2. Segundo parágrafo.' in md.read_text(encoding='utf-8')

    # livros de verdade: o pipeline recusa
    for real in sorted(d.name for d in (RAIZ / 'livros').iterdir() if d.is_dir() and not d.name.startswith(('zz-', '.')) and d.name != livro):
        if not req(f'/api/pipeline/{real}')[1].get('impedimento'):      # livro ainda sem texto pronto: iniciar aqui o poria para processar de verdade
            continue
        c, r = req(f'/api/pipeline/{real}/iniciar', {})
        assert c == 400, (real, c, r)
    assert req(f'/api/pipeline/{livro}')[1]['rascunho'] == {'total': 5, 'aceitos': 4, 'revisar': 0, 'juiz': 0}
    print('ok')
finally:
    shutil.rmtree(p)
    subprocess.run(['git', 'add', '-A', str(p)], cwd=repo())
    subprocess.run(['git', 'commit', '-q', '-m', 'Remove livro de teste da revisão'], cwd=repo())
