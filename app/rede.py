"""Único ponto do app que fala com a internet. Tudo desligado por padrão; cada função confere a chave dela em config.

O que sai da máquina fica anotado em app/dados/rede.log (data, destino, o que foi enviado), e a tela Configurações mostra.
  consulta(termo, idioma)    dicionário e enciclopédia para um termo do glossário: sai só o termo
  edicoes(titulo, autor)     outras edições em acervos públicos: saem só título e autor
  acervos(busca), arquivos(id), baixa(url, nome)    buscar e baixar livros de acervos abertos (mesma chave): sai só a busca e o pedido do arquivo
  conversa_fora(mensagens)   modelo pela internet, com endereço e chave do usuário: SAI O TEXTO do bloco
Nenhuma resposta de fora vira texto do livro sozinha: consulta e edições são referência para o usuário,
e a saída de um modelo de fora passa pelas mesmas checagens e pelo mesmo aceite dos modelos locais.
"""
import json, re, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

import config

REGISTRO = Path(__file__).resolve().parent / 'dados' / 'rede.log'
AGENTE = {'User-Agent': 'Estante (app local de livros; https://github.com/kaymitow/ESTANTE)'}


class Desligado(Exception):
    pass


def _exige(chave):
    if not config.le()['rede'].get(chave):
        raise Desligado(f'esta função usa a internet e está desligada (Configurações → Rede → {chave})')


def _anota(destino, enviado):
    REGISTRO.parent.mkdir(exist_ok=True)
    with REGISTRO.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'quando': time.strftime('%Y-%m-%d %H:%M:%S'), 'destino': destino, 'enviado': enviado}, ensure_ascii=False) + '\n')


def registro(n=100):
    if not REGISTRO.exists():
        return []
    return [json.loads(l) for l in REGISTRO.read_text(encoding='utf-8').split('\n')[-n - 1:] if l.strip()][::-1]


