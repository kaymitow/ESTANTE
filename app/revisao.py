"""Revisão do rascunho: é AQUI (e só aqui) que o texto do pipeline vira texto aprovado, por aceite explícito do usuário.

O texto/livro.md é remontado a partir dos blocos aceitos, na ordem da fonte, com o marcador de página exato de cada um.
Edições de linha feitas direto no livro.md (Conferência, /api/editar) são preservadas: antes de remontar, cada linha que
difere da última montagem é guardada no bloco (campo linha_md). Se linhas foram acrescentadas ou removidas à mão, o aceite
recusa (409) em vez de sobrescrever. Cada aceite vira um commit.

    python app/revisao.py      -> autoteste da montagem
"""
import re, time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import pipeline
from extras import commit

router = APIRouter()
FRONT = re.compile(r'\A---\n.*?\n---\n', re.S)


def esc(s):
    """Escapa o que o Markdown do Pandoc leria como formatação."""
    return re.sub(r'([\\`*_{}\[\]<>#$@^~|])', r'\\\1', s)


def literal(t):
    """Linhas que o Markdown leria como lista ("1) ...", "a) ...", "III. ...", "- ...") ficam literais."""
    t = re.sub(r'^(\(?(?:\d+|[A-Za-z]|[IVXLCDMivxlcdm]+))([.)])(\s)', lambda m: m[1] + '\\' + m[2] + m[3], t)
    return re.sub(r'^([-+])(\s)', lambda m: '\\' + m[1] + m[2], t)


def linha(b):
    """Um bloco aceito -> uma linha do livro.md."""
    if b.get('linha_md'):
        return b['linha_md']                 # linha editada à mão no livro.md depois do aceite
    t = ' '.join((b.get('texto') or b['resultado']).split())
    if b.get('md'):                          # veio de EPUB: o texto já é Markdown (itálico, links), não se escapa
        return ('#' * (b.get('nivel') or 1) + ' ' + t.lstrip('# ')) if b['tipo'] == 'titulo' else b.get('prefixo', '') + t
    if b['tipo'] == 'titulo':
        return '#' * (b.get('nivel') or 1) + ' ' + esc(t.lstrip('# '))
    m = re.match(r'(\d{1,4})\.\s+(.*)', t)
    return f'[{m[1]}.]{{.pnum}} {esc(m[2])}' if m else literal(esc(t))


def pares(front, blocos, conf, todos=False):
    """Linhas do livro.md como (id do bloco ou None, linha). conf = {página: concordância da leitura}.
    todos=False (livro antigo, montado por aceite): só entram os aceitos. todos=True (livro gerado do rascunho): entram todos,
    menos os que o processamento não terminou (esses ficam de fora e são contados em gera_livro_md)."""
    out, pag = [(None, l) for l in front.rstrip('\n').split('\n')] + [(None, '')], None
    for b in blocos:
        if not b.get('aceito') and not (todos and b.get('status') != 'andamento'):
            continue
        n = b['paginas'][0]
        if n != pag:
            c = conf.get(n, 1.0)
            out += [(None, f'<!-- org: seção {n} do original -->' if b.get('md') and not b.get('pagina_pdf') else
                     f"<!-- pg: scan {n} · impressa ? · confiança {'ok' if c >= 0.85 else '?'} {c:.2f} -->"), (None, '')]
            pag = n
        out += [(b['id'], linha(b)), (None, '')]
    return out


def monta(front, blocos, conf, todos=False):
    return '\n'.join(l for _, l in pares(front, blocos, conf, todos))


def gera_livro_md(p: Path) -> dict:
    """Monta texto/livro.md com o rascunho inteiro, aceito ou não: a Revisão deixa de ser passo obrigatório.
    Marca o rascunho com livro_gerado, para que os aceites seguintes conferiram o livro.md com o mesmo critério.
    Blocos que o processamento não terminou ficam de fora e são contados (o original em inglês não entra no livro)."""
    dados, md = p / 'revisao' / 'dados', p / 'texto' / 'livro.md'
    r = pipeline._le(dados / 'rascunho.json')
    if not r or not md.exists():
        return {'gerado': False, 'motivo': 'ainda não há rascunho ou livro.md'}
    f = FRONT.match(md.read_text(encoding='utf-8'))
    if not f:
        return {'gerado': False, 'motivo': 'o livro.md está sem o cabeçalho (--- title … ---)'}
    conf = {}
    for b in r['blocos']:
        if b['paginas'][0] not in conf:
            conf[b['paginas'][0]] = (pipeline._le(p / 'ocr' / 'paginas' / f"{b['paginas'][0]:04d}.json") or {}).get('concordancia', 1.0)
    md.write_text(monta(f[0], r['blocos'], conf, todos=True), encoding='utf-8', newline='\n')
    r['livro_gerado'] = True
    pipeline._grava(dados / 'rascunho.json', r)
    de_fora = sum(b['status'] == 'andamento' and not b.get('aceito') for b in r['blocos'])
    return {'gerado': True, 'de_fora': de_fora}


