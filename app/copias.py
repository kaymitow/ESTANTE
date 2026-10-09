"""Comparar o livro com OUTRA cópia do mesmo texto (outra edição, outro arquivo, de onde for), bloco a bloco.

Serve para achar cortes, acréscimos e palavras trocadas entre edições. A outra cópia NUNCA escreve no texto do livro:
o resultado é só um relatório para o usuário ler. A cópia fica guardada em <livro>/fonte/outras-copias/.

Como compara: a outra cópia vira uma fila de palavras (sem pontuação, maiúsculas nem hifenização); cada bloco da fonte é
localizado nela pelas sequências de 4 palavras do começo e do fim do bloco, sempre andando para a frente; o trecho achado
é comparado palavra por palavra. Bloco não localizado = "não está na outra cópia". Trecho da cópia que sobra entre dois
blocos vizinhos = "só na outra cópia" (possível corte na nossa fonte).
"""
import difflib, html, io, json, re, time, unicodedata, zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
RAIZ = Path(__file__).resolve().parent.parent
ACEITOS = ('.epub', '.pdf', '.txt', '.md', '.html', '.htm')


def palavras(t):
    """Só as palavras: aspas, travessões, pontuação, maiúsculas e hífen de fim de linha não contam como diferença."""
    t = unicodedata.normalize('NFKC', t)
    t = re.sub(r'(\w)-[ \t]*\n[ \t]*(\w)', r'\1\2', t).replace('’', "'").replace('‘', "'")
    return [w for w in (p.strip("'") for p in re.findall(r"[\w']+", t.lower())) if w]      # o apóstrofo só conta dentro da palavra (don't); nas pontas é aspa


def texto_da_copia(dados, ext):
    """O texto corrido da outra cópia, na ordem de leitura."""
    # link e span somem sem deixar espaço ("<a>makes</a>the" é "makesthe" na cópia como é na fonte); as outras marcas separam,
    # inclusive as de ênfase, porque na fonte o asterisco do itálico também separa ("extent*failed*")
    sem_tags = lambda s: html.unescape(re.sub(r'<[^>]+>', ' ', re.sub(r'</?(?:a|span|font)\b[^>]*>', '',      # noqa: E731
                                                                      re.sub(r'<(script|style)\b.*?</\1>', ' ', s, flags=re.S | re.I), flags=re.I)))
    if ext == '.epub':
        z = zipfile.ZipFile(io.BytesIO(dados))
        opf_nome = next((n for n in z.namelist() if n.endswith('.opf')), None)
        ordem = []
        if opf_nome:      # ordem de leitura declarada no próprio EPUB
            opf = z.read(opf_nome).decode('utf-8', 'replace')
            itens = dict(re.findall(r'<item\b[^>]*?\bid="([^"]+)"[^>]*?\bhref="([^"]+)"', opf)) | {i: h for h, i in re.findall(r'<item\b[^>]*?\bhref="([^"]+)"[^>]*?\bid="([^"]+)"', opf)}
            base = opf_nome.rsplit('/', 1)[0] + '/' if '/' in opf_nome else ''
            ordem = [base + itens[i] for i in re.findall(r'<itemref\b[^>]*?\bidref="([^"]+)"', opf) if i in itens]
        ordem = [n for n in ordem if n in z.namelist()] or sorted(n for n in z.namelist() if n.lower().endswith(('.xhtml', '.html', '.htm')))
        return '\n\n'.join(sem_tags(z.read(n).decode('utf-8', 'replace')) for n in ordem)
    if ext == '.pdf':
        import pymupdf
        doc = pymupdf.open(stream=dados, filetype='pdf')
        # cabeçalho corrido e número de página não são texto do livro: linha curta nas pontas da página que se repete em muitas páginas
        # (ignorando os números) sai, como na extração da fonte; sem isso cada virada de página aparecia como "palavra diferente"
        pags = [[l.strip() for l in pg.get_text().split('\n') if l.strip()] for pg in doc]
        chave = lambda l: re.sub(r'[\W\d_]+', '', l.lower())      # noqa: E731
        ponta = lambda ls, i: (i < 2 or i >= len(ls) - 2) and len(ls[i]) < 60      # noqa: E731
        cont = {}
        for ls in pags:
            for k in {chave(ls[i]) for i in range(len(ls)) if ponta(ls, i)}:
                cont[k] = cont.get(k, 0) + 1
        fora = {k for k, c in cont.items() if not k or c >= max(2, 0.2 * len(pags))}      # chave vazia = linha só de número
        return '\n\n'.join('\n'.join(l for i, l in enumerate(ls) if not (ponta(ls, i) and chave(l) in fora)) for ls in pags)
    t = dados.decode('utf-8', 'replace')
    return sem_tags(t) if ext in ('.html', '.htm') else t