def _json(url, corpo=None, cabecalhos=None, timeout=20):
    req = urllib.request.Request(url, json.dumps(corpo).encode() if corpo is not None else None, {**AGENTE, **(cabecalhos or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def consulta(termo, idioma='en'):
    """Definição (Wikcionário) e resumo (Wikipédia) do termo, no idioma dado. Só o termo sai da máquina."""
    _exige('pesquisa')
    termo = termo.strip()[:80]
    out = {'termo': termo, 'idioma': idioma, 'definicoes': [], 'resumo': '', 'fontes': []}
    q = urllib.parse.quote(termo.replace(' ', '_'), safe='')
    _anota(f'{idioma}.wikipedia.org, en.wiktionary.org', termo)
    try:
        d = _json(f'https://en.wiktionary.org/api/rest_v1/page/definition/{q}')
        for grupo in d.get(idioma, [])[:3]:
            for x in grupo.get('definitions', [])[:3]:
                texto = __import__('re').sub(r'<[^>]+>', '', x.get('definition', '')).strip()
                if texto:
                    out['definicoes'].append(f"({grupo.get('partOfSpeech', '')}) {texto}")
        out['fontes'].append(f'https://en.wiktionary.org/wiki/{q}')
    except (OSError, ValueError, KeyError):      # sem resposta, tempo esgotado ou formato inesperado
        pass
    try:
        d = _json(f'https://{idioma}.wikipedia.org/api/rest_v1/page/summary/{q}')
        if d.get('type') != 'disambiguation':
            out['resumo'] = d.get('extract', '')
        out['fontes'].append(d.get('content_urls', {}).get('desktop', {}).get('page', ''))
    except (OSError, ValueError, KeyError):      # sem resposta, tempo esgotado ou formato inesperado
        pass
    return out


def _opds(xml):
    """Livros de uma resposta do catálogo do Project Gutenberg (Atom/OPDS): [(número, título, autor, idioma)]."""
    import xml.etree.ElementTree as ET
    A = '{http://www.w3.org/2005/Atom}'
    achados = []
    for e in ET.fromstring(xml).iter(A + 'entry'):
        m = re.search(r'/ebooks/(\d+)\.opds', e.findtext(A + 'id') or '')      # as outras entradas são atalhos do catálogo (autores, ordenação)
        if m:
            t = re.match(r'(.*?)(?: \(([^()]+)\))?$', (e.findtext(A + 'title') or '').strip(), re.S)
            achados.append((m[1], t[1], (e.findtext(A + 'content') or '').strip(), t[2] or ''))
    return achados


def _gutenberg(busca):
    """Busca no próprio gutenberg.org. O Gutendex, usado antes, leva mais de 30 s para responder (medido em 07/10/2026) e nunca chegava a tempo."""
    req = urllib.request.Request('https://www.gutenberg.org/ebooks/search.opds/?' + urllib.parse.urlencode({'query': busca}), headers=AGENTE)
    with urllib.request.urlopen(req, timeout=20) as r:
        return _opds(r.read(2 << 20))


def edicoes(titulo, autor=''):
    """Outras edições do livro em acervos públicos (Internet Archive, Open Library, Gutenberg). Saem só título e autor."""
    _exige('edicoes')
    _anota('archive.org, openlibrary.org, gutenberg.org', f'{titulo} / {autor}')
    achados, mudos = [], []
    try:
        q = f'title:("{titulo}")' + (f' AND creator:("{autor}")' if autor else '') + ' AND mediatype:texts'
        d = _json('https://archive.org/advancedsearch.php?' + urllib.parse.urlencode(
            [('q', q), ('fl[]', 'identifier'), ('fl[]', 'title'), ('fl[]', 'year'), ('fl[]', 'language'), ('fl[]', 'creator'), ('rows', '25'), ('output', 'json')]))
        for x in d['response']['docs']:
            lingua = x.get('language', '')
            achados.append({'acervo': 'Internet Archive', 'titulo': x.get('title', ''), 'autor': x.get('creator', '') if isinstance(x.get('creator'), str) else ', '.join(x.get('creator', [])),
                            'ano': str(x.get('year', '')), 'idioma': lingua if isinstance(lingua, str) else ', '.join(lingua),
                            'link': f"https://archive.org/details/{x['identifier']}"})
    except (OSError, ValueError, KeyError):
        mudos.append('Internet Archive')
    try:
        d = _json('https://openlibrary.org/search.json?' + urllib.parse.urlencode({'title': titulo, 'author': autor, 'limit': 15, 'fields': 'key,title,author_name,first_publish_year,language,edition_count'}))
        for x in d.get('docs', []):
            achados.append({'acervo': 'Open Library', 'titulo': x.get('title', ''), 'autor': ', '.join(x.get('author_name', [])), 'ano': str(x.get('first_publish_year', '')),
                            'idioma': ', '.join(x.get('language', [])[:6]), 'link': 'https://openlibrary.org' + x['key'], 'edicoes': x.get('edition_count')})
    except (OSError, ValueError, KeyError):
        mudos.append('Open Library')
    try:
        for n, t, a, lingua in _gutenberg(f'{titulo} {autor}'.strip())[:10]:
            achados.append({'acervo': 'Project Gutenberg', 'titulo': t, 'autor': a, 'ano': '', 'idioma': lingua, 'link': f'https://www.gutenberg.org/ebooks/{n}'})
    except (OSError, ValueError, KeyError):
        mudos.append('Project Gutenberg')
    return {'achados': achados, 'sem_resposta': mudos}


ACERVOS = ('archive.org', 'gutenberg.org')      # os únicos lugares de onde o app aceita baixar um livro
LIMITE = 300 * 2 ** 20                          # 300 MB por arquivo


def _permitido(url):
    u = urllib.parse.urlsplit(url)
    return u.scheme == 'https' and any(u.hostname == h or (u.hostname or '').endswith('.' + h) for h in ACERVOS)


def acervos(busca):
    """Livros com arquivo aberto para baixar (Internet Archive e Project Gutenberg). Sai só o que foi digitado na busca.
    Empréstimo digital (que pede conta e vem com trava) fica de fora: o app não tem login."""
    _exige('edicoes')
    busca = busca.strip()[:120]
    _anota('archive.org, gutenberg.org', busca)
    achados, mudos = [], []
    junta = lambda v: v if isinstance(v, str) else ', '.join(v or [])      # noqa: E731
    try:
        q = (f'({busca}) AND mediatype:texts AND format:(EPUB OR "Text PDF") '
             'AND NOT collection:(inlibrary OR printdisabled) AND NOT access-restricted-item:true')
        d = _json('https://archive.org/advancedsearch.php?' + urllib.parse.urlencode(
            [('q', q), ('fl[]', 'identifier'), ('fl[]', 'title'), ('fl[]', 'creator'), ('fl[]', 'year'), ('fl[]', 'language'), ('rows', '20'), ('output', 'json')]))
        for x in d['response']['docs']:
            achados.append({'acervo': 'Internet Archive', 'id': x['identifier'], 'titulo': junta(x.get('title', '')), 'autor': junta(x.get('creator', '')), 'ano': str(x.get('year', '')),
                            'idioma': junta(x.get('language', '')), 'link': f"https://archive.org/details/{x['identifier']}", 'arquivos': None})      # None = pedir com arquivos(id)
    except (OSError, ValueError, KeyError):
        mudos.append('Internet Archive')
    try:
        for n, t, a, lingua in _gutenberg(busca)[:12]:
            achados.append({'acervo': 'Project Gutenberg', 'id': n, 'titulo': t, 'autor': a, 'ano': '', 'idioma': lingua, 'link': f'https://www.gutenberg.org/ebooks/{n}',
                            'arquivos': [{'formato': 'EPUB', 'url': f'https://www.gutenberg.org/ebooks/{n}.epub3.images', 'kb': None}]})
    except (OSError, ValueError, KeyError):
        mudos.append('Project Gutenberg')
    return {'achados': achados, 'sem_resposta': mudos}


def arquivos(ident):
    """Arquivos de livro de um item do Internet Archive (EPUB e PDF com texto), com o tamanho de cada um."""
    _exige('edicoes')
    ident = re.sub(r'[^\w.-]', '', ident)
    _anota('archive.org', f'lista de arquivos de {ident}')
    d = _json(f'https://archive.org/metadata/{ident}/files')
    return [{'formato': 'EPUB' if x['format'] == 'EPUB' else 'PDF', 'url': f"https://archive.org/download/{ident}/{urllib.parse.quote(x['name'])}", 'kb': round(int(x.get('size') or 0) / 1024)}
            for x in d.get('result', []) if x.get('format') in ('EPUB', 'Text PDF', 'Additional Text PDF') and x.get('private') != 'true']


class _SoAcervos(urllib.request.HTTPRedirectHandler):
    """O acervo pode redirecionar o download para outro servidor dele; para fora da lista, não."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _permitido(newurl):
            raise urllib.error.HTTPError(newurl, code, 'o acervo redirecionou para fora da lista permitida', headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def busca_arquivo(url):
    """Os bytes de um livro de um acervo aberto e a extensão dele. Só https, só dos acervos da lista (a cada redirecionamento),
    só EPUB ou PDF de verdade (conferido pelo começo do arquivo), até o limite de tamanho."""
    _exige('edicoes')
    if not _permitido(url):
        raise ValueError('o app só baixa de ' + ' e '.join(ACERVOS))
    _anota(urllib.parse.urlsplit(url).hostname, f'download de {url}')
    dados = b''
    with urllib.request.build_opener(_SoAcervos).open(urllib.request.Request(url, headers=AGENTE), timeout=60) as r:
        while pedaco := r.read(1 << 20):
            dados += pedaco
            if len(dados) > LIMITE:
                raise ValueError('arquivo maior que o limite de 300 MB')
    ext = '.epub' if dados.startswith(b'PK') else '.pdf' if dados.startswith(b'%PDF') else None
    if not ext:
        raise ValueError('o que veio não é um EPUB nem um PDF')
    return dados, ext


def baixa(url, nome):
    """Baixa um livro de um acervo aberto para a pasta livros/, como arquivo solto: o usuário importa depois, como qualquer outro."""
    dados, ext = busca_arquivo(url)
    base = re.sub(r'[\\/:*?"<>|\s]+', ' ', nome).strip()[:120] or 'livro'
    pasta = Path(__file__).resolve().parent.parent / 'livros'
    pasta.mkdir(exist_ok=True)
    destino, n = pasta / (base + ext), 1
    while destino.exists():
        n += 1; destino = pasta / f'{base} {n}{ext}'
    destino.write_bytes(dados)
    return destino


def conversa_fora(mensagens, max_tokens=2000):
    """Um pedido a um modelo pela internet (API no formato OpenAI). O texto do bloco sai da máquina: só com a chave 'modelo_fora' ligada."""
    _exige('modelo_fora')
    r = config.le()['rede']
    if not r['fora_url'] or not r['fora_modelo']:
        raise Desligado('falta o endereço ou o nome do modelo de fora (Configurações → Rede)')
    url = r['fora_url'].rstrip('/')
    url = url if url.endswith('/chat/completions') else url + '/chat/completions'
    _anota(urllib.parse.urlsplit(url).netloc, f"texto de um bloco ({sum(len(str(m.get('content', ''))) for m in mensagens)} caracteres) para o modelo {r['fora_modelo']}")
    d = _json(url, {'model': r['fora_modelo'], 'messages': mensagens, 'temperature': 0, 'max_tokens': max_tokens},
              {'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + r['fora_chave']} if r['fora_chave'] else {})}, timeout=300)
    return (d['choices'][0]['message'].get('content') or '').strip()


if __name__ == '__main__':      # autoteste (sem rede): python app/rede.py
    assert _permitido('https://archive.org/download/x/x.epub') and _permitido('https://ia800.us.archive.org/1/x.pdf') and _permitido('https://www.gutenberg.org/ebooks/1.epub3.images')
    assert not _permitido('http://archive.org/x.epub') and not _permitido('https://archive.org.exemplo.com/x.epub') and not _permitido('https://exemplo.com/archive.org/x.epub')
    assert not _permitido('file:///C:/x.epub') and not _permitido('https://127.0.0.1/x.epub')
    atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://www.gutenberg.org/ebooks/authors/search.opds/?query=x</id><title>Authors</title></entry>'
            '<entry><id>https://www.gutenberg.org/ebooks/55752.opds</id><title>Livro de exemplo (Portuguese)</title><content type="text">Autor de exemplo</content></entry>'
            '<entry><id>https://www.gutenberg.org/ebooks/84.opds</id><title>Outro livro de exemplo; Or, Exemplo</title><content type="text">Autor B</content></entry></feed>')
    assert _opds(atom) == [('55752', 'Livro de exemplo', 'Autor de exemplo', 'Portuguese'), ('84', 'Outro livro de exemplo; Or, Exemplo', 'Autor B', '')], _opds(atom)
    assert _permitido('https://www.gutenberg.org/ebooks/55752.epub3.images')
    print('ok')