def _corpo(md):
    return re.sub(r'<!--.*?-->', '', FRONT.sub('', md), flags=re.S).strip()


def sincroniza(atual, front, blocos, conf, gerado=False):
    """Traz para os blocos as linhas editadas à mão no livro.md. Recusa se o arquivo não corresponde à última montagem.
    gerado=True: o livro.md veio do rascunho inteiro (gera_livro_md), então a comparação é com todos os blocos."""
    if not gerado and not any(b.get('aceito') for b in blocos):
        if _corpo(atual):
            raise HTTPException(409, 'este livro já tem texto aprovado feito fora do pipeline; o aceite não vai sobrescrevê-lo')
        return
    velho, cur = pares(front, blocos, conf, todos=gerado), atual.split('\n')
    por_id = {b['id']: b for b in blocos}
    if len(velho) != len(cur) or any(l != c for (bid, l), c in zip(velho, cur) if bid is None):
        raise HTTPException(409, 'o livro.md teve linhas acrescentadas, removidas ou marcadores alterados à mão; o aceite não vai sobrescrever. '
                                 'Desfaça a mudança pelo histórico ou continue editando direto no texto.')
    for (bid, l), c in zip(velho, cur):
        if l != c:
            por_id[bid]['linha_md'] = c


class Aceite(BaseModel):
    ids: list[str] = []
    texto: str | None = None        # texto editado pelo usuário (só com um id)
    aprovados: bool = False         # todos os que os modelos aprovaram e ainda não foram aceitos
    desfazer: bool = False
    nivel: int | None = None        # só muda o tipo do bloco (0 = parágrafo, 1 a 6 = título desse nível), sem aceitar nem tirar
    auto: bool = False              # aceite feito pelo app ao fim do processamento (opção "aceite automático"): fica no commit