def sem_marcacao(md):
    """Texto de um bloco da fonte sem a marcação do Markdown (endereços de link, notas, ênfase)."""
    md = re.sub(r'<[^>]+>', ' ', md)      # <br> e outras marcas
    md = re.sub(r'(?:^|(?<=\s))\d{1,3}\.\s{2,}', ' ', md)      # número de item de lista ("1.  texto", com dois espaços): é marcação, a outra cópia não o traz
    return re.sub(r'[*_#>]|\[\^[^\]]+\]', ' ', re.sub(r'!?\[([^\]]*)\]\((?:[^()\s]|\([^()\s]*\))+\)', r'\1', md))


def compara(blocos, copia):
    """blocos = [(id, texto)] da fonte; copia = texto da outra cópia. Devolve {'resumo', 'diferencas', 'ausentes', 'so_na_copia'}."""
    W = palavras(copia)
    onde = {}
    for i in range(len(W) - 3):
        onde.setdefault(tuple(W[i:i + 4]), []).append(i)

    def acha(g, minimo):      # primeira ocorrência da sequência a partir de `minimo`
        return next((p for p in onde.get(g, ()) if p >= minimo), None)
    pos, itens, ausentes, difs, iguais, curtos = 0, [], [], [], 0, 0      # itens: um por bloco, [id, palavras, início, fim, texto] (início None = não localizado)
    for bid, texto in blocos:
        a = palavras(sem_marcacao(texto))
        if len(a) < 6:          # título ou linha curta: não dá para localizar sozinho; fica para depois, entre os vizinhos
            itens.append([bid, a, None, None, texto]); continue
        ini = fim = None
        for i in range(0, min(len(a) - 3, 14)):
            p = acha(tuple(a[i:i + 4]), max(0, pos - 5))
            if p is not None and p - i < pos + 3000 + 20 * len(a):      # não salta para longe: o mesmo trecho pode se repetir no fim do livro
                ini = max(0, p - i); break
        if ini is not None:
            for j in range(len(a) - 4, max(len(a) - 18, -1), -1):
                p = acha(tuple(a[j:j + 4]), ini)
                if p is not None and p - ini < 2.2 * len(a) + 40:
                    fim = p + len(a) - j; break
        b = W[ini:fim] if ini is not None and fim is not None else []
        # não localizado, ou achou as pontas mas o miolo é outro texto
        if len(b) < 0.4 * len(a) or difflib.SequenceMatcher(None, a, b, autojunk=False).quick_ratio() < 0.5:
            ausentes.append({'id': bid, 'trecho': ' '.join(texto.split())[:240]}); itens.append([bid, None, None, None, texto]); continue
        itens.append([bid, a, ini, fim, texto]); pos = fim
        if a == b or ''.join(a) == ''.join(b):
            iguais += 1; continue
        cod = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
        ops = [{'op': op, 'nosso': ' '.join(a[i1:i2]), 'outra': ' '.join(b[j1:j2]), 'antes': ' '.join(a[max(0, i1 - 6):i1])}
               for k, (op, i1, i2, j1, j2) in enumerate(cod)
               if op != 'equal' and ''.join(a[i1:i2]) != ''.join(b[j1:j2]) and not (op == 'insert' and k in (0, len(cod) - 1))]      # sobra nas pontas é do bloco vizinho
        if ops:
            difs.append({'id': bid, 'mudancas': ops[:12], 'total': len(ops)})
        else:
            iguais += 1
    # blocos curtos (títulos, datas, linhas de uma frase): procurados só no intervalo entre os dois vizinhos já localizados.
    # Sem vizinho dos dois lados, ou com os vizinhos longe um do outro, nada se afirma: o bloco fica como não comparado.
    for k, it in enumerate(itens):
        bid, a, ini, _, texto = it
        if a is None or ini is not None:
            continue
        antes = next((x[3] for x in reversed(itens[:k]) if x[2] is not None), None)
        depois = next((x[2] for x in itens[k + 1:] if x[2] is not None), None)
        if not a or antes is None or depois is None or not 0 <= depois - antes <= 400:
            curtos += 1; continue
        vao, n = W[antes:depois], len(a)
        janelas = [(i, vao[i:i + n]) for i in range(len(vao) - n + 1)] or ([(0, vao)] if vao else [])      # intervalo menor que o bloco: compara com ele inteiro
        p = next((i for i, j in janelas if j == a), None)
        if p is not None:
            it[2], it[3] = antes + p, antes + p + n; iguais += 1; continue
        nota, i, j = max(((difflib.SequenceMatcher(None, a, j, autojunk=False).ratio(), -i, j) for i, j in janelas), default=(0, 0, []))
        if nota >= 0.5:      # está lá, com palavra diferente
            it[2], it[3] = antes - i, antes - i + len(j)
            difs.append({'id': bid, 'mudancas': [{'op': 'replace', 'nosso': ' '.join(a), 'outra': ' '.join(j), 'antes': ''}], 'total': 1})
        else:
            ausentes.append({'id': bid, 'trecho': ' '.join(texto.split())[:240]})
    ordem = {b[0]: k for k, b in enumerate(blocos)}
    difs.sort(key=lambda d: ordem[d['id']]); ausentes.sort(key=lambda d: ordem[d['id']])
    achados = [(x[0], x[2], x[3]) for x in itens if x[2] is not None]
    sobras, ant, ant_id = [], 0, None
    for bid, ini, fim in achados + [(None, len(W), len(W))]:
        if achados and ini - ant > 40 and (ant_id is not None or bid is not None):      # mais de 40 palavras da cópia sem dono
            sobras.append({'depois_de': ant_id, 'antes_de': bid, 'palavras': ini - ant, 'trecho': ' '.join(W[ant:ant + 70])})
        ant, ant_id = fim, bid
    return {'resumo': {'blocos': len(blocos), 'comparados': len(blocos) - curtos, 'nao_comparados': curtos, 'iguais': iguais, 'diferentes': len(difs), 'ausentes': len(ausentes),
                       'so_na_copia': len(sobras), 'palavras_da_copia': len(W)},
            'diferencas': difs, 'ausentes': ausentes, 'so_na_copia': sobras}


