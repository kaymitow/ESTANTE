"""Servidor local do aplicativo (FastAPI). Roda só em 127.0.0.1; nada sai do seu PC.

  .venv\\Scripts\\python app\\servidor.py        (ou o atalho iniciar-app.bat)  ->  http://127.0.0.1:8765

Camada fina sobre as ferramentas/ que já existem. Regras do projeto, aplicadas aqui:
- a IA SÓ SUGERE; gravar texto é sempre uma ação explícita do usuário;
- toda gravação vira um commit no git (histórico e "desfazer");
- fonte/ nunca é alterada por esta API.
"""
import json, re, subprocess, sys, threading, time, urllib.request, uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'ferramentas'))
from buscar import sem_acento, unidades, limpa   # noqa: E402

PY = sys.executable
app = FastAPI(title='Estante')
PORTA = int(__import__('os').environ.get('ESTANTE_PORTA', '8765'))
DONOS = {f'127.0.0.1:{PORTA}', f'localhost:{PORTA}'}


@app.middleware('http')
async def so_desta_maquina(request, call_next):
    """O servidor só escuta em 127.0.0.1, mas um site aberto no navegador ainda poderia mandar pedidos para cá.
    Recusa o que não vem da própria tela do app: endereço (Host) estranho, ou pedido de escrita vindo de outra origem."""
    origem = request.headers.get('origin')
    if request.headers.get('host') not in DONOS or (origem and origem.split('://', 1)[-1] not in DONOS):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': 'pedido recusado: o Estante só atende a própria tela, nesta máquina'}, status_code=403)
    return await call_next(request)
JOBS: dict[str, dict] = {}


# ---------- livros ----------
def pasta_livro(nome):
    p = (RAIZ / 'livros' / nome).resolve()
    if p.parent != (RAIZ / 'livros').resolve() or not (p / 'texto' / 'livro.md').exists():
        raise HTTPException(404, 'livro não encontrado')
    return p


@app.get('/api/livros')
def livros():
    out = []
    (RAIZ / 'livros').mkdir(exist_ok=True)
    for p in sorted((RAIZ / 'livros').iterdir()):
        md = p / 'texto' / 'livro.md'
        if not md.exists():
            continue
        texto = md.read_text(encoding='utf-8')
        titulo = re.search(r'^title:\s*"(.*)"', texto, re.M)
        original = re.search(r'^title-original:\s*"(.*)"', texto, re.M)      # só existe quando o usuário deu um título em português
        autor = re.search(r'^author:\s*"(.*)"', texto, re.M)
        saida = p / 'saida'
        try:
            andamento = pipeline.estado(p.name)
        except Exception:      # noqa: BLE001
            andamento = {}
        out.append({'id': p.name, 'titulo': titulo[1] if titulo else p.name, 'titulo_original': original[1] if original else None, 'autor': autor[1] if autor else '',
                    'paragrafos': sum(1 for _ in unidades(md)),
                    'pdf': (saida / f'{p.name}.pdf').exists(), 'epub': (saida / f'{p.name}.epub').exists(),
                    'glossario': (p / 'revisao' / 'glossario.csv').exists(), 'anotacoes': (p / 'texto' / 'anotacoes.md').exists(),
                    'processando': andamento.get('estado') == 'rodando', 'novo': andamento.get('estado') == 'novo', 'pausado': andamento.get('estado') in ('pausado', 'erro'),
                    'rascunho': andamento.get('rascunho'), 'capa': bool(capa_do(p))})
    return out


@app.get('/api/buscar')
def buscar(q: str, livro: str = '', limite: int = 60):
    termos = [sem_acento(t) for t in q.split() if t]
    if not termos:
        return []
    res = []
    for p in sorted((RAIZ / 'livros').iterdir()):
        md = p / 'texto' / 'livro.md'
        if not md.exists() or (livro and livro != p.name):
            continue
        for texto, rotulo in unidades(md):
            base = sem_acento(texto)
            if all(t in base for t in termos):
                i = base.find(termos[0])
                res.append({'livro': p.name, 'rotulo': rotulo, 'trecho': texto[max(0, i - 90):i + 170], 'termo': termos[0]})
                if len(res) >= limite:
                    return res
    return res