@router.post('/api/revisao/{livro}/aceitar')
def aceitar(livro: str, a: Aceite):
    try:
        p = pipeline.pasta(livro)
    except FileNotFoundError:
        raise HTTPException(404, 'livro não encontrado')
    dados, md = p / 'revisao' / 'dados', p / 'texto' / 'livro.md'
    r = pipeline._le(dados / 'rascunho.json')
    if not r:
        raise HTTPException(404, 'ainda não há rascunho')
    if a.texto is not None and len(a.ids) != 1:
        raise HTTPException(400, 'texto editado vale para um bloco por vez')
    alvo = set(a.ids) | ({b['id'] for b in r['blocos'] if b['status'] == 'aprovado' and not b.get('aceito')} if a.aprovados else set())
    if not a.desfazer and any(b['id'] in alvo and b['status'] == 'andamento' for b in r['blocos']):
        raise HTTPException(409, 'esse bloco ainda está sendo trabalhado pelos modelos: espere o processamento terminar para aceitar')
    atual = md.read_text(encoding='utf-8')
    f = FRONT.match(atual)
    if not f:
        raise HTTPException(409, 'o livro.md está sem o cabeçalho (--- title … ---)')
    conf = {}
    for b in r['blocos']:
        if b['paginas'][0] not in conf:
            conf[b['paginas'][0]] = (pipeline._le(p / 'ocr' / 'paginas' / f"{b['paginas'][0]:04d}.json") or {}).get('concordancia', 1.0)
    sincroniza(atual, f[0], r['blocos'], conf, gerado=bool(r.get('livro_gerado')))
    # marca de link ou nota que o modelo deixou pela metade (<a1> sem par, <n3/>) não pode entrar no livro: quebraria o EPUB
    sobra = {b['id']: pipeline.duplo.MARCA.search((a.texto if a.texto is not None and b['id'] in a.ids else b.get('texto') or b['resultado']).replace('<br>', ''))
             for b in r['blocos'] if b['id'] in alvo and a.nivel is None and not a.desfazer}
    sobra = {k: m[0] for k, m in sobra.items() if m}
    if sobra and a.ids:
        k, marca = next(iter(sobra.items()))
        raise HTTPException(400, f'o bloco {k} ainda tem a marca {marca} no texto (link ou nota que o modelo não devolveu inteiro). Corrija o texto antes de aceitar.')
    alvo -= set(sobra)                      # no "aceitar todos os aprovados", esses ficam de fora
    n = 0
    for b in r['blocos']:
        if b['id'] in alvo:
            if a.nivel is not None:                 # a detecção de título é um palpite: o usuário corrige aqui
                if b['tipo'] == 'imagem' or not 0 <= a.nivel <= 6:
                    raise HTTPException(400, 'tipo de bloco inválido')
                b['tipo'] = 'titulo' if a.nivel else 'paragrafo'
                b['nivel'] = a.nivel or None
                b.pop('linha_md', None)
            else:
                b['aceito'] = not a.desfazer
                if a.desfazer:
                    b.pop('aceito_em', None); b.pop('aceito_auto', None)
                elif a.auto:
                    b['aceito_auto'] = True
                else:
                    b['aceito_em'] = time.time()      # o commit deste aceite é o primeiro depois desta hora (ver app/prova.py)
            if a.texto is not None:
                b['texto'] = a.texto.strip(); b.pop('linha_md', None)
            n += 1
    if not n:
        raise HTTPException(400, 'nenhum bloco para aceitar')
    pipeline._grava(dados / 'rascunho.json', r)
    conta = {'mudados': n, 'aceitos': sum(bool(b.get('aceito')) for b in r['blocos']), 'total': len(r['blocos'])}
    if a.nivel is not None and not any(b['id'] in alvo and b.get('aceito') for b in r['blocos']):
        return conta                                # bloco ainda fora do livro: nada a regravar
    md.write_text(monta(f[0], r['blocos'], conf, todos=bool(r.get('livro_gerado'))), encoding='utf-8', newline='\n')
    verbo = 'Muda o tipo de' if a.nivel is not None else 'Desfaz aceite de' if a.desfazer else 'Aceita'
    commit(f"{verbo} {n} bloco{'s' if n > 1 else ''} em {livro}" + (f' ({a.ids[0]})' if len(alvo) == 1 and a.ids else '') + (' (automático)' if a.auto else ''), md, dados / 'rascunho.json')
    return {'mudados': n, 'aceitos': sum(bool(b.get('aceito')) for b in r['blocos']), 'total': len(r['blocos'])}


def aceita_automatico(livro: str) -> dict:
    """Fim do processamento, com a opção "aceite automático" ligada: aceita todo bloco que ainda não foi aceito, inclusive os que
    pediam atenção (o usuário escolheu isso: o que o modelo local não resolveu fica no livro). Ficam de fora, e são contados:
    blocos que não terminaram (status "andamento": o resultado ainda é o original) e blocos com marca de link quebrada, que
    não pode entrar no livro. Cada aceite vira commit marcado como automático (ver app/prova.py)."""
    p = pipeline.pasta(livro)
    r = pipeline._le(p / 'revisao' / 'dados' / 'rascunho.json') or {'blocos': []}
    pendentes = [b for b in r['blocos'] if not b.get('aceito')]
    ids = [b['id'] for b in pendentes if b['status'] != 'andamento'
           and not pipeline.duplo.MARCA.search((b.get('texto') or b['resultado'] or '').replace('<br>', ''))]
    if ids:
        aceitar(livro, Aceite(ids=ids, auto=True))
    return {'aceitos': len(ids), 'ficaram_de_fora': len(pendentes) - len(ids)}


@router.get('/api/livro/{livro}/pagina/{n}')
def pagina(livro: str, n: int):
    """Imagem da página do PDF de origem, para conferir ao lado do texto."""
    import pymupdf
    try:
        pdf = pipeline._pdf(pipeline.pasta(livro))
    except FileNotFoundError:
        pdf = None
    if not pdf:
        raise HTTPException(404, 'sem PDF em fonte/')
    doc = pymupdf.open(str(pdf))
    if not 1 <= n <= len(doc):
        raise HTTPException(404, 'página fora do intervalo')
    return Response(doc[n - 1].get_pixmap(dpi=110).tobytes('jpeg', jpg_quality=80), media_type='image/jpeg',
                    headers={'Cache-Control': 'max-age=3600'})


