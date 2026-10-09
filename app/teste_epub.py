"""Teste da entrada por EPUB, sem modelos nem servidor: EPUB -> blocos -> rascunho -> linhas do livro.md.

    python app/teste_epub.py caminho/do/livro.epub [pasta]
Trabalha numa pasta temporária; não cria livro nem mexe em livros/. Com [pasta], deixa lá o livro montado (texto original, tudo aceito)
para testar a geração de PDF/EPUB com o estilo do livro: python ferramentas/construir.py <pasta> tudo
"""
import collections, shutil, sys, tempfile
from pathlib import Path

import pipeline
import revisao

sys.stdout.reconfigure(encoding='utf-8')
manter = len(sys.argv) > 2
p = Path(sys.argv[2]).resolve() if manter else Path(tempfile.mkdtemp(prefix='estante-epub-'))
if manter:
    shutil.rmtree(p, ignore_errors=True)
try:
    for d in ('fonte', 'texto', 'revisao/dados'):
        (p / d).mkdir(parents=True)
    shutil.copy(sys.argv[1], p / 'fonte' / ('livro' + Path(sys.argv[1]).suffix.lower()))
    (p / 'config.json').write_text('{"divisao_topo": "chapter", "quebra_secao": false}', encoding='utf-8')
    front = '---\ntitle: "teste"\nauthor: "zz"\nlang: pt-BR\n---\n'
    (p / 'texto' / 'livro.md').write_text(front, encoding='utf-8')
    st = {'config': {'tarefa': 'nenhuma'}}
    d = pipeline.diagnostico(p, st); print(st['mensagem'])
    pipeline.inventario(p, st); pipeline.extracao(p, st, lambda: False)          # (no EPUB não fazem nada; no PDF digital tiram texto e imagens)
    blocos = pipeline.estrutura(p, st); print(st['mensagem'])
    pipeline.rascunho(p, st); print(st['mensagem'])
    r = pipeline._le(p / 'revisao/dados/rascunho.json')['blocos']
    print('tipos:', dict(collections.Counter(b['tipo'] for b in r)), '| prefixos:', dict(collections.Counter(b.get('prefixo', '') for b in r)))
    import estilo
    capa = estilo.le(p).get('capa_origem')
    n_capa = sum(1 for b in blocos if capa and b['kind'] == 'image' and capa in b['text'])      # a capa sai do texto (um EPUB pode citá-la mais de uma vez)
    assert len(blocos) - n_capa == len(r), (len(blocos), n_capa, len(r))
    eh_pdf = sys.argv[1].lower().endswith('.pdf')
    # nada se perde: todo o texto do EPUB convertido está nos blocos
    if not eh_pdf:
        orig = ''.join((p / 'ocr' / 'epub.md').read_text(encoding='utf-8').split())
        nos_blocos = sum(len(''.join((b.get('prefixo', '') + b['fonte']).split())) for b in r)
        print(f'caracteres no EPUB convertido: {len(orig)} | nos blocos: {nos_blocos}')
        assert nos_blocos >= 0.99 * len(orig) - 200 * len(r), 'texto perdido na estrutura'
    for b in r:
        b['aceito'] = True
    md = revisao.monta(front, r, {})
    (p / 'texto' / 'livro.md').write_text(md, encoding='utf-8')
    imgs = [b['fonte'] for b in r if b['tipo'] == 'imagem']
    print('imagens:', imgs[:3], '| extraídas:', [str(x.relative_to(p / 'texto')) for x in (p / 'texto' / 'img').rglob('*') if x.is_file()][:5])
    print('\n'.join(l[:110] for l in md.split('\n')[5:26] if l))
    print('ok')
finally:
    if not manter:
        shutil.rmtree(p, ignore_errors=True)