# ---------- conferência / edição ----------
@app.get('/api/livro/{nome}/linhas')
def linhas(nome: str):
    """Blocos editáveis do livro.md: títulos e parágrafos, com o índice da linha."""
    md = pasta_livro(nome) / 'texto' / 'livro.md'
    saida, pagina, em_yaml = [], '', False
    for i, l in enumerate(md.read_text(encoding='utf-8').split('\n')):
        s = l.strip()
        if i == 0 and s == '---':
            em_yaml = True; continue
        if em_yaml:
            em_yaml = s != '---'; continue
        m = re.match(r'<!-- pg: scan (\d+) · impressa (.*?) · confiança (\S+)', s)
        if m:
            pagina = f'scan {m[1]} · impressa {m[2]}'; continue
        m = re.match(r'<!-- org: (seção \d+ do original)', s)      # livro que veio de EPUB: a origem é a seção, não a página
        if m:
            pagina = m[1]; continue
        if not s or s.startswith(('<!--', ':::', '|', '![')):
            continue
        tipo = 'titulo' if s.startswith('#') else 'par'
        saida.append({'i': i, 'tipo': tipo, 'raw': l, 'pagina': pagina})
    return saida


class Edicao(BaseModel):
    livro: str
    i: int
    antigo: str
    novo: str
    motivo: str = ''


def git(*args):
    import extras
    return extras.git(*args)


@app.post('/api/editar')
def editar(e: Edicao):
    md = pasta_livro(e.livro) / 'texto' / 'livro.md'
    L = md.read_text(encoding='utf-8').split('\n')
    if e.i >= len(L) or L[e.i] != e.antigo:
        raise HTTPException(409, 'o arquivo mudou desde que você abriu; recarregue')
    if '\n' in e.novo:
        raise HTTPException(400, 'um parágrafo por linha (sem quebra de linha)')
    L[e.i] = e.novo
    md.write_text('\n'.join(L), encoding='utf-8', newline='\n')
    import extras
    r = extras.commit(f'Edita {e.livro}, linha {e.i + 1}' + (f': {e.motivo}' if e.motivo else ''), md)
    return {'ok': True, 'commit': r.returncode == 0}


@app.get('/api/historico')
def historico(livro: str, n: int = 15):
    md = pasta_livro(livro) / 'texto' / 'livro.md'
    r = git('log', f'-{n}', '--format=%h|%ad|%s', '--date=format:%d/%m %H:%M', '--', str(md))
    return [dict(zip(('hash', 'data', 'msg'), l.split('|', 2))) for l in r.stdout.splitlines() if l]


# ---------- tarefas longas (construir / verificar / glossário) ----------
def roda(job_id, cmd):
    j = JOBS[job_id]
    try:
        p = subprocess.Popen(cmd, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                             env={**__import__('os').environ, 'PYTHONIOENCODING': 'utf-8'})
        for linha in p.stdout:
            j['log'].append(linha.rstrip())
        j['codigo'] = p.wait()
    except Exception as ex:      # noqa: BLE001
        j['log'].append(f'erro: {ex}'); j['codigo'] = -1
    j['fim'] = time.time()


class Tarefa(BaseModel):
    livro: str = ''
    acao: str                    # epub | pdf | tudo | anotada | verificar | glossario


@app.post('/api/tarefa')
def tarefa(t: Tarefa):
    F = RAIZ / 'ferramentas'
    if t.acao in ('epub', 'pdf', 'tudo', 'anotada', 'docx', 'odt', 'html', 'fb2', 'azw3', 'todos', 'bilingue'):
        pasta_livro(t.livro)
        # livro ainda sem texto aceito (processado antes do livro sair do rascunho): monta o livro.md a partir do rascunho
        import revisao
        rasc = RAIZ / 'livros' / t.livro
        r = pipeline._le(rasc / 'revisao' / 'dados' / 'rascunho.json') or {}
        md = rasc / 'texto' / 'livro.md'
        if r and not r.get('livro_gerado') and not any(b.get('aceito') for b in r.get('blocos', [])) and not (md.exists() and revisao._corpo(md.read_text(encoding='utf-8'))):
            revisao.gera_livro_md(rasc)
        cmd = [PY, str(F / 'construir.py'), f'livros/{t.livro}', t.acao]
    elif t.acao == 'verificar':
        pasta_livro(t.livro); cmd = [PY, str(F / 'verificar.py'), f'livros/{t.livro}']
    elif t.acao == 'glossario':
        cmd = [PY, str(F / 'checar_glossario.py'), t.livro[:12]] if t.livro else [PY, str(F / 'checar_glossario.py')]
    else:
        raise HTTPException(400, 'ação desconhecida')
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {'acao': t.acao, 'livro': t.livro, 'log': [], 'codigo': None, 'inicio': time.time(), 'fim': None}
    threading.Thread(target=roda, args=(jid, cmd), daemon=True).start()
    return {'id': jid}


