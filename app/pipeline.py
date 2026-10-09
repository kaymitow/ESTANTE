"""Pipeline do livro novo, de ponta a ponta (etapas 0 a 5). Cada etapa grava em arquivos do próprio livro e pode ser retomada.

  0 diagnostico   páginas, texto digital ou scan, idioma provável        -> revisao/dados/diagnostico.json
  1 inventario    tabela de páginas                                      -> revisao/inventario.csv
  2 extracao      digital: blocos do PDF; scan: dois modelos leem cada página, de forma independente
                                                                         -> ocr/paginas/NNN.json
  3 estrutura     tira cabeçalhos/numeração, une parágrafos entre páginas, marca títulos
                                                                         -> fonte/dados/source.json
  4 transformacao traduzir / atualizar português (fila persistente de dois modelos), com o glossário no prompt
  5 rascunho      resultado por bloco, com status e problemas            -> revisao/dados/rascunho.json

O estado fica em revisao/dados/pipeline.json. NADA aqui toca em texto/livro.md nem em fonte/*.pdf:
o texto só vira "aprovado" quando o usuário aceita, na revisão.
"""
import base64, csv, json, re, subprocess, threading, time, unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import duplo
import epub
import estilo
import fila

RAIZ = Path(__file__).resolve().parent.parent
ETAPAS = ['diagnostico', 'inventario', 'extracao', 'estrutura', 'transformacao', 'rascunho']
_threads: dict[str, threading.Thread] = {}
_conta_rascunho: dict[str, tuple] = {}      # livro -> (data do arquivo, contagem): a tela consulta o estado várias vezes por segundo
_pedidos: set[str] = set()      # livros com pedido de pausa (em memória: o arquivo de estado é regravado o tempo todo pela thread)
FIM_FRASE = re.compile(r'[.!?:;…"”»)\]]\s*$')
SO_NUMERO = re.compile(r'^\W*(\d{1,4}|[ivxlcdm]{1,7})\W*$', re.I)
CLITICOS = {'se', 'me', 'te', 'lhe', 'lhes', 'nos', 'vos', 'o', 'a', 'os', 'as', 'lo', 'la', 'los', 'las', 'no', 'na', 'nos', 'nas', 'á', 'ão', 'ia', 'iam', 'ei', 'emos'}
PALAVRAS = {'pt': ' de que não uma para com os das dos como mais ', 'en': ' the and of to that is in it for with ', 'de': ' der die und das ist nicht den von zu mit '}


def pasta(livro):
    p = (RAIZ / 'livros' / livro).resolve()
    if p.parent != (RAIZ / 'livros').resolve() or not p.is_dir():
        raise FileNotFoundError(livro)
    return p


_arq = threading.RLock()      # leitura e escrita dos JSON de estado, uma de cada vez dentro do processo


def _le(f, padrao=None):
    for tentativa in range(8):
        try:
            with _arq:
                return json.loads(f.read_text(encoding='utf-8')) if f.exists() else padrao
        except (PermissionError, json.JSONDecodeError):     # no Windows, outro leitor pode estar com o arquivo aberto
            time.sleep(0.05 * (tentativa + 1))
    return padrao


def _grava(f, d):
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + f'.{threading.get_ident()}.tmp')
    texto = json.dumps(d, ensure_ascii=False, indent=1)
    with _arq:
        tmp.write_text(texto, encoding='utf-8')
        for tentativa in range(10):
            try:
                tmp.replace(f)
                return
            except PermissionError:
                time.sleep(0.05 * (tentativa + 1))
        f.write_text(texto, encoding='utf-8')        # último recurso: grava direto
        tmp.unlink(missing_ok=True)


def impedimento(p):
    """Motivo para NÃO rodar o pipeline neste livro: ele já tem texto ou fonte estruturada feitos fora do pipeline (seriam sobrescritos)."""
    src = _le(p / 'fonte' / 'dados' / 'source.json')
    if src and not src.get('gerado_por'):
        return 'este livro já tem um texto-fonte estruturado feito à mão (fonte/dados/source.json)'
    md = p / 'texto' / 'livro.md'
    if md.exists() and not any(b.get('aceito') for b in (_le(p / 'revisao/dados/rascunho.json') or {}).get('blocos', [])):
        corpo = re.sub(r'\A---\n.*?\n---\n', '', md.read_text(encoding='utf-8'), flags=re.S)
        if re.sub(r'<!--.*?-->', '', corpo, flags=re.S).strip():
            return 'este livro já tem texto aprovado feito fora do processamento automático'
    return None


def estado(livro):
    p = pasta(livro)
    st = _le(p / 'revisao/dados/pipeline.json', {'estado': 'novo', 'etapa': None, 'feitas': [], 'progresso': 0, 'mensagem': '', 'config': {}})
    st['rodando_agora'] = livro in _threads and _threads[livro].is_alive()
    st['impedimento'] = None if st['rodando_agora'] or st.get('feitas') else impedimento(p)      # quem já passou da largada não tem impedimento
    if st['rodando_agora'] and duplo.AO_VIVO:
        st['ao_vivo'] = dict(duplo.AO_VIVO, segundos=round(time.time() - duplo.AO_VIVO.get('inicio', time.time()), 1))
    fr = p / 'revisao/dados/rascunho.json'
    if fr.exists():
        m = fr.stat().st_mtime_ns
        if _conta_rascunho.get(livro, (0,))[0] != m:
            bl = (_le(fr) or {}).get('blocos', [])
            _conta_rascunho[livro] = (m, {'total': len(bl), 'aceitos': sum(bool(b.get('aceito')) for b in bl),
                                          'revisar': sum(b['status'] == 'revisar' and not b.get('aceito') for b in bl),
                                          'juiz': sum(b['status'] == 'juiz' and not b.get('aceito') for b in bl)})
        st['rascunho'] = _conta_rascunho[livro][1]
    if st.get('trabalho'):
        t = fila.resumo(st['trabalho'])
        if t:
            st['fila'] = {k: t[k] for k in ('fase', 'estado', 'progresso', 'total', 'feito', 'segundos', 'conta', 'a', 'b', 'tarefa')}      # a e b: os nomes nas placas do tribunal
    return st


def _salva(p, st):
    st['atualizado'] = time.time()
    _grava(p / 'revisao/dados/pipeline.json', {k: v for k, v in st.items() if k not in ('rodando_agora', 'fila', 'impedimento', 'rascunho', 'ao_vivo')})


def _pdf(p):
    return next(iter(sorted((p / 'fonte').glob('*.pdf'))), None)


# formatos com texto digital estruturado: extensão -> leitor do Pandoc. MOBI/AZW são desempacotados antes (pacote opcional "mobi").
DIGITAIS = {'.epub': 'epub', '.docx': 'docx', '.odt': 'odt', '.rtf': 'rtf', '.fb2': 'fb2', '.html': 'html', '.htm': 'html',
            '.md': 'markdown', '.txt': 'markdown', '.mobi': None, '.azw': None, '.azw3': None}