def _marca(r):
    """Em que pé está um bloco no trabalho dos modelos (r = linha da fila, ou None se ele não passou por lá)."""
    limpo = lambda ok, ch: bool(ok) and ch in (None, '', '[]')      # noqa: E731
    if not r or r['proposta'] is None:
        return 'espera'
    if r['aud_ok'] is None:
        return 'proposto'
    if limpo(r['aud_ok'], r['checagem']):
        return 'conferido'
    if r['aud2_ok'] is None:
        return 'objecao'
    if limpo(r['aud2_ok'], r['checagem2']):
        return 'conferido'
    if r['julgado']:
        return 'juiz'
    if r['juiz'] or r['estado'] in ('aprovado', 'revisar'):
        return 'conferido' if r['estado'] == 'aprovado' else 'voce'
    return 'disputa'


def _paginas_do_vivo(blocos, pdf, cabe=1800, linhas=14):
    """Em que página do livro ao vivo fica cada bloco. PDF: a página do arquivo (há imagem dela). Outros formatos não têm página
    (num EPUB a "página" seria o capítulo inteiro): o texto é repartido em páginas de uns 1.800 caracteres ou 14 blocos (créditos e sumário são
    muitas linhas curtas), sem partir bloco, e título depois de texto corrido abre página."""
    if pdf:
        return {b['id']: b['source_pages'][0] for b in blocos}
    onde, n, cheio, quantos, corrido = {}, 1, 0, 0, False
    for b in blocos:
        if cheio and (cheio + len(b['text']) > cabe or quantos >= linhas or (b['kind'] == 'heading' and corrido)):
            n, cheio, quantos, corrido = n + 1, 0, 0, False
        onde[b['id']] = n
        cheio += len(b['text']); quantos += 1; corrido = corrido or (b['kind'] != 'heading' and len(b['text']) > 200)
    return onde


@router.get('/api/livro/{livro}/vivo/{n}')
def vivo(livro: str, n: int):
    """Livro ao vivo: os blocos de uma página do original com o que os modelos já fizeram em cada um. n = 0 pede a página em que
    o trabalho está agora (ou a primeira). Nada aqui é texto aprovado: é o andamento, para acompanhar."""
    import json
    p = pipeline.pasta(livro)
    src = pipeline._le(p / 'fonte' / 'dados' / 'source.json') or {}
    blocos = [b for b in src.get('blocks', []) if b.get('kind') in ('paragraph', 'heading') and b.get('text') and b.get('source_pages')]
    if not blocos:
        raise HTTPException(404, 'o texto deste livro ainda não foi extraído')
    st = pipeline._le(p / 'revisao/dados/pipeline.json', {}) or {}
    its = {r['raw']: r for r in pipeline.fila.todos('select * from item where trabalho=?', (st['trabalho'],))} if st.get('trabalho') else {}
    try:
        imagem = bool(pipeline._pdf(p))
    except FileNotFoundError:
        imagem = False
    onde = _paginas_do_vivo(blocos, imagem)      # id do bloco -> página do livro ao vivo
    pags = sorted(set(onde.values()))
    agora = None
    em_pauta = pipeline.duplo.AO_VIVO.get('fonte') if pipeline.estado(livro).get('rodando_agora') else None
    if em_pauta:
        # o bloco em pauta é achado pelo texto que o modelo recebeu (o começo basta: o pedido pode trazer o texto com marcas a mais no fim)
        chave = em_pauta.strip()[:80]
        agora = next(({'id': b['id'], 'pagina': onde[b['id']]} for b in blocos if ((its.get(b['id']) or {'fonte': ''})['fonte'] or '').strip()[:80] == chave), None)
    if n not in pags:
        n = agora['pagina'] if agora else pags[0]
    k = pags.index(n)
    saida = []
    for b in blocos:
        if onde[b['id']] != n:
            continue
        r = its.get(b['id'])
        m = _marca(r)
        obj = json.loads(r['aud2_prob'] or r['aud_prob'] or '[]') + json.loads(r['checagem2'] or r['checagem'] or '[]') if r and m in ('objecao', 'disputa', 'voce', 'juiz') else []
        saida.append({'id': b['id'], 'titulo': b['kind'] == 'heading', 'fonte': b['text'], 'marca': m, 'objecoes': [str(o)[:300] for o in obj][:6],
                      'texto': (r['julgado'] or r['revisado'] or r['proposta']) if r else None, 'continua': imagem and len(b['source_pages']) > 1})
    return {'pagina': n, 'n': k + 1, 'total': len(pags), 'anterior': pags[k - 1] if k else None, 'proxima': pags[k + 1] if k + 1 < len(pags) else None,
            'imagem': imagem, 'agora': agora, 'processado': bool(its), 'blocos': saida}