@app.get('/api/tarefa/{jid}')
def estado(jid: str, desde: int = 0):
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404)
    return {'log': j['log'][desde:], 'total': len(j['log']), 'codigo': j['codigo'], 'rodando': j['codigo'] is None,
            'segundos': round((j['fim'] or time.time()) - j['inicio'])}


# ---------- IA local: só sugere ----------
sys.path.insert(0, str(Path(__file__).parent))
import duplo   # noqa: E402
import motor   # noqa: E402


@app.get('/api/modelos')
def modelos():
    return {'ok': True, 'modelos': motor.instalados()}


# ---------- arquivos gerados e identidade do livro ----------
@app.get('/api/livro/{nome}/saida')
def saidas(nome: str):
    d = pasta_livro(nome) / 'saida'
    return [{'arquivo': f.name, 'kb': round(f.stat().st_size / 1024), 'quando': f.stat().st_mtime}
            for f in sorted(d.iterdir()) if f.is_file() and not f.name.startswith('.')] if d.exists() else []


@app.get('/api/livro/{nome}/saida/{arquivo}')
def saida_arquivo(nome: str, arquivo: str):
    f = (pasta_livro(nome) / 'saida' / arquivo).resolve()
    if f.parent != (pasta_livro(nome) / 'saida').resolve() or not f.is_file():
        raise HTTPException(404, 'arquivo não encontrado')
    return FileResponse(f, filename=f.name if f.suffix != '.pdf' else None)      # PDF abre no navegador; o resto baixa


def capa_do(p):
    """Arquivo da capa em uso no livro (a do original ou a que o usuário escolheu), ou None."""
    f = p / 'estilo' / 'estilo.json'
    nome = json.loads(f.read_text(encoding='utf-8')).get('capa') if f.exists() else None
    return p / 'estilo' / nome if nome and (p / 'estilo' / nome).is_file() else None


@app.get('/api/livro/{nome}/estilo')
def estilo_do_livro(nome: str):
    f = pasta_livro(nome) / 'estilo' / 'estilo.json'
    return json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}


@app.get('/api/livro/{nome}/capa')
def capa(nome: str):
    p = pasta_livro(nome)
    est = estilo_do_livro(nome)
    if not est.get('capa') or not (p / 'estilo' / est['capa']).is_file():
        raise HTTPException(404, 'este livro não tem capa')
    return FileResponse(p / 'estilo' / est['capa'])


# ---------- fluxo de dois modelos ----------
from lote import router as router_lote   # noqa: E402
import leitor      # noqa: E402
app.include_router(leitor.router)
app.include_router(router_lote)
import copias      # noqa: E402
app.include_router(copias.router)
import fila   # noqa: E402
fila.iniciar()        # retoma lotes que ficaram pela metade
import pipeline   # noqa: E402
pipeline.retomar_todos()   # e os livros que estavam sendo processados
import fila_livros   # noqa: E402
fila_livros.iniciar_laco(pipeline)   # modo lote: a fila de livros, um por vez; também mantém o computador acordado enquanto há livro rodando
app.include_router(fila_livros.router)
from extras import router as router_extras   # noqa: E402
app.include_router(router_extras)
from revisao import router as router_revisao   # noqa: E402
app.include_router(router_revisao)
from prova import router as router_prova   # noqa: E402
app.include_router(router_prova)
from partes import router as router_partes   # noqa: E402
app.include_router(router_partes)
from modelos import router as router_modelos   # noqa: E402
app.include_router(router_modelos)
from ajustes import router as router_ajustes   # noqa: E402
app.include_router(router_ajustes)


# ---------- interface ----------
app.mount('/static', StaticFiles(directory=Path(__file__).parent / 'static'), name='static')


@app.get('/')
def raiz():
    """A interface do app (Svelte). O build fica em app/static/novo."""
    return FileResponse(Path(__file__).parent / 'static' / 'novo' / 'index.html')


@app.get('/novo')
def novo():
    """Endereço antigo da interface: quem guardou o atalho continua chegando (o trecho depois de # é mantido pelo navegador)."""
    return RedirectResponse('/')


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=PORTA, log_level='warning')
