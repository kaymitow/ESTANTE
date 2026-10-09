"""Motor de IA: o llama-server (llama.cpp) roda como processo do app, com um modelo por vez (a placa de 12 GB não cabe os cinco).
Os modelos são arquivos GGUF numa pasta do usuário (ESTANTE_MODELOS, padrão %APPDATA%\\Estante\\modelos); o catálogo fica em modelos.json.
Pedir outro modelo para o motor para o atual e sobe o outro. Quem chama (duplo.chat) já serializa os pedidos com o semáforo GPU."""
import atexit, json, os, socket, subprocess, threading, time, urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent                       # no programa instalado é resources/ (o app fica em resources/app)
CATALOGO = json.loads((AQUI / 'modelos.json').read_text(encoding='utf-8'))
PASTA = Path(os.environ['ESTANTE_MODELOS']) if os.environ.get('ESTANTE_MODELOS') else Path(os.environ.get('APPDATA', str(AQUI))) / 'Estante' / 'modelos'
CTX = int(os.environ.get('ESTANTE_CTX', '8192'))              # tokens por pedido
PARALELO = int(os.environ.get('ESTANTE_PARALELO', '1'))        # pedidos ao mesmo tempo; o contexto total é CTX x PARALELO
PID = AQUI / 'dados' / 'motor.pid'
LOG = AQUI / 'dados' / 'motor.log'
SEM_JANELA = subprocess.CREATE_NO_WINDOW
TRAVA = threading.Lock()
_atual = {'nome': None, 'proc': None, 'porta': None}
# o que o Ollama usava por padrão e os modelos não pedem: a repetição de 1,1 muda o texto mesmo com temperatura 0
AMOSTRA_PADRAO = {'repeat_penalty': 1.1, 'repeat_last_n': 64}


def placa():
    try:
        r = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5, creationflags=SEM_JANELA)
        nome, mb = r.stdout.strip().split('\n')[0].rsplit(',', 1)
        return {'nome': nome.strip(), 'gb': round(int(mb) / 1024, 1)}
    except Exception:      # noqa: BLE001
        return None


def _proprios():
    import config
    return config.le().get('modelos_proprios') or {}


def ache(nome):
    """(modelo do catálogo ou {}, arquivo GGUF, projetor de imagem ou None) se o modelo está instalado; senão None."""
    m = next((c for c in CATALOGO if c['nome'] == nome), None)
    if m is None and nome in _proprios():
        arq = Path(_proprios()[nome])
        return ({'nome': nome}, arq, None) if arq.is_file() else None
    if m is None:
        return None
    arq = PASTA / m['arquivo']
    mm = PASTA / m['mmproj']['arquivo'] if m.get('mmproj') else None
    return (m, arq, mm) if arq.is_file() and (mm is None or mm.is_file()) else None


def instalados():
    """Modelos instalados: [{nome, gb}] (o do catálogo e os próprios)."""
    out = [{'nome': m['nome'], 'gb': m['gb']} for m in CATALOGO if ache(m['nome'])]
    out += [{'nome': n, 'gb': round(Path(c).stat().st_size / 1e9, 1)} for n, c in _proprios().items() if ache(n)]
    return out


def nomes():
    return {m['nome'] for m in instalados()}


def carregado():
    """Nome do modelo que está na memória agora, ou None."""
    return _atual['nome'] if _atual['proc'] and _atual['proc'].poll() is None else None


def amostragem(nome):
    achado = ache(nome)
    return {**AMOSTRA_PADRAO, **(achado[0].get('amostragem') or {})} if achado else dict(AMOSTRA_PADRAO)


def _binario():
    cuda = RAIZ / 'ferramentas' / 'llama' / 'cuda' / 'llama-server.exe'
    cpu = RAIZ / 'ferramentas' / 'llama' / 'cpu' / 'llama-server.exe'
    return cuda if placa() and cuda.is_file() else cpu


def versao():
    try:
        r = subprocess.run([str(_binario()), '--version'], capture_output=True, text=True, timeout=10, creationflags=SEM_JANELA)
        return (r.stdout + r.stderr).strip().split('\n')[0].replace('version: ', '')
    except Exception:      # noqa: BLE001
        return ''


def _porta_livre():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _mata_anterior():
    """Um motor que sobrou de um app fechado à força segura a placa (vários GB): encerra antes de subir outro."""
    try:
        pid = int(PID.read_text())
    except (OSError, ValueError):
        return
    r = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'], capture_output=True, text=True, creationflags=SEM_JANELA)
    if 'llama-server' in r.stdout:
        subprocess.run(['taskkill', '/pid', str(pid), '/T', '/F'], capture_output=True, creationflags=SEM_JANELA)
    PID.unlink(missing_ok=True)


def para():
    proc = _atual['proc']
    if proc and proc.poll() is None:
        subprocess.run(['taskkill', '/pid', str(proc.pid), '/T', '/F'], capture_output=True, creationflags=SEM_JANELA)
        proc.wait(timeout=20)
    _atual.update(nome=None, proc=None, porta=None)
    PID.unlink(missing_ok=True)


atexit.register(para)


def _espera(proc, porta, limite=900):
    fim = time.time() + limite
    while time.time() < fim:
        if proc.poll() is not None:
            raise RuntimeError(f'o motor parou ao carregar o modelo (código {proc.returncode}); veja app/dados/motor.log')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{porta}/health', timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:      # noqa: BLE001  (503 enquanto carrega)
            pass
        time.sleep(0.5)
    para()
    raise RuntimeError('o motor não carregou o modelo a tempo')


def sobe(nome):
    """Garante que o modelo está carregado e devolve a porta do servidor dele. Se outro modelo estiver carregado, ele sai."""
    with TRAVA:
        if _atual['nome'] == nome and _atual['proc'].poll() is None:
            return _atual['porta']
        para()
        achado = ache(nome)
        if not achado:
            raise RuntimeError(f'o modelo {nome} não está instalado (tela Modelos)')
        m, arq, mm = achado
        _mata_anterior()
        porta = _porta_livre()
        cmd = [str(_binario()), '-m', str(arq), '--host', '127.0.0.1', '--port', str(porta), '-c', str(CTX * PARALELO), '-np', str(PARALELO),
               '--jinja', '--no-ui']
        if m.get('conversa'):      # o formato de conversa que o modelo foi medido com (quando o do GGUF não serve)
            cmd += ['--chat-template-file', str(AQUI / 'conversas' / m['conversa'])]
        if mm:
            cmd += ['--mmproj', str(mm)]
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, 'a', encoding='utf-8') as log:
            log.write(f'\n== {nome}\n')
            log.flush()
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=SEM_JANELA)
        PID.write_text(str(proc.pid), encoding='utf-8')
        _atual.update(nome=nome, proc=proc, porta=porta)
        try:
            _espera(proc, porta)
        except Exception:
            para()
            raise
        return porta