def _livro(nome):
    p = (RAIZ / 'livros' / nome).resolve()
    if p.parent != (RAIZ / 'livros').resolve() or not p.is_dir():
        raise HTTPException(404, 'livro não encontrado')
    return p


@router.get('/api/copias/{livro}')
def lista(livro: str):
    """Comparações já feitas para este livro (a mais recente primeiro)."""
    d = _livro(livro) / 'revisao' / 'dados'
    return sorted((json.loads(f.read_text(encoding='utf-8')) for f in d.glob('copia-*.json')), key=lambda r: -r['quando']) if d.exists() else []


@router.post('/api/copias/{livro}')
async def nova(livro: str, request: Request, arquivo: str):
    """Corpo = bytes da outra cópia. Guarda em fonte/outras-copias/ e compara com os blocos da fonte do livro."""
    return _guarda_e_compara(_livro(livro), await request.body(), arquivo)


class DoAcervo(BaseModel):
    url: str
    nome: str = ''


@router.post('/api/copias/{livro}/baixar')
def do_acervo(livro: str, d: DoAcervo):
    """Baixa outra edição de um acervo aberto (mesmas regras e mesma chave de rede do download de livros) e compara."""
    import rede
    p = _livro(livro)
    try:
        dados, ext = rede.busca_arquivo(d.url)
    except rede.Desligado as ex:
        raise HTTPException(403, str(ex))
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    except OSError:
        raise HTTPException(502, 'o acervo não respondeu ou o download foi interrompido')
    return _guarda_e_compara(p, dados, (d.nome.strip() or 'edicao-do-acervo') + ext)