def _epub(p):
    """Arquivo de origem com texto digital (EPUB, DOCX, ODT, RTF, FB2, HTML, TXT, MOBI, AZW3), se houver."""
    return next((f for f in sorted((p / 'fonte').iterdir()) if f.suffix.lower() in DIGITAIS), None)


FORMATO_EPUB = 'markdown-smart-raw_html-native_divs-native_spans-fenced_divs-bracketed_spans-header_attributes-link_attributes-raw_attribute'


def _epub_para_md(p):
    # Pandoc converte o EPUB em Markdown limpo (um parágrafo por linha) e extrai as imagens para texto/img/
    arq, tmp, preparado, esperado = _epub(p), None, None, 0
    try:
        if DIGITAIS[arq.suffix.lower()] is None:          # Kindle: desempacota para EPUB ou HTML
            try:
                import mobi
            except ImportError:
                raise RuntimeError('para ler MOBI/AZW3 falta o componente opcional "mobi" (pip install mobi)')
            tmp, saida = mobi.extract(str(arq))
            arq = Path(saida)
            if arq.suffix.lower() in ('.html', '.htm'):   # MOBI antigo: os títulos são parágrafos em letra grande
                preparado = arq.with_name('estante-' + arq.name)      # ao lado do original, para as imagens continuarem no lugar
                preparado.write_text(epub.mobi_titulos(arq.read_text(encoding='utf-8', errors='replace')), encoding='utf-8')
        if arq.suffix.lower() == '.epub':                 # recupera subtítulos e notas que o EPUB só indica pelo estilo
            preparado, _ = epub.prepara(arq)
        if arq.suffix.lower() == '.fb2':                  # texto solto fora das seções seria ignorado pelo conversor
            dados, esperado = epub.fb2_arruma(arq.read_bytes())
            fd, nome_tmp = __import__('tempfile').mkstemp(suffix='.fb2')
            __import__('os').close(fd)                    # no Windows o arquivo fica preso enquanto este descritor estiver aberto
            preparado = Path(nome_tmp)
            preparado.write_bytes(dados)
        r = subprocess.run(['pandoc', str(preparado or arq), '-f', DIGITAIS[arq.suffix.lower()] or 'html', '-t', FORMATO_EPUB, '--wrap=none', '--extract-media=img'],
                           cwd=p / 'texto', capture_output=True, text=True, encoding='utf-8', errors='replace')
    finally:
        if tmp:
            __import__('shutil').rmtree(tmp, ignore_errors=True)
        if preparado:
            preparado.unlink(missing_ok=True)
    if r.returncode:
        raise RuntimeError(f'pandoc não conseguiu ler o arquivo {arq.suffix}: ' + r.stderr[-300:])
    if len(''.join(r.stdout.split())) < 0.7 * esperado:      # nada se perde em silêncio: melhor parar que seguir com um pedaço do livro
        raise RuntimeError(f'o conversor leu só {len(r.stdout) * 100 // max(1, esperado)}% do texto deste {arq.suffix[1:].upper()}; o arquivo foge do formato. '
                           'Converta-o para EPUB (o Calibre faz isso) e importe de novo.')
    return epub.notas_e_links(r.stdout.replace('\r', ''))


# ---------- 0 e 1 ----------
def _lingua(texto):
    t = ' ' + ' '.join(texto.lower().split()) + ' '
    return max(PALAVRAS, key=lambda k: sum(t.count(f' {w} ') for w in PALAVRAS[k].split()))


