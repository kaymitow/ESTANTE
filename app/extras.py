"""Rotas extras do app: importar livro novo, editar glossário, colação com outra cópia."""
import csv, io, json, re, shutil, subprocess, sys, time, unicodedata
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable
COLS = ['fonte', 'usar', 'evitar', 'exceto', 'obs']
ACEITOS = {'.pdf', '.epub', '.mobi', '.azw', '.azw3', '.docx', '.odt', '.rtf', '.fb2', '.html', '.htm', '.txt', '.md'}


LIVROS = RAIZ / 'livros'


def repo():
    """Onde fica o histórico da biblioteca. Se o repositório do programa ignora livros/ (cópia pública) ou não existe,
    a biblioteca ganha um repositório git próprio, só local, em livros/. Senão (projeto antigo), vale o da raiz."""
    if not (LIVROS / '.git').exists():
        ignorada = subprocess.run(['git', 'check-ignore', '-q', 'livros/x'], cwd=RAIZ, capture_output=True).returncode
        if ignorada != 1:                 # 0 = ignorada; 128 = a raiz nem é um repositório
            LIVROS.mkdir(exist_ok=True)
            subprocess.run(['git', 'init', '-q'], cwd=LIVROS, capture_output=True)
    return LIVROS if (LIVROS / '.git').exists() else RAIZ


def git(*args):
    return subprocess.run(['git', *args], cwd=repo(), capture_output=True, text=True, encoding='utf-8', errors='replace')


def commit(msg, *paths):
    git('add', *[str(p) for p in paths])
    # sem nome configurado no git da máquina, o commit falharia: usa um nome local genérico
    quem = [] if git('config', 'user.name').stdout.strip() else ['-c', 'user.name=Estante', '-c', 'user.email=estante@localhost']
    return git(*quem, 'commit', '-q', '-m', msg, '--', *[str(p) for p in paths])      # só estes caminhos: o que mais estiver preparado no git não entra junto