def _guarda_e_compara(p, dados, arquivo):
    fonte = p / 'fonte' / 'dados' / 'source.json'
    if not fonte.exists():
        raise HTTPException(400, 'o texto deste livro ainda não foi extraído: processe o livro primeiro')
    ext = Path(arquivo).suffix.lower()
    if ext not in ACEITOS:
        raise HTTPException(400, 'formato não aceito para comparação. Aceitos: ' + ', '.join(e[1:].upper() for e in ACEITOS))
    try:
        copia = texto_da_copia(dados, ext)
    except Exception:      # noqa: BLE001
        raise HTTPException(400, 'não foi possível ler esse arquivo')
    if len(palavras(copia)) < 200:
        raise HTTPException(400, 'quase não há texto nesse arquivo (é um scan sem texto?)')
    nome = re.sub(r'[^\w.-]+', '-', Path(arquivo).stem).strip('-')[:60] or 'copia'
    (p / 'fonte' / 'outras-copias').mkdir(parents=True, exist_ok=True)
    (p / 'fonte' / 'outras-copias' / (nome + ext)).write_bytes(dados)
    blocos = [(b['id'], b['text']) for b in json.loads(fonte.read_text(encoding='utf-8'))['blocks'] if b.get('kind') in ('paragraph', 'heading') and b.get('text')]
    r = {'arquivo': Path(arquivo).name, 'quando': time.time(), 'data': time.strftime('%d/%m/%Y %H:%M'), **compara(blocos, copia)}
    (p / 'revisao' / 'dados' / f'copia-{nome}.json').write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding='utf-8')
    return r


if __name__ == '__main__':      # autoteste: python app/copias.py
    import random
    rnd = random.Random(3); vocab = [''.join(rnd.choice('abcdefghijlmnoprstuv') for _ in range(rnd.randint(4, 9))) for _ in range(900)]
    base = [' '.join(rnd.choice(vocab) for _ in range(40)) + ' coisa bem específica ' + ' '.join(rnd.choice(vocab) for _ in range(20)) + '.' for n in range(30)]
    fonte = [(f'b{n}', t) for n, t in enumerate(base, 1)]
    r = compara(fonte, '\n\n'.join(base))['resumo']
    assert r['iguais'] == 30 and r['diferentes'] == r['ausentes'] == r['so_na_copia'] == 0, r
    outra = list(base)
    outra[4] = outra[4].replace('bem específica', 'muito vaga')            # palavra trocada no bloco 5
    del outra[9]                                                            # o bloco 10 foi cortado na outra cópia
    outra.insert(20, 'Este trecho inteiro só existe na outra edição. ' * 12)      # acréscimo depois do bloco 21
    c = compara(fonte, '\n\n'.join(outra))
    assert [d['id'] for d in c['diferencas']] == ['b5'] and c['diferencas'][0]['mudancas'][0]['nosso'] == 'bem específica', c['diferencas']
    assert [a['id'] for a in c['ausentes']] == ['b10'], c['ausentes']
    assert len(c['so_na_copia']) == 1 and c['so_na_copia'][0]['depois_de'] == 'b21', c['so_na_copia']
    assert palavras('suffe-\nring “Aspas” — fim.') == ['suffering', 'aspas', 'fim'] and palavras("‘hbd’ don't ' x") == ['hbd', "don't", 'x']
    assert palavras(sem_marcacao('1.  Um item. 2.  Outro, de 1930. 3.0 fica.')) == ['um', 'item', 'outro', 'de', '1930', '3', '0', 'fica']
    assert palavras(texto_da_copia('<p>blog <a href="x">makes</a>the <em>point</em>.</p><p>Outro</p>'.encode(), '.html')) == ['blog', 'makesthe', 'point', 'outro']
    # blocos curtos, entre vizinhos localizados: igual, com palavra trocada, cortado; e o que não tem palavras não é comparado
    com_t = fonte[:3] + [('t1', '## Capítulo dois')] + fonte[3:6] + [('t2', 'Maio de 1925')] + fonte[6:9] + [('t3', 'Uma linha curta'), ('t4', '* * *')] + fonte[9:]
    copia_t = base[:3] + ['Capítulo dois'] + base[3:6] + ['Junho de 1925'] + base[6:]
    c = compara(com_t, '\n\n'.join(copia_t))
    assert [d['id'] for d in c['diferencas']] == ['t2'] and c['diferencas'][0]['mudancas'][0]['outra'] == 'junho de 1925', c['diferencas']
    assert [a['id'] for a in c['ausentes']] == ['t3'] and c['resumo']['nao_comparados'] == 1 and c['resumo']['iguais'] == 31, c['resumo']
    print('ok')