def camada(doc, paginas, idioma):
    """Qualidade do texto que vem dentro de um PDF, numa amostra de até 30 páginas espalhadas pela faixa:
    sobre_imagem  a maioria das páginas tem imagem (scan com texto por cima, feito por leitura automática)
    outra_lingua  parcela das páginas em idioma diferente do livro (edição bilíngue, por exemplo)
    desconhecidas parcela mediana de palavras que não existem no português atual, já descontada a grafia antiga (só para português)
    ruins         parcela das páginas em que essa taxa passa de 8%
    Medido em 07/10/2026 em 14 PDFs, 60 páginas de cada: nos scans de boa leitura, até 10% das páginas passam de 8%; nos de leitura ruim,
    de 40% para cima. A mediana sozinha não separa (um scan ruim deu 7,9%); por isso quem decide é a parcela de páginas ruins, com limite em 25%."""
    com = [i for i in paginas if len(doc[i].get_text().strip()) > 200]
    am = com[::max(1, len(com) // 30) | 1][:30]      # passo ímpar: em edição bilíngue de páginas alternadas, a amostra pega os dois idiomas
    if not am:
        return {}
    textos = [doc[i].get_text()[:3000] for i in am]
    da_lingua = [t for t in textos if _lingua(t) == idioma]
    r = {'sobre_imagem': sum(bool(doc[i].get_images()) for i in am) > len(am) / 2, 'outra_lingua': round(1 - len(da_lingua) / len(am), 2)}
    if idioma == 'pt' and da_lingua and duplo.regras.existe('casa') is not None:
        taxas = []
        for t in da_lingua:
            ws = [w for w in re.findall(r'[A-Za-zÀ-ÿ]+', duplo.regras.moderniza(t)[0]) if len(w) >= 4 and not w[:1].isupper()]
            taxas.append(sum(not duplo.regras.existe(w) for w in ws) / max(1, len(ws)))
        r['desconhecidas'] = round(sorted(taxas)[len(taxas) // 2], 3)
        r['ruins'] = round(sum(t > 0.08 for t in taxas) / len(taxas), 2)
    return r


def diagnostico(p, st):
    if _epub(p) and not _pdf(p):
        md = _epub_para_md(p)
        (p / 'ocr').mkdir(exist_ok=True)
        (p / 'ocr' / 'epub.md').write_text(md, encoding='utf-8', newline='\n')
        amostra = ' ' + md[:20000].lower() + ' '
        idioma = max(PALAVRAS, key=lambda k: sum(amostra.count(f' {w} ') for w in PALAVRAS[k].split()))
        estilo.colhe(p)          # capa, fontes e CSS do original -> <livro>/estilo/
        estilo.colhe_medidas(p)  # tamanho de página e fonte de um DOCX
        d = {'origem': 'epub', 'digital': True, 'caracteres': len(md), 'idioma_detectado': idioma}
        _grava(p / 'revisao/dados/diagnostico.json', d)
        st['mensagem'] = f'{_epub(p).suffix[1:].upper()} com {len(md) // 1000} mil caracteres de texto; idioma {idioma}'
        return d
    import pymupdf
    doc = pymupdf.open(str(_pdf(p)))
    chars = [len(pg.get_text().strip()) for pg in doc]
    ini, fim = st['config'].get('paginas') or (1, len(doc))
    faixa = chars[ini - 1:fim]
    mediana = sorted(faixa)[len(faixa) // 2] if faixa else 0
    digital = mediana > 200
    amostra = ' ' + ' '.join(doc[i].get_text()[:1500] for i in range(ini - 1, min(fim, ini + 5))).lower() + ' '
    idioma = max(PALAVRAS, key=lambda k: sum(amostra.count(f' {w} ') for w in PALAVRAS[k].split())) if digital else st['config'].get('idioma', '?')
    d = {'paginas': len(doc), 'faixa': [ini, fim], 'digital': digital, 'mediana_caracteres': mediana, 'idioma_detectado': idioma, 'caracteres_por_pagina': chars}
    st.pop('pergunta', None); st.pop('aviso', None)
    if digital:
        d['camada'] = c = camada(doc, range(ini - 1, min(fim, len(doc))), idioma)
        if c.get('outra_lingua', 0) >= 0.25:
            st['aviso'] = (f"{round(c['outra_lingua'] * 100)}% das páginas da amostra estão em outro idioma (edição bilíngue?). "
                           'O app trata o livro como um idioma só: confira esses trechos na Revisão.')
        escolha = st['config'].get('ler_por_imagem')
        if escolha is None and c.get('sobre_imagem') and c.get('ruins', 0) >= 0.25:
            # a decisão é do usuário: o texto do arquivo é rápido e imperfeito; reler pelas imagens leva uns 30 s por página
            st['pergunta'] = 'camada'
            st['mensagem'] = (f"Este PDF é um scan com texto por cima, e em {round(c['ruins'] * 100)}% das páginas da amostra esse texto tem muitas palavras "
                              'que não existem (leitura automática ruim). Escolha: usar esse texto assim mesmo ou reler as páginas pelas imagens.')
            _grava(p / 'revisao/dados/diagnostico.json', d)
            return False
        if escolha:
            d['digital'] = digital = False      # o usuário mandou reler: o livro segue como scan
    _grava(p / 'revisao/dados/diagnostico.json', d)
    if digital:
        estilo.colhe_medidas(p)      # tamanho da página e fonte do texto (pelo nome)
    st['mensagem'] = f"{len(doc)} páginas; {'texto digital' if digital else 'scan (precisa de leitura por imagem)'}; idioma {idioma}"
    return d


def inventario(p, st):
    d = _le(p / 'revisao/dados/diagnostico.json')
    if d.get('origem') == 'epub':
        return
    with (p / 'revisao' / 'inventario.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['pagina_pdf', 'caracteres_de_texto_digital', 'tipo'])
        for i, c in enumerate(d['caracteres_por_pagina'], 1):
            w.writerow([i, c, 'digital' if c > 200 else ('vazia ou imagem' if c < 20 else 'pouco texto')])


# ---------- 2 ----------
def _concordancia(a, b):
    return SequenceMatcher(None, re.findall(r'\w+', a.lower()), re.findall(r'\w+', b.lower()), autojunk=False).ratio()


def _imagens_da_pagina(p, pg, n, capa=False):
    """Imagens de uma página de PDF digital, como linhas de Markdown na posição em que aparecem: [(y, x, '![](img/…)')].
    Página tomada por uma imagem é guardada inteira (com o que estiver escrito por cima). A primeira, se for só imagem, vira a capa."""
    area = pg.rect.width * pg.rect.height
    out = []
    for k, b in enumerate(pg.get_text('dict')['blocks']):
        if b['type'] != 1:
            continue
        x0, y0, x1, y1 = b['bbox']
        fracao = max(0, min(x1, pg.rect.x1) - max(x0, pg.rect.x0)) * max(0, min(y1, pg.rect.y1) - max(y0, pg.rect.y0)) / area
        if fracao < 0.02:                       # enfeite, linha, ícone
            continue
        inteira = fracao >= 0.7
        figura = pg.get_pixmap(dpi=150, clip=None if inteira else pymupdf_rect(b['bbox'])).tobytes('jpeg', jpg_quality=88)
        if inteira and capa and len(pg.get_text().strip()) < 20:
            (p / 'estilo').mkdir(exist_ok=True)
            (p / 'estilo' / 'capa.jpg').write_bytes(figura)
            _grava(p / 'estilo' / 'estilo.json', {**estilo.le(p), 'origem': _pdf(p).name, 'capa': 'capa.jpg'})
            return []
        (p / 'texto' / 'img').mkdir(parents=True, exist_ok=True)
        nome = f'p{n:03d}-{k}.jpg'
        (p / 'texto' / 'img' / nome).write_bytes(figura)
        out.append((round(y0), x0, f'![](img/{nome})'))
        if inteira:
            break                               # a página inteira já foi guardada como uma imagem só
    return out


def pymupdf_rect(bbox):
    import pymupdf
    return pymupdf.Rect(bbox)


ENFASE = '\x02'      # marca, dentro do texto extraído do PDF, de que o bloco traz itálico ou negrito já em Markdown


def _com_enfase(linhas):
    """Texto de um bloco de PDF com o itálico e o negrito do original em Markdown (*…*, **…**). O resto do texto é escapado, para que um
    asterisco do autor não vire ênfase. O bloco sai marcado (ENFASE no começo) e estrutura() o trata como Markdown."""
    from revisao import esc
    pedacos = []          # [estilo, texto] em sequência, com '\n' entre as linhas
    for k, l in enumerate(linhas):
        for sp in l['spans']:
            est = ('**' if sp['flags'] & 16 else '') + ('*' if sp['flags'] & 2 else '')
            if pedacos and pedacos[-1][0] == est:
                pedacos[-1][1] += sp['text']
            else:
                pedacos.append([est, sp['text']])
        if k < len(linhas) - 1:
            pedacos[-1][1] += '\n'
    saida = ''
    for est, t in pedacos:
        miolo = t.strip()
        if est and miolo:      # a marca fica colada ao texto: espaço e quebra de linha ficam de fora
            saida += t[:len(t) - len(t.lstrip())] + est + esc(miolo) + est[::-1] + t[len(t.rstrip()):]
        else:
            saida += esc(t)
    return ENFASE + saida.strip()


def extracao(p, st, parar):
    d = _le(p / 'revisao/dados/diagnostico.json')
    if d.get('origem') == 'epub':
        return True                       # o texto já saiu do EPUB no diagnóstico (ocr/epub.md)
    import pymupdf
    doc = pymupdf.open(str(_pdf(p)))
    ini, fim = d['faixa']
    pags = list(range(ini, fim + 1))
    dest = p / 'ocr' / 'paginas'
    if d['digital']:
        # tamanho de letra do corpo do livro: o mais usado, contando caracteres
        tamanhos, por_pagina = {}, {}
        for n in pags:
            por_pagina[n] = doc[n - 1].get_text('dict')['blocks']
            for b in por_pagina[n]:
                for l in b.get('lines', []):
                    for sp in l['spans']:
                        tamanhos[round(sp['size'])] = tamanhos.get(round(sp['size']), 0) + len(sp['text'].strip())
        corpo = max(tamanhos, key=tamanhos.get) if tamanhos else 0
        for n in pags:
            pg = doc[n - 1]
            partes, titulos, ult_titulo = [], [], None
            for b in por_pagina[n]:
                if b['type'] != 0:
                    continue
                spans = [sp for l in b['lines'] for sp in l['spans'] if sp['text'].strip()]
                # itálico (2) ou negrito (16) em parte do bloco: vai como Markdown; bloco todo em negrito é título e fica como está
                texto = _com_enfase(b['lines']) if any(sp['flags'] & 18 for sp in spans) and not all(sp['flags'] & 16 for sp in spans) else \
                    '\n'.join(''.join(sp['text'] for sp in l['spans']) for l in b['lines']).strip()
                if not texto or not spans:
                    continue
                maior = max(spans, key=lambda sp: len(sp['text']))['size']
                # título pela tipografia: letra bem maior que a do corpo, ou bloco curto todo em negrito
                eh_tit = len(texto) < 200 and (maior >= 1.18 * corpo or (len(texto) < 120 and all(sp['flags'] & 16 for sp in spans)))
                ant = ult_titulo
                # título de várias linhas que o PDF guarda como blocos separados ("ASLEEP AT A STOPLIGHT, AWOKEN" / "ONLY BY HORN"): mesma letra,
                # linha logo abaixo e o anterior sem ponto final -> é um título só (visto num livro inteiro: iam pela metade para o tradutor)
                if (eh_tit and ant and abs(ant['tam'] - maior) < 0.6 and -0.3 * maior <= b['bbox'][1] - ant['y1'] < 0.9 * maior and not FIM_FRASE.search(ant['texto'])
                        and ENFASE not in texto and ENFASE not in ant['texto']):
                    partes[ant['k']] = (partes[ant['k']][0], partes[ant['k']][1], ant['texto'] + ' ' + texto)
                    titulos[-1] = ant['texto'] + ' ' + texto
                    ant.update(texto=ant['texto'] + ' ' + texto, y1=b['bbox'][3])
                    continue
                partes.append((round(b['bbox'][1]), b['bbox'][0], texto))
                ult_titulo = {'k': len(partes) - 1, 'texto': texto, 'tam': maior, 'y1': b['bbox'][3]} if eh_tit else None
                if eh_tit:
                    titulos.append(texto)
            imagens = _imagens_da_pagina(p, pg, n, capa=(n == pags[0]))
            j = {'pagina': n, 'origem': 'digital', 'texto': '\n\n'.join(t for _, _, t in sorted(partes + imagens)), 'titulos': titulos}
            if any(pg.rect.width * pg.rect.height * 0.7 <= (b['bbox'][2] - b['bbox'][0]) * (b['bbox'][3] - b['bbox'][1]) for b in por_pagina[n] if b['type'] == 1):
                # página tomada por uma imagem: o que está escrito por cima já foi guardado dentro da imagem; o texto solto vai para conferência
                j.update(titulos=[], sobre_imagem=True)
            _grava(dest / f'{n:04d}.json', j)
        return True
    la, lb = duplo.escolhe('ler_pagina')
    a, b = st['config'].get('leitor') or la, st['config'].get('b') or lb
    total = 2 * len(pags); feito = 0
    for chave, modelo in (('a', a), ('b', b)):            # por modelo: todas as páginas com A, depois todas com B
        for n in pags:
            if parar():
                return False
            f = dest / f'{n:04d}.json'
            j = _le(f, {'pagina': n, 'origem': 'scan'})
            if chave not in j:
                img = base64.b64encode(doc[n - 1].get_pixmap(dpi=130).tobytes('jpeg', jpg_quality=80)).decode()
                t0 = time.time()
                j[chave] = duplo.chat(modelo, [{'role': 'user', 'content': duplo.pedido_leitura(modelo)}], imagens=[img], num_predict=2500, corta_repeticao=True,
                                      vivo={'papel': 'lendo', 'pagina': n})
                j[f'modelo_{chave}'] = modelo; j[f'segundos_{chave}'] = round(time.time() - t0, 1)
                if 'a' in j and 'b' in j:
                    j['concordancia'] = round(_concordancia(j['a'], j['b']), 3)
                    # com o GLM-OCR de segundo leitor: as palavras dele (lê melhor) com a grafia do primeiro (ele moderniza por conta própria).
                    # Medido em 7 páginas de um scan antigo: 0,80 do texto aprovado contra 0,73 do primeiro leitor sozinho, e menos sobra (0,18 contra 0,29)
                    j['texto'] = duplo.combina(j['b'], j['a']) if 'glm-ocr' in j.get('modelo_b', '') else j['a']
                    j['estado'] = 'ok' if j['concordancia'] >= 0.85 and not duplo.eh_recusa(j['a']) else 'revisar'
                _grava(f, j)
            feito += 1
            st['progresso'] = round(feito / total, 3); st['mensagem'] = f'lendo página {n} com o modelo {chave.upper()} ({feito}/{total})'
            _salva(p, st)
    return True


# ---------- 3 ----------
def _letras(s):
    return re.sub(r'[^a-z]', '', ''.join(c for c in unicodedata.normalize('NFD', s.lower()) if unicodedata.category(c) != 'Mn'))


VOCAB = {}      # palavra -> vezes no livro em processamento (estrutura() preenche): decide se um hífen de fim de linha é da palavra


def _junta_linhas(linhas):
    """Une as linhas de um parágrafo, desfazendo a hifenização de fim de linha (mantém o hífen antes de pronome/terminação).
    Palavra composta partida no hífen ("government-/sanctioned") fica com o hífen: as duas metades existem sozinhas no livro e a
    palavra emendada não. Sem o vocabulário do livro (VOCAB vazio), emenda sempre, como antes."""
    out = ''
    for l in linhas:
        l = l.strip()
        if not l:
            continue
        if out.endswith('-') and l[:1].islower():
            prox = re.match(r'\w+', l)
            antes = re.search(r'(\w+)-$', out)
            if prox and prox[0].lower() in CLITICOS:
                out += l                      # obriga-/se  -> obriga-se
            elif (prox and antes and (antes[1] + prox[0]).lower() not in VOCAB
                  and VOCAB.get(antes[1].lower(), 0) >= 2 and VOCAB.get(prox[0].lower(), 0) >= 2):
                out += l                      # government-/sanctioned -> government-sanctioned
            else:
                out = out[:-1] + l            # reconheci-/mento -> reconhecimento
        else:
            out += (' ' if out else '') + l
    return out


def _eh_titulo(t, linha_curta=True):
    """linha_curta=False desliga o palpite mais fraco (linha curta sem ponto), para livros em que a tipografia já diz o que é título."""
    if len(t) > 90 or len(t) < 3 or t.endswith((',', ';')) or re.search(r'[.]\s*$', t) and not re.match(r'^[IVXLC]+\.', t):
        return False
    letras = [c for c in t if c.isalpha()]
    if not letras:
        return False
    maiusc = sum(c.isupper() for c in letras) / len(letras)
    if linha_curta and len(t) < 60 and not re.search(r'[.!?:;,]\s*$', t) and t[:1].isupper() and not re.match(r'^(\d{1,3}[.)]|[a-z]\))', t):
        return True                              # linha curta, isolada, sem pontuação final: título ou subtítulo
    return maiusc > 0.75 or bool(re.match(r'^(cap[ií]tulo|chapter|kapitel|parte|part|teil|livro|book|pr[eó]logo|pref[aá]cio|introdu[cç][aã]o|introduction|[IVXLC]+\.)\b', t, re.I))


LISTA = re.compile(r'^(\s*(?:[-*+]|\d+\.)\s+)(.*)', re.S)


def niveis_sem_buraco(blocos):
    """Títulos que pulam níveis no original (# e depois ###) viram níveis seguidos (# e ##), para o sumário e os capítulos saírem certos."""
    usados = sorted({b['nivel'] for b in blocos if b['kind'] == 'heading'})
    for b in blocos:
        if b['kind'] == 'heading':
            b['nivel'] = usados.index(b['nivel']) + 1


def estrutura_epub(p, st):
    """ocr/epub.md -> blocos. O texto de cada bloco é Markdown (itálico, links); o prefixo ('> ', '- ', nível do título) fica à parte."""
    blocos, sec = [], 0
    texto = re.sub(r'\n>[ \t]*(?=\n)', '\n', (p / 'ocr' / 'epub.md').read_text(encoding='utf-8'))     # linha só com '>' separa parágrafos da citação
    for trecho in re.split(r'\n\s*\n', texto):
        linhas = [l for l in trecho.split('\n') if l.strip()]
        if not linhas:
            continue
        b = {'kind': 'paragraph', 'md': True, 'prefixo': ''}
        t = linhas[0].strip()
        m = re.match(r'^(#{1,6})\s+(.*)', t)
        if m:
            sec += 1
            b.update(kind='heading', nivel=len(m[1]), text=m[2])
        elif t.startswith('!['):
            b.update(kind='image', text=t)
        else:
            if all(l.lstrip().startswith('>') for l in linhas):
                b['prefixo'] = '> '; linhas = [re.sub(r'^\s*>\s?', '', l) for l in linhas]
            lm = LISTA.match(linhas[0]) or re.match(r'^(\[\^[^\]]+\]:\s+)(.*)', linhas[0], re.S)      # item de lista ou texto de nota de rodapé
            if lm and len(linhas) == 1:
                b['prefixo'] += lm[1]; linhas = [lm[2]]
            # quebra de linha do original (linha terminada em "\") vira <br>, que o filtro livro.lua devolve como quebra
            linhas = [l.strip()[:-1].rstrip() + ' <br>' if l.rstrip().endswith('\\') else l.strip() for l in linhas]
            if any(not l.endswith('<br>') for l in linhas[:-1]):
                b['quebras'] = True          # ponytail: tabela ou lista de várias linhas vira uma linha só; o bloco vai para revisão manual
            b['text'] = ' '.join(linhas)
        b['source_pages'] = [max(1, sec)]
        blocos.append(b)
    niveis_sem_buraco(blocos)
    for k, b in enumerate(blocos):
        b['id'] = f'b{k:05d}'
    md = (p / 'texto' / 'livro.md').read_text(encoding='utf-8')
    tit = re.search(r'^title:\s*"(.*)"', md, re.M); aut = re.search(r'^author:\s*"(.*)"', md, re.M)
    _grava(p / 'fonte' / 'dados' / 'source.json', {'title': tit[1] if tit else p.name, 'author': aut[1] if aut else '', 'origem': 'epub', 'blocks': blocos, 'notes': [],
                                                   'gerado_por': 'pipeline (automático; conferir)'})
    n_t = sum(b['kind'] == 'heading' for b in blocos)
    st['mensagem'] = f'{len(blocos) - n_t} blocos de texto e {n_t} títulos em {sec} seções'
    return blocos


def revisao_esc(t):
    from revisao import esc, literal
    return literal(esc(t))


def estrutura(p, st):
    d = _le(p / 'revisao/dados/diagnostico.json')
    if d.get('origem') == 'epub':
        return estrutura_epub(p, st)
    ini, fim = d['faixa']
    pags, por_fonte = [], set()        # por_fonte: títulos que o PDF digital distingue pela letra (maior ou em negrito)
    for n in range(ini, fim + 1):
        j = _le(p / 'ocr' / 'paginas' / f'{n:04d}.json')
        if j and j.get('texto'):
            pags.append((n, j['texto'], 'sobre_imagem' if j.get('sobre_imagem') else j.get('estado', 'ok')))
            por_fonte |= {_letras(x) for x in j.get('titulos', [])}
    # cabeçalhos corridos: linha curta entre as duas primeiras ou a última da página, repetida em várias páginas (ignorando o número da página)
    def chave(l):
        return _letras(re.sub(r'\d+', '', l))
    cont = {}
    for _, t, _ in pags:
        ls = [l.strip() for l in t.split('\n') if l.strip()]
        for l in {chave(x) for x in ls[:2] + ls[-1:] if len(x) < 60 and not x.startswith('![')}:
            if l:
                cont[l] = cont.get(l, 0) + 1
    repetidas = {l for l, c in cont.items() if c >= max(2, 0.2 * len(pags))}
    marcador = re.compile(r'^(\d{1,3}[.)]|[a-z]\)|[IVXLC]{1,6}\.\s*[—-]?)\s+\S')
    VOCAB.clear()
    for _, t, _ in pags:
        for w in re.findall(r'[^\W\d_]+', t.lower()):
            VOCAB[w] = VOCAB.get(w, 0) + 1
    blocos = []
    # Página tomada por uma imagem, com texto por cima. Num livro de texto são poucas (capa, colagem, ilustração): a imagem já entra no livro
    # e o texto solto, lido de dentro da figura, só gerava bloco quebrado pedindo atenção (38 num livro de 827). Aí o texto fica de fora.
    # Se são muitas (scan com texto por cima), o texto É o livro e continua entrando.
    poucas_imagens = sum(e == 'sobre_imagem' for _, _, e in pags) <= 0.2 * len(pags)
    for n, texto, est in pags:
        if est == 'sobre_imagem' and poucas_imagens:
            texto = '\n\n'.join(t for t in re.split(r'\n\s*\n', texto) if re.fullmatch(r'!\[\]\(img/[\w.-]+\)', t.strip()))
        paras = []
        for bruto in re.split(r'\n\s*\n', texto):
            atual = []
            for l in bruto.split('\n'):
                if not l.strip() or SO_NUMERO.match(l.strip()) or (len(l.strip()) < 60 and chave(l) in repetidas and not l.strip().startswith('![')):
                    continue
                if atual and marcador.match(l.strip()):       # item de lista ("1. …", "a) …", "I. — …") abre parágrafo novo
                    paras.append(atual); atual = []
                atual.append(l)
            if atual:
                paras.append(atual)
        primeiro_da_pagina = True
        for linhas in paras:
            t = _junta_linhas(linhas)
            enfase, t = ENFASE in t, t.replace(ENFASE, '')      # bloco de PDF que traz itálico ou negrito, já em Markdown
            t = re.sub(r'¬\s*', '', t)                          # marca de quebra opcional que alguns PDFs deixam no meio da palavra
            if not t:
                continue
            # título em caixa-alta colado no fim do parágrafo ("…for life.FRIDAY"): vira um bloco à parte
            colado = re.search(r'(?<=[a-zà-ÿ][.!?])([A-ZÀ-Ý][A-ZÀ-Ý\' ]{3,40})$', t)
            if colado:
                paras_extra = colado[1]; t = t[:colado.start()]
            else:
                paras_extra = None
            if re.fullmatch(r'!\[\]\(img/[\w.-]+\)', t):          # imagem do PDF, na posição em que estava
                blocos.append({'kind': 'image', 'md': True, 'pagina_pdf': True, 'prefixo': '', 'text': t, 'source_pages': [n]})
                primeiro_da_pagina = False
                continue
            # se o livro distingue títulos pela letra, vale a tipografia (mais os sinais fortes: caixa-alta, "Capítulo…"); senão, o palpite por linha curta
            titulo = (_letras(t) in por_fonte or _eh_titulo(t, linha_curta=False)) if len(por_fonte) >= 3 else _eh_titulo(t)
            titulo = titulo and est != 'sobre_imagem'           # texto por cima de uma imagem de página inteira não é título
            ant = blocos[-1] if blocos else None
            continua = ant and ant['kind'] == 'paragraph' and not titulo and not FIM_FRASE.search(ant['text'])
            # o parágrafo continua o anterior: na virada de página, ou na mesma página quando o PDF o partiu em dois pedaços
            # (visto num livro inteiro: 35 de 819 blocos começavam em minúscula, todos no meio da página, e iam pela metade para o tradutor)
            if continua and ((primeiro_da_pagina and ant['source_pages'][-1] == n - 1)
                             or (ant['source_pages'][-1] == n and t[:1].islower() and est != 'sobre_imagem' and not ant.get('sobre_imagem'))):
                # parágrafo que continua da página anterior (se só um dos pedaços é Markdown, o outro é escapado para poder juntar)
                if enfase and not ant.get('md'):
                    ant.update(text=revisao_esc(ant['text']), md=True, pagina_pdf=True, prefixo='')
                elif ant.get('md') and not enfase:
                    t = revisao_esc(t)
                if ant['text'].endswith('-') and t[:1].islower():
                    ant['text'] = _junta_linhas([ant['text'], t])
                else:
                    ant['text'] += ' ' + t
                if ant['source_pages'][-1] != n:
                    ant['source_pages'].append(n)
            else:
                blocos.append({'kind': 'heading' if titulo else 'paragraph', 'text': t, 'source_pages': [n]})
                if enfase and not titulo:
                    blocos[-1].update(md=True, pagina_pdf=True, prefixo='', text=__import__('revisao').literal(t))
                elif enfase:                 # título: sem ênfase dentro (o título já sai destacado)
                    blocos[-1]['text'] = re.sub(r'(?<!\\)\*+|\\(.)', lambda m: m[1] or '', t)
                if est == 'revisar':
                    blocos[-1]['pagina_duvidosa'] = True
                elif est == 'sobre_imagem':
                    blocos[-1]['sobre_imagem'] = True
            if paras_extra:
                blocos.append({'kind': 'heading', 'text': paras_extra, 'source_pages': [n]})
            primeiro_da_pagina = False
    for k, b in enumerate(blocos):
        b['id'] = f'b{k:05d}'
        m = re.match(r'^(\d{1,4})\.\s', b['text'])
        if b['kind'] == 'paragraph' and m:
            b['number'] = int(m[1])
    md = (p / 'texto' / 'livro.md').read_text(encoding='utf-8') if (p / 'texto' / 'livro.md').exists() else ''
    tit = re.search(r'^title:\s*"(.*)"', md, re.M); aut = re.search(r'^author:\s*"(.*)"', md, re.M)
    _grava(p / 'fonte' / 'dados' / 'source.json', {'title': tit[1] if tit else p.name, 'author': aut[1] if aut else '', 'frontmatter': '', 'blocks': blocos, 'notes': [],
                                                   'gerado_por': 'pipeline (automático; conferir)'})
    n_par = sum(b['kind'] == 'paragraph' for b in blocos)
    st['mensagem'] = f'{n_par} parágrafos e {len(blocos) - n_par} títulos em {len(pags)} páginas'
    return blocos


# ---------- 4 e 5 ----------
def _glossario(p):
    f = p / 'revisao' / 'glossario.csv'
    if not f.exists():
        return ''
    linhas = [r for r in csv.DictReader(f.open(encoding='utf-8'), delimiter=';') if r.get('fonte') and r.get('usar')]
    return ('Termos já decididos (use sempre):\n' + '\n'.join(f"- {r['fonte']} = {r['usar'].split('|')[0]}" for r in linhas)) if linhas else ''


LINK = re.compile(r'\[([^\]\[]*)\]\(((?:[^()\s]|\([^()\s]*\))+)\)')      # o endereço pode ter um par de parênteses dentro
NOTA = re.compile(r'\[\^[^\]]+\]')


def mascara(t):
    """Tira do caminho o que o modelo não deve tocar: [texto](endereço) -> <a1>texto</a1>; [^nota] -> <n2/>.
    O texto do link continua à vista para ser traduzido; o endereço e a nota voltam, iguais, em desmascara().
    Devolve (texto, peças). A checagem de que as marcas voltaram todas fica em duplo.checagens."""
    pecas = []

    def link(m):
        pecas.append(m[2])
        return f'<a{len(pecas)}>{m[1]}</a{len(pecas)}>'

    def nota(m):
        pecas.append(m[0])
        return f'<n{len(pecas)}/>'

    def enfase(letra, sinal):
        def f(m):
            pecas.append(sinal)
            return f'<{letra}{len(pecas)}>{m[1]}</{letra}{len(pecas)}>'
        return f
    t = NOTA.sub(nota, LINK.sub(link, t))      # links e notas primeiro: a numeração deles é a mesma de antes de existir a marca de itálico
    # bloco inteiro em itálico (citação): o sinal sai e volta em volta do resultado, sem depender do modelo
    if re.fullmatch(r'\*[^*]+\*', t.strip(), re.S):
        pecas.append(TUDO)
        return t.strip()[1:-1], pecas
    # itálico e negrito no meio do texto viram marcas, como os links: no piloto o modelo perdeu ou criou asteriscos em 23 blocos e quase nunca perdeu marca
    t = NEGRITO.sub(enfase('b', '**'), t)
    return ITALICO.sub(enfase('i', '*'), t), pecas


TUDO = '*bloco inteiro em itálico*'
NEGRITO = re.compile(r'\*\*(?!\s)([^*\n]+?)(?<!\s)\*\*')
ITALICO = re.compile(r'(?<!\*)\*(?![\s*])([^*\n]+?)(?<![\s*])\*(?!\*)')


def desmascara(t, pecas):
    for k, peca in enumerate(pecas, 1):
        if peca == TUDO:
            t = '*' + t.strip().strip('*').strip() + '*'
        elif peca in ('*', '**'):
            t = re.sub(rf'<[ib]{k}>(.*?)</[ib]{k}>', lambda m: f'{peca}{m[1]}{peca}', t, flags=re.S)
        else:
            t = re.sub(rf'<a{k}>(.*?)</a{k}>', lambda m: f'[{m[1]}]({peca})', t, flags=re.S)
            t = t.replace(f'<n{k}/>', peca)
    return t


def tem_letras(t):
    """Bloco sem nenhuma letra ("* * *", "—", só números) não tem o que traduzir: não vai ao modelo e sai como está."""
    return bool(re.search(r'[A-Za-zÀ-ÿ]', duplo.MARCA.sub('', t)))


def transformacao(p, st, parar):
    tarefa = st['config'].get('tarefa', 'nenhuma')
    if tarefa == 'nenhuma':
        return True
    if not st.get('trabalho'):
        src = _le(p / 'fonte' / 'dados' / 'source.json')
        # o que vai ao modelo: links e notas viram marcas; português antigo já sai com a grafia atualizada por léxico e regras
        prepara = lambda b: duplo.regras.moderniza(b['text'])[0] if tarefa == 'atualizar_pt' else mascara(b['text'])[0] if b.get('md') else b['text']   # noqa: E731
        itens = [{'i': k, 'raw': b['id'], 'prefixo': '', 'fonte': prepara(b)}
                 for k, b in enumerate(src['blocks']) if b['kind'] in ('paragraph', 'heading') and tem_letras(b['text'])]
        a, b = duplo.escolhe(tarefa)
        if st['config'].get('rapido'):
            if tarefa != 'traduzir' or not duplo.classico.disponivel():
                raise RuntimeError('o rascunho rápido só traduz do inglês e precisa do motor clássico instalado (python app/classico.py --preparar)')
            st['config']['a'] = duplo.classico.NOME
        st['trabalho'] = fila.criar(p.name, tarefa, itens, st['config'].get('a') or a, st['config'].get('b') or b, contexto=_glossario(p))
        _salva(p, st)
    parcial = 0
    while True:
        t = fila.resumo(st['trabalho'])
        if time.time() - parcial > 60:      # de minuto em minuto, o que já foi escrito aparece na Revisão para leitura (ainda sem poder aceitar)
            parcial = time.time(); rascunho(p, st)
        st['progresso'] = t['progresso']; st['mensagem'] = f"{tarefa}: fase {t['fase']} ({round(t['progresso'] * 100)}%)"
        _salva(p, st)
        if t['estado'] == 'concluido':
            return True
        if t['estado'] in ('cancelado', 'pausado') or parar():
            if parar():
                fila.pausar(st['trabalho'], True)
            elif t.get('erro'):         # o modelo falhou (fora do ar, não instalado…): diz o motivo na tela
                st['mensagem'] = 'parou porque o modelo não respondeu: ' + t['erro']
                _salva(p, st)
            return False
        time.sleep(3)


def rascunho(p, st):
    src = _le(p / 'fonte' / 'dados' / 'source.json')
    por_id = {}
    if st.get('trabalho'):
        for it in fila.estado(st['trabalho'])['itens']:
            por_id[it['raw']] = it
    antigo = {b['id']: b for b in (_le(p / 'revisao/dados/rascunho.json', {}) or {}).get('blocos', [])}
    blocos = []
    capa = estilo.le(p).get('capa_origem')
    for b in src['blocks']:
        if capa and b['kind'] == 'image' and capa in b['text']:
            continue                    # a capa entra como capa do livro (estilo/), não como imagem no meio do texto
        it = por_id.get(b['id'])
        novo = {'id': b['id'], 'tipo': {'heading': 'titulo', 'image': 'imagem'}.get(b['kind'], 'paragrafo'), 'paginas': b['source_pages'], 'fonte': b['text'],
                'resultado': (it['resultado'] if it else b['text']),
                # bloco que os modelos ainda não terminaram: dá para ler, não dá para aceitar
                'status': (it['estado'] if it['estado'] in ('aprovado', 'revisar') else 'andamento') if it else 'aprovado',
                'problemas': (it['problemas'] if it else []), 'conversa': (it['conversa'] if it else [])}
        if it and any(c.get('ganhou') == 'auditor' for c in novo['conversa']):
            # o juiz reescreveu um trecho da tradução: não entra no "aceitar todos"; o usuário vê o antes e o depois e decide
            novo['status'] = 'juiz'
            novo['antes_do_juiz'] = next((c['disse'].removeprefix('Revisão: ') for c in reversed(novo['conversa']) if c.get('papel') != 'juiz' and c['quem'] == novo['conversa'][0]['quem']), '')
        if it and b.get('md'):
            novo['resultado'] = desmascara(it['resultado'], mascara(b['text'])[1])       # endereços dos links e notas voltam como estavam
            if novo.get('antes_do_juiz'):
                novo['antes_do_juiz'] = desmascara(novo['antes_do_juiz'], mascara(b['text'])[1])
        if it and st['config'].get('tarefa') == 'atualizar_pt':
            novo['trocas'] = list(dict.fromkeys(f'{a} → {n}' for a, n in duplo.regras.moderniza(b['text'])[1]))      # grafias trocadas por regra, para conferir
            if any('além da grafia' in pr or 'tamanho fora' in pr for pr in novo['problemas']):
                # medido em app/regua_antigo.py: às vezes o modelo troca ou corta palavras; aí vale a versão só com léxico e regras
                novo['resultado'] = it['fonte']
                novo['problemas'] = novo['problemas'] + ['o modelo mexeu no texto além da grafia; ficou a versão feita só por léxico e regras (confira os acentos)']
        if b.get('pagina_duvidosa'):
            novo['status'] = 'revisar'; novo['problemas'] = novo['problemas'] + ['a página de origem teve leituras divergentes entre os dois modelos']
        for k in ('md', 'prefixo', 'nivel', 'pagina_pdf'):
            if k in b:
                novo[k] = b[k]
        if b.get('sobre_imagem'):
            novo['status'] = 'revisar'; novo['problemas'] = novo['problemas'] + ['texto que está por cima de uma imagem de página inteira (a imagem foi guardada com ele): confira se deve ficar também como texto']
        if b.get('quebras') and (not it or any('<br>' in pr for pr in novo['problemas'])):      # traduzido com todas as quebras no lugar: não precisa de conferência
            novo['status'] = 'revisar'; novo['problemas'] = novo['problemas'] + ['o bloco tinha quebras de linha no original (verso ou tabela?); conferir']
        if novo['status'] == 'andamento':
            novo['problemas'] = []
        if b['kind'] == 'heading' and not it and st['config'].get('tarefa', 'nenhuma') != 'nenhuma':
            novo['status'] = 'revisar'; novo['problemas'] = ['título ainda no idioma/grafia da fonte']
        ant = antigo.get(b['id'], {})
        novo['aceito'] = bool(ant.get('aceito')) and ant.get('resultado') == novo['resultado']
        if novo['aceito'] and ant.get('aceito_em'):
            novo['aceito_em'] = ant['aceito_em']      # a data do aceite sobrevive a um reprocessamento que manteve o texto
            if ant.get('aceito_auto'):
                novo['aceito_auto'] = True
        if novo['aceito'] and ant.get('texto'):
            novo['texto'] = ant['texto']          # texto editado pelo usuário no aceite
        blocos.append(novo)
    _grava(p / 'revisao/dados/rascunho.json', {'livro': p.name, 'tarefa': st['config'].get('tarefa'), 'gerado': time.time(), 'blocos': blocos})
    n_rev, n_juiz = sum(b['status'] == 'revisar' for b in blocos), sum(b['status'] == 'juiz' for b in blocos)
    st['mensagem'] = (f'{len(blocos)} blocos no rascunho; {n_rev} para revisar, ' + (f'{n_juiz} corrigidos pelo juiz para conferir, ' if n_juiz else '')
                      + f'{len(blocos) - n_rev - n_juiz} aprovados pelos modelos')


# ---------- orquestração ----------
def _roda(livro):
    p = pasta(livro)
    st = _le(p / 'revisao/dados/pipeline.json')
    parar = lambda: livro in _pedidos   # noqa: E731
    try:
        for etapa in ETAPAS:
            if etapa in st['feitas']:
                continue
            st.update(etapa=etapa, estado='rodando', progresso=0); _salva(p, st)
            ok = True
            if etapa == 'diagnostico': ok = diagnostico(p, st) is not False
            elif etapa == 'inventario': inventario(p, st)
            elif etapa == 'extracao': ok = extracao(p, st, parar)
            elif etapa == 'estrutura': estrutura(p, st)
            elif etapa == 'transformacao': ok = transformacao(p, st, parar)
            elif etapa == 'rascunho': rascunho(p, st)
            if not ok:
                st['estado'] = 'pausado'; _pedidos.discard(livro); _salva(p, st)
                return
            st['feitas'].append(etapa); st['progresso'] = 1; _salva(p, st)
        try:      # o livro sai do rascunho inteiro: a Revisão não é passo obrigatório (ver revisao.gera_livro_md)
            import revisao
            st['livro_gerado'] = revisao.gera_livro_md(p)
        except Exception as ex:      # noqa: BLE001
            st['mensagem_livro'] = f'livro não montado do rascunho: {type(ex).__name__}: {ex}'
        import config      # opção global em Configurações > Processamento (padrão desligada)
        if config.le()['processo'].get('aceite_automatico'):      # aceita o que sobrou, com um commit por aceite (ver revisao.aceita_automatico)
            st.pop('mensagem_auto', None)
            try:
                import revisao
                res = revisao.aceita_automatico(livro)
                st['aceitos_automaticos'] = res
                if res['ficaram_de_fora']:
                    st['mensagem_auto'] = f"{res['ficaram_de_fora']} bloco(s) não terminaram o processamento e ficaram de fora do aceite automático (aceite-os à mão ou gere de novo)"
            except Exception as ex:      # noqa: BLE001  (o livro continua processado; o aceite pode ser feito à mão)
                st['mensagem_auto'] = f'aceite automático não rodou: {type(ex).__name__}: {ex}'
        st.update(estado='concluido', etapa='revisao'); _salva(p, st)
    except Exception as ex:      # noqa: BLE001
        st.update(estado='erro', mensagem=f'{type(ex).__name__}: {ex}'); _salva(p, st)


def iniciar(livro, config=None):
    """Começa (ou continua) o pipeline de um livro. config: tarefa, paginas [ini, fim], a, b, idioma."""
    p = pasta(livro)
    if not _pdf(p) and not _epub(p):
        raise ValueError('o livro não tem arquivo de origem em fonte/')
    if impedimento(p):
        raise ValueError(impedimento(p) + '; o processamento não vai sobrescrevê-lo')
    if livro in _threads and _threads[livro].is_alive():
        return estado(livro)
    st = _le(p / 'revisao/dados/pipeline.json', {'estado': 'novo', 'etapa': None, 'feitas': [], 'progresso': 0, 'mensagem': '', 'config': {}})
    if config:
        st['config'].update({k: v for k, v in config.items() if v is not None})
    _pedidos.discard(livro)
    if st.get('trabalho') and (fila.resumo(st['trabalho']) or {}).get('estado') == 'pausado':
        fila.pausar(st['trabalho'], False)
    st['estado'] = 'rodando'; _salva(p, st)
    t = threading.Thread(target=_roda, args=(livro,), daemon=True, name=f'pipeline-{livro}')
    _threads[livro] = t; t.start()
    return estado(livro)


def pausar(livro):
    p = pasta(livro)
    if livro in _threads and _threads[livro].is_alive():
        _pedidos.add(livro)                    # a thread vê o pedido no próximo passo e grava "pausado"
    else:
        st = _le(p / 'revisao/dados/pipeline.json')
        if st and st.get('estado') == 'rodando':
            st['estado'] = 'pausado'; _salva(p, st)
    return estado(livro)


def retomar_todos():
    """Ao subir o servidor: continua os pipelines que estavam rodando."""
    for p in (RAIZ / 'livros').iterdir():
        st = _le(p / 'revisao/dados/pipeline.json') if p.is_dir() else None
        if st and st.get('estado') == 'rodando':
            iniciar(p.name)


if __name__ == '__main__':      # autoteste: python app/pipeline.py
    t = 'Veja a [discussão](http://x.org/a_(b)?q=1) e a nota[^3]; depois *isto* e ![capa](img/c.png).'
    m, pecas = mascara(t)
    assert m == 'Veja a <a1>discussão</a1> e a nota<n3/>; depois <i4>isto</i4> e !<a2>capa</a2>.', m
    assert desmascara(m, pecas) == t
    assert desmascara(m.replace('discussão', 'discussion'), pecas) == t.replace('discussão', 'discussion')
    sem_nota, sem_italico = duplo.checagens(m, m.replace('<n3/>', ''), 'traduzir'), duplo.checagens(m, re.sub(r'</?i4>', '', m), 'traduzir')
    assert sem_nota == ['marcação diferente da fonte; faltam as marcas <n3/>'] and duplo.trava(sem_nota[0])           # nota perdida: nem o juiz libera
    assert len(sem_italico) == 1 and '<i4>' in sem_italico[0] and not duplo.trava(sem_italico[0])      # itálico: o juiz pode liberar
    cit, pc = mascara('*Uma citação inteira em itálico, com **negrito** e * solto.*')
    assert mascara('*Tudo em itálico.*') == ('Tudo em itálico.', [TUDO]) and desmascara('Tudo traduzido.', [TUDO]) == '*Tudo traduzido.*'
    assert mascara('a **forte** e *leve*; 2 * 3 e * * *')[0] == 'a <b1>forte</b1> e <i2>leve</i2>; 2 * 3 e * * *'
    assert desmascara(*mascara('a **forte** e *leve*')) == 'a **forte** e *leve*'
    VOCAB.update(government=3, sanctioned=2, exam=1, example=4)
    assert _junta_linhas(['the government-', 'sanctioned food']) == 'the government-sanctioned food' and _junta_linhas(['an exam-', 'ple of']) == 'an example of'
    VOCAB.clear()
    assert _junta_linhas(['reconheci-', 'mento']) == 'reconhecimento' and _junta_linhas(['obriga-', 'se a']) == 'obriga-se a'
    assert duplo.ajusta('Sem ênfase.', 'Sem *ênfase*.') == 'Sem ênfase.'
    assert duplo.ajusta('The Title of a Book', 'O Título de um Livro.') == 'O Título de um Livro'
    assert duplo.ajusta('It ends.', 'Termina.') == 'Termina.' and duplo.ajusta('Wait…', 'Espere...') == 'Espere...'
    print('ok')