def slug(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', s.lower()) if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:60]


def pasta_livro(nome):
    p = (RAIZ / 'livros' / nome).resolve()
    if p.parent != (RAIZ / 'livros').resolve() or not p.is_dir():
        raise HTTPException(404, 'livro não encontrado')
    return p


# ---------- importar livro novo ----------
@router.post('/api/importar')
async def importar(request: Request, titulo: str, autor: str, idioma: str = 'pt', tipo: str = 'traducao', arquivo: str = 'fonte.pdf'):
    """Corpo da requisição = bytes do arquivo do livro. Cria livros/<autor-titulo>/ com a estrutura padrão."""
    return cria_livro(await request.body(), titulo, autor, idioma, tipo, arquivo)


@router.get('/api/soltos')
def soltos():
    """Arquivos de livro largados direto na pasta livros/, ainda não importados."""
    d = RAIZ / 'livros'
    return [{'arquivo': f.name, 'kb': round(f.stat().st_size / 1024)} for f in sorted(d.iterdir()) if f.is_file() and f.suffix.lower() in ACEITOS] if d.exists() else []


@router.post('/api/importar-solto')
def importar_solto(arquivo: str, titulo: str, autor: str, idioma: str = 'pt', tipo: str = 'traducao'):
    """Importa um arquivo que já está em livros/. Depois de importado, o arquivo solto sai dali: a cópia fica em <livro>/fonte/."""
    f = (RAIZ / 'livros' / arquivo).resolve()
    if f.parent != (RAIZ / 'livros').resolve() or not f.is_file():
        raise HTTPException(404, 'arquivo não encontrado em livros/')
    r = cria_livro(f.read_bytes(), titulo, autor, idioma, tipo, f.name)
    f.unlink()
    return r


def palpite(dados, arquivo):
    """Título, autor, idioma e ação recomendada, tirados do próprio arquivo (dados do EPUB/PDF e uma amostra do texto)
    e, na falta, do nome: "Título (Autor) (site).epub". É só sugestão: a tela mostra e o usuário pode trocar tudo."""
    import html, io, zipfile
    import duplo
    base, ext = Path(arquivo).stem, Path(arquivo).suffix.lower()
    autor = (re.search(r'\(([^()]+)\)', base) or ['', ''])[1].strip()
    titulo = re.sub(r'[_]+', ' ', re.sub(r'\s*\(.*$', '', base)).strip()
    amostra, meta = '', {}
    sem_tags = lambda s: html.unescape(re.sub(r'<[^>]+>', ' ', s))      # noqa: E731
    try:
        if ext == '.epub':
            z = zipfile.ZipFile(io.BytesIO(dados))
            opf = next((z.read(n).decode('utf-8', 'replace') for n in z.namelist() if n.endswith('.opf')), '')
            for k, campo in (('titulo', 'title'), ('autor', 'creator'), ('idioma', 'language')):
                m = re.search(rf'<dc:{campo}[^>]*>([^<]+)<', opf)
                meta[k] = html.unescape(m[1]).strip() if m else ''
            paginas = [n for n in z.namelist() if n.lower().endswith(('.xhtml', '.html', '.htm'))]
            amostra = ' '.join(sem_tags(z.read(n).decode('utf-8', 'replace')) for n in paginas[len(paginas) // 3:][:4])[:20000]
        elif ext == '.pdf':
            import pymupdf
            doc = pymupdf.open(stream=dados, filetype='pdf')
            meta = {'titulo': (doc.metadata.get('title') or '').strip(), 'autor': (doc.metadata.get('author') or '').strip()}
            pags = [doc[n].get_text() for n in range(min(len(doc), 40))[5:25] or range(len(doc))]
            # edição bilíngue: a amostra fica só com as páginas do idioma mais comum, senão as palavras do outro passam por "grafia antiga"
            voto = [max(duplo.COMUNS, key=lambda k: sum(w in duplo.COMUNS[k] for w in t.lower().split())) for t in pags]
            amostra = ' '.join(t for t, v in zip(pags, voto) if v == max(set(voto), key=voto.count))[:20000]
        elif ext in ('.txt', '.md', '.html', '.htm', '.fb2'):
            amostra = sem_tags(dados[:60000].decode('utf-8', 'replace'))
    except Exception:      # noqa: BLE001  arquivo estranho: fica o palpite pelo nome
        pass
    # nome no padrão "Título (Autor)" vale mais que os dados internos do PDF, que costumam vir com lixo do programa que o gerou
    if ext == '.epub' or (not autor and meta.get('titulo') and meta.get('autor')):
        titulo, autor = meta.get('titulo') or titulo, meta.get('autor') or autor
    if re.fullmatch(r'[^,]+, [^,]+', autor):          # "Sobrenome, Nome" -> "Nome Sobrenome"
        autor = ' '.join(reversed(autor.split(', ')))
    palavras = re.findall(r'[a-zà-ÿ]+', amostra.lower())
    # idiomas que o app ainda não traduz entram só para não serem confundidos com português (testado com francês, espanhol e italiano)
    linguas = {**duplo.COMUNS, 'pt': duplo.COMUNS['pt'] | set('não são um do da no na em ao também pelo isso foi já seu sua mas'.split()),
               'es': set('el los las y del en es lo su al muy pero más como una que de la se por con no'.split()),
               'fr': set('le les des et est un une dans pour qui pas je il ne au du sur avec ce que de la se'.split()),
               'it': set('il di che per non gli della sono una nel più con le del la un si da in è'.split())}
    conta = {k: sum(w in v for w in palavras) for k, v in linguas.items()}
    idioma = max(conta, key=conta.get) if len(palavras) > 200 else (meta.get('idioma') or '')[:2].lower()
    outro = idioma if idioma and idioma not in duplo.COMUNS else ''      # reconhecido, mas sem tradução no app por enquanto
    idioma = '' if outro else idioma
    # português com muita grafia antiga (ph, th, letras dobradas…): atualizar; português atual: só extrair
    antigo = idioma == 'pt' and len(duplo.regras.sobras(amostra)) > max(8, len(palavras) // 400)
    tipo = '' if not idioma else 'traducao' if idioma != 'pt' else 'atualizacao' if antigo else 'nativo'
    return {'titulo': titulo, 'autor': autor, 'idioma': idioma, 'tipo': 'nativo' if outro else tipo, 'outro_idioma': outro, 'leu_texto': len(palavras) > 200}


@router.post('/api/palpite')
async def rota_palpite(request: Request, arquivo: str):
    """Corpo = bytes do arquivo escolhido; corpo vazio = arquivo que já está solto em livros/."""
    dados = await request.body()
    if not dados:
        f = (RAIZ / 'livros' / arquivo).resolve()
        if f.parent != (RAIZ / 'livros').resolve() or not f.is_file():
            raise HTTPException(404, 'arquivo não encontrado em livros/')
        dados = f.read_bytes()
    return palpite(dados, arquivo)


def cria_livro(dados, titulo, autor, idioma, tipo, arquivo):
    nome = slug(f'{autor} {titulo}')
    if not nome:
        raise HTTPException(400, 'título e autor são obrigatórios')
    livro = RAIZ / 'livros' / nome
    if livro.exists():
        raise HTTPException(409, f'já existe um livro "{nome}"')
    ext = Path(arquivo).suffix.lower()
    if ext not in ACEITOS or (ext == '.pdf') != dados.startswith(b'%PDF') or (ext in ('.epub', '.docx', '.odt') and not dados.startswith(b'PK')):
        raise HTTPException(400, 'formato não aceito ou arquivo corrompido. Aceitos: ' + ', '.join(sorted(e[1:].upper() for e in ACEITOS)))
    for d in ('fonte', 'ocr', 'texto', 'saida', 'revisao/historico'):
        (livro / d).mkdir(parents=True)
    (livro / 'fonte' / (slug(Path(arquivo).stem) + ext)).write_bytes(dados)
    for d in ('ocr', 'saida', 'revisao/historico'):
        (livro / d / '.gitkeep').write_text('')
    q = lambda s: s.replace('"', "'")   # noqa: E731
    (livro / 'texto' / 'livro.md').write_text(
        f'---\ntitle: "{q(titulo)}"\nauthor: "{q(autor)}"\nlang: pt-BR\n---\n\n<!-- Texto aprovado do livro. Um parágrafo por bloco. Veja README.md (seção "Como o Markdown dos livros é escrito"). -->\n',
        encoding='utf-8', newline='\n')
    (livro / 'config.json').write_text(json.dumps({'divisao_topo': 'chapter', 'quebra_secao': False}, indent=1), encoding='utf-8')
    (livro / 'revisao' / 'glossario.csv').write_text(';'.join(COLS) + '\n', encoding='utf-8', newline='\n')
    tipos = {'traducao': 'tradução direta', 'atualizacao': 'atualização de uma tradução mais antiga', 'nativo': 'edição no idioma original'}
    (livro / 'LEIA-ME.md').write_text(
        f'# {titulo} — {autor}\n\n## Procedência (preencher)\n\n- Idioma da fonte: **{idioma}**\n- Tipo: **{tipos.get(tipo, tipo)}**\n'
        '- Edição / editora / ano: (não informado)\n- Tem texto digital ou é scan: (a verificar)\n- O que NÃO foi verificado: (listar)\n\n## Estado\n\nImportado; texto ainda não extraído.\n',
        encoding='utf-8')
    tarefa = {'atualizacao': 'atualizar_pt', 'nativo': 'nenhuma'}.get(tipo) or {'en': 'traduzir', 'de': 'traduzir_de'}.get(idioma, 'nenhuma')
    (livro / 'revisao' / 'dados').mkdir(parents=True, exist_ok=True)
    (livro / 'revisao' / 'dados' / 'pipeline.json').write_text(json.dumps(
        {'estado': 'novo', 'etapa': None, 'feitas': [], 'progresso': 0, 'mensagem': '', 'config': {'tarefa': tarefa, 'idioma': idioma}}, indent=1), encoding='utf-8')
    commit(f'Importa livro novo: {titulo} ({autor})', livro)
    return {'id': nome}


@router.delete('/api/livro/{nome}')
def apaga_livro(nome: str):
    """Tira o livro da estante. Nada é destruído: a pasta inteira vai para livros/.lixeira/, de onde dá para trazer de volta à mão."""
    p = pasta_livro(nome)
    st = json.loads((p / 'revisao' / 'dados' / 'pipeline.json').read_text(encoding='utf-8')) if (p / 'revisao' / 'dados' / 'pipeline.json').exists() else {}
    if st.get('estado') == 'rodando':
        raise HTTPException(409, 'o livro está sendo processado: pause antes de apagar')
    if st.get('trabalho'):
        import fila
        fila.parar(st['trabalho'])
    lixo = RAIZ / 'livros' / '.lixeira'
    lixo.mkdir(exist_ok=True)
    destino = lixo / f"{nome}-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.move(str(p), str(destino))
    commit(f'Tira da estante: {nome} (a pasta foi para a lixeira)', p)
    return {'lixeira': str(destino.relative_to(RAIZ))}


# ---------- título em português (o original fica guardado em title-original) ----------
CABECALHO = re.compile(r'\A---\n.*?\n---\n', re.S)


def titulos(md):
    """(título em uso, título original ou None) do cabeçalho do livro.md."""
    cab = CABECALHO.match(md)
    t, o = (re.search(rf'^{k}:\s*"(.*)"\s*$', cab[0] if cab else '', re.M) for k in ('title', 'title-original'))
    return (t[1] if t else ''), (o[1] if o else None)


def troca_titulo(md, novo):
    """Cabeçalho com o título novo. O título com que o livro foi importado fica em title-original (é o que serve para procurar
    outras edições); voltar a ele tira a linha."""
    novo = ' '.join(novo.replace('"', "'").split())
    cab = CABECALHO.match(md)
    atual, original = titulos(md)
    if not cab or not atual or not novo:
        raise ValueError('o livro.md está sem título no cabeçalho, ou o título novo veio vazio')
    original = original or atual
    c = re.sub(r'^title-original:.*\n', '', cab[0], flags=re.M)
    c = re.sub(r'^title:.*$', lambda _: f'title: "{novo}"' + ('' if novo == original else f'\ntitle-original: "{original}"'), c, count=1, flags=re.M)
    return c + md[cab.end():]


@router.get('/api/livro/{nome}/titulo')
def sugere_titulo(nome: str):
    """O título original e a sugestão do tradutor para ele. Só sugere: quem decide é o usuário, em PUT."""
    import duplo
    p = pasta_livro(nome)
    atual, original = titulos((p / 'texto' / 'livro.md').read_text(encoding='utf-8'))
    f = p / 'revisao' / 'dados' / 'pipeline.json'
    tarefa = (json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}).get('config', {}).get('tarefa', '')
    if not tarefa.startswith('traduzir'):
        raise HTTPException(400, 'a sugestão de título é para livros que estão sendo traduzidos')
    try:
        return {'original': original or atual, 'sugestao': duplo.propor(tarefa, original or atual, duplo.escolhe(tarefa)[0])}
    except Exception as ex:      # noqa: BLE001
        raise HTTPException(503, f'o tradutor não respondeu ({str(ex)[:160]}); escreva o título à mão')


class Titulo(BaseModel):
    titulo: str


@router.put('/api/livro/{nome}/titulo')
def grava_titulo(nome: str, t: Titulo):
    md = pasta_livro(nome) / 'texto' / 'livro.md'
    try:
        novo = troca_titulo(md.read_text(encoding='utf-8'), t.titulo)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    md.write_text(novo, encoding='utf-8', newline='\n')
    atual, original = titulos(novo)
    commit(f'Título de {nome}: {atual}', md)
    return {'titulo': atual, 'titulo_original': original}


# ---------- aparência do livro gerado: capa e fontes, trocadas pela tela ----------
def _estilo(p, muda):
    f = p / 'estilo' / 'estilo.json'
    f.parent.mkdir(exist_ok=True)
    est = json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}
    muda(est)
    f.write_text(json.dumps(est, ensure_ascii=False, indent=1), encoding='utf-8')
    return est


@router.post('/api/livro/{nome}/estilo/capa')
async def troca_capa(nome: str, request: Request):
    """Corpo = a imagem da capa (JPEG ou PNG). Vale para o PDF e o EPUB gerados e para a estante."""
    p, dados = pasta_livro(nome), await request.body()
    ext = '.jpg' if dados.startswith(b'\xff\xd8') else '.png' if dados.startswith(b'\x89PNG') else None
    if not ext or len(dados) > 30 * 2 ** 20:
        raise HTTPException(400, 'a capa tem de ser uma imagem JPEG ou PNG de até 30 MB')
    (p / 'estilo').mkdir(exist_ok=True)
    (p / 'estilo' / ('capa-escolhida' + ext)).write_bytes(dados)
    est = _estilo(p, lambda e: e.update(capa='capa-escolhida' + ext))
    commit(f'Capa nova em {nome}', p / 'estilo')
    return est


@router.post('/api/livro/{nome}/estilo/fonte')
async def troca_fonte(nome: str, request: Request, alvo: str, arquivo: str):
    """Corpo = um arquivo de fonte (.ttf ou .otf). alvo = 'titulos' ou 'texto'. A fonte vai embutida no PDF e no EPUB gerados."""
    p, dados = pasta_livro(nome), await request.body()
    if alvo not in ('titulos', 'texto') or dados[:4] not in (b'\x00\x01\x00\x00', b'OTTO', b'true') or len(dados) > 20 * 2 ** 20:
        raise HTTPException(400, 'envie um arquivo de fonte .ttf ou .otf (até 20 MB) para os títulos ou para o texto')
    nome_arq = slug(Path(arquivo).stem) + ('.otf' if dados[:4] == b'OTTO' else '.ttf')
    (p / 'estilo' / 'fontes').mkdir(parents=True, exist_ok=True)
    (p / 'estilo' / 'fontes' / nome_arq).write_bytes(dados)
    est = _estilo(p, lambda e: e.update({alvo: {'familia': Path(arquivo).stem, 'regular': nome_arq}}))
    commit(f'Fonte nova ({alvo}) em {nome}', p / 'estilo')
    return est


@router.delete('/api/livro/{nome}/estilo/{alvo}')
def volta_ao_padrao(nome: str, alvo: str):
    """Deixa de usar a capa ou a fonte do livro (o arquivo continua na pasta estilo/); o livro gerado volta ao padrão do app nesse ponto."""
    if alvo not in ('capa', 'titulos', 'texto', 'texto_tex', 'pagina'):
        raise HTTPException(400, 'alvo desconhecido')
    p = pasta_livro(nome)
    est = _estilo(p, lambda e: e.pop(alvo, None))
    commit(f'{alvo} de {nome} volta ao padrão do app', p / 'estilo')
    return est


# ---------- glossário ----------
@router.get('/api/glossario/{nome}')
def le_glossario(nome: str):
    f = pasta_livro(nome) / 'revisao' / 'glossario.csv'
    if not f.exists():
        return []
    return [{c: (r.get(c) or '') for c in COLS} for r in csv.DictReader(f.open(encoding='utf-8'), delimiter=';')]


class Glossario(BaseModel):
    linhas: list[dict]


@router.put('/api/glossario/{nome}')
def grava_glossario(nome: str, g: Glossario):
    livro = pasta_livro(nome)
    out = io.StringIO()
    w = csv.writer(out, delimiter=';', lineterminator='\n')
    w.writerow(COLS)
    n = 0
    for r in g.linhas:
        vals = [str(r.get(c, '')).replace(';', ',').replace('\n', ' ').strip() for c in COLS]
        if vals[0] or vals[1]:
            w.writerow(vals); n += 1
    f = livro / 'revisao' / 'glossario.csv'
    f.parent.mkdir(exist_ok=True)
    f.write_text(out.getvalue(), encoding='utf-8', newline='\n')
    commit(f'Glossário de {nome}: {n} termos', f)
    return {'ok': True, 'termos': n}


TERMO = re.compile(r"[A-ZÀ-Ý][\w’'-]*(?:(?:\s+(?:of|the|and|de|da|do|dos|das|von|van|der|des|du|la|le)){0,2}\s+[A-ZÀ-Ý][\w’'-]*){0,3}")
INICIO = re.compile(r'(?:^|[.!?:;…—–]["”’»)\]]*\s+|\n\s*)[\s"“‘«(\[]*$')
CORRIQUEIRAS = set('I The A An It He She We They You This That These Those There Here But And Or Nor If In On At As Of To For With By From Mr Mrs Ms Dr St Sir '
                   'When What Why How Where Who Which While Yet So Not No Yes Now Then Thus Since Because Although Though After Before Even Perhaps Indeed Still '
                   'Such Some Many Most All Each Every Any One Two Three His Her Its Their Our My Your Is Are Was Were Do Does Did Can Could Would Should May Might Let '
                   'Part Chapter Book Section January February March April May June July August September October November December '
                   'Monday Tuesday Wednesday Thursday Friday Saturday Sunday '
                   'O Os As Um Uma Ele Ela Eles Elas Isso Este Esta Esse Essa Mas E Ou Se Em No Na Por Para Com Como Quando Parte Capítulo '
                   'Der Die Das Ein Eine Und Sie Er Es Wir Ich Aber Oder Wenn Nicht Auch Kapitel Teil'.split())


def sugestoes_de_termos(textos, ja=()):
    """Nomes e termos que se repetem na fonte: sequências de palavras em maiúscula, vistas ao menos 3 vezes e ao menos uma vez
    fora do começo de frase (no começo, a maiúscula não quer dizer nada). Sem modelo: é só uma lista do que vale a pena fixar
    no glossário antes de traduzir; quem decide é o usuário. Devolve [{'termo', 'vezes', 'exemplo'}], os mais frequentes primeiro."""
    conta, meio, exemplo = {}, {}, {}
    for t in textos:
        # sem marcação (os links primeiro: o endereço pode ter "_", que depois seria tomado por itálico)
        t = re.sub(r'<[^>]+>|\[\^[^\]]+\]|[*_#]', ' ', re.sub(r'!?\[([^\]]*)\]\((?:[^()\s]|\([^()\s]*\))+\)', r'\1', t))
        for m in TERMO.finditer(t):
            termo, ini = m[0], m.start()
            while ' ' in termo and (termo.split(None, 1)[0] in CORRIQUEIRAS or termo[0].islower()):      # "The Citadel" e "Of the Citadel" são o termo "Citadel"
                resto = termo.split(None, 1)[1]
                ini += len(termo) - len(resto); termo = resto
            termo = re.sub(r"[’']s$", '', termo).strip("’'-")              # "Lindqvist’s" conta para "Lindqvist"
            if len(termo) < 3 or termo in CORRIQUEIRAS or termo.isdigit() or re.search(r"[’'](m|t|re|ve|ll|d)$", termo):      # I’m, Don’t…
                continue
            conta[termo] = conta.get(termo, 0) + 1
            if not INICIO.search(t[:ini]):
                meio[termo] = meio.get(termo, 0) + 1
                exemplo.setdefault(termo, ' '.join(t[max(0, ini - 70):m.end() + 70].split()))
    tem = {x.strip().lower() for x in ja}
    achados = [{'termo': k, 'vezes': n, 'exemplo': exemplo[k]} for k, n in conta.items() if n >= 3 and meio.get(k) and k.lower() not in tem]
    return sorted(achados, key=lambda a: (-a['vezes'], a['termo']))[:80]


@router.get('/api/glossario/{nome}/sugestoes')
def sugere_termos(nome: str):
    p = pasta_livro(nome)
    f = p / 'fonte' / 'dados' / 'source.json'
    if not f.exists():
        return []                        # o texto ainda não foi extraído: nada a sugerir
    blocos = json.loads(f.read_text(encoding='utf-8')).get('blocks', [])
    return sugestoes_de_termos([b.get('text') or '' for b in blocos if b.get('kind') in ('paragraph', 'heading')], [r['fonte'] for r in le_glossario(nome)])


# ---------- colação ----------
@router.post('/api/colacao')
async def colacao(request: Request, livro: str, nome: str = 'outra-copia'):
    """Corpo = texto simples da outra cópia (parágrafos começando por 'N. '). Exige fonte/dados/source.json."""
    p = pasta_livro(livro)
    if not (p / 'fonte' / 'dados' / 'source.json').exists():
        raise HTTPException(400, 'este livro não tem fonte/dados/source.json (texto-fonte estruturado), necessário para a colação')
    texto = (await request.body()).decode('utf-8', errors='replace')
    if len(texto) < 500:
        raise HTTPException(400, 'texto muito curto')
    dest = p / 'fonte' / 'outras-copias'
    dest.mkdir(exist_ok=True)
    arq = dest / (slug(nome) + '.txt')
    arq.write_text(texto, encoding='utf-8')
    r = subprocess.run([PY, str(RAIZ / 'ferramentas' / 'colacionar.py'), str(p), str(arq)], capture_output=True, text=True, encoding='utf-8', errors='replace',
                       env={**__import__('os').environ, 'PYTHONIOENCODING': 'utf-8'})
    if r.returncode:
        raise HTTPException(500, (r.stderr or r.stdout)[-400:])
    rel = next(iter(sorted((p / 'revisao').glob(f'colacao - {arq.stem[:60]}*.md'))), None)
    commit(f'Colação de {livro} com {arq.name}', arq, *( [rel] if rel else []))
    return {'resumo': r.stdout.strip(), 'relatorio': rel.read_text(encoding='utf-8')[:60000] if rel else ''}


if __name__ == '__main__':      # autoteste: python app/extras.py
    md = '---\ntitle: "The Book"\nauthor: "A"\nlang: pt-BR\n---\n\ntitle: "isto é texto, não cabeçalho"\n'
    pt = troca_titulo(md, 'O  "Livro"')
    assert pt == '---\ntitle: "O \'Livro\'"\ntitle-original: "The Book"\nauthor: "A"\nlang: pt-BR\n---\n\ntitle: "isto é texto, não cabeçalho"\n', pt
    assert titulos(pt) == ("O 'Livro'", 'The Book') and titulos(md) == ('The Book', None)
    assert titulos(troca_titulo(pt, 'Outro')) == ('Outro', 'The Book')          # o original não se perde na segunda troca
    assert troca_titulo(pt, 'The Book') == md                                    # voltar ao original tira a linha
    livro = ['The Citadel rules. Nobody doubts the Citadel, said Anna Lindqvist.', 'However, the Citadel is patient. However, it waits.',
             'According to Anna Lindqvist, the [Long Winter](http://x.y/z) begins. However late.', 'The Long Winter is no joke; the Long Winter is Lindqvist.']
    s = sugestoes_de_termos(livro, ja=['anna lindqvist'])
    assert [(x['termo'], x['vezes']) for x in s] == [('Citadel', 3), ('Long Winter', 3)], s      # "However" só aparece em começo de frase; "Lindqvist" sozinho, uma vez
    assert 'Nobody doubts the Citadel' in s[0]['exemplo']
    print('ok')