if __name__ == '__main__':
    L = lambda **k: dict({'proposta': None, 'aud_ok': None, 'checagem': None, 'aud2_ok': None, 'checagem2': None, 'julgado': None, 'juiz': None, 'estado': 'na fila'}, **k)      # noqa: E731
    assert [_marca(x) for x in (None, L(), L(proposta='a'), L(proposta='a', aud_ok=1), L(proposta='a', aud_ok=1, checagem='["x"]'), L(proposta='a', aud_ok=0, aud2_ok=1),
                                L(proposta='a', aud_ok=0, aud2_ok=0), L(proposta='a', aud_ok=0, aud2_ok=0, julgado='b', juiz='{}'), L(proposta='a', aud_ok=0, aud2_ok=0, juiz='{}', estado='revisar'),
                                L(proposta='a', aud_ok=0, aud2_ok=0, juiz='{}', estado='aprovado'))] == \
        ['espera', 'espera', 'proposto', 'conferido', 'objecao', 'conferido', 'disputa', 'juiz', 'voce', 'conferido']
    B = lambda i, k, t: {'id': i, 'kind': k, 'text': t, 'source_pages': [7]}      # noqa: E731
    assert _paginas_do_vivo([B('a', 'heading', 'T'), B('b', 'paragraph', 'x' * 1000), B('c', 'paragraph', 'x' * 1000), B('d', 'heading', 'U'), B('e', 'paragraph', 'y')], False) == {'a': 1, 'b': 1, 'c': 2, 'd': 3, 'e': 3}
    assert max(_paginas_do_vivo([B(str(k), 'paragraph', 'linha curta') for k in range(30)], False).values()) == 3      # 14 por página
    assert set(_paginas_do_vivo([B('a', 'paragraph', 'x')], True).values()) == {7}
    bl = [{'id': 'a', 'tipo': 'titulo', 'paginas': [3], 'resultado': 'Introdução', 'aceito': True},
          {'id': 'b', 'tipo': 'paragrafo', 'paginas': [3, 4], 'resultado': '1. Texto *com*\nquebra.', 'aceito': True},
          {'id': 'c', 'tipo': 'paragrafo', 'paginas': [4], 'resultado': 'não aceito'},
          {'id': 'd', 'tipo': 'paragrafo', 'paginas': [4], 'resultado': 'a) item', 'texto': 'a) item editado', 'aceito': True}]
    front = '---\ntitle: "x"\n---\n'
    t = monta(front, bl, {4: 0.8})
    assert t.split('\n') == ['---', 'title: "x"', '---', '', '<!-- pg: scan 3 · impressa ? · confiança ok 1.00 -->', '', '# Introdução', '',
                             '[1.]{.pnum} Texto \\*com\\* quebra.', '', '<!-- pg: scan 4 · impressa ? · confiança ? 0.80 -->', '', 'a\\) item editado', ''], t
    assert re.search(r'<!-- pg: scan (\d+) · impressa (.*?) · confiança (\S+) ([\d.]+) -->', t)      # formato lido por ferramentas/conferencia.py
    assert not _corpo('---\na: 1\n---\n\n<!-- só comentário -->\n') and _corpo('---\na: 1\n---\n\ntexto')
    sincroniza(t.replace('# Introdução', '# Introdução à mão'), front, bl, {4: 0.8})
    assert bl[0]['linha_md'] == '# Introdução à mão'
    try:
        sincroniza(t + 'linha a mais\n', front, bl, {4: 0.8}); raise SystemExit('devia recusar')
    except HTTPException:
        pass
    print('ok')
