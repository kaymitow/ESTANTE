"""Monta desktop/pacote/: o que vai dentro do instalador do Estante (Python embutido, dependências, código do app, Pandoc, Tectonic e o motor de IA).

    python desktop/preparar_pacote.py      (usa o .venv do projeto para instalar as dependências no Python embutido)

Layout dentro do pacote (vira resources/ depois de instalado):
    python/            Python 3.12 embutível + dependências em Lib/site-packages
    app/               código do app (servidor, telas compiladas em static/novo, modelos.json, conversas/)
    ferramentas/       construir.py, filtros, estilo, dicionário de grafia, motor clássico,
                       llama/cuda e llama/cpu (llama.cpp: llama-server), bin/ (pandoc.exe, tectonic.exe)
Os modelos de IA e os livros não entram: os modelos baixam na primeira abertura (Hugging Face, com SHA-256 conferido), e os livros são criados pelo uso.
"""
import hashlib, shutil, subprocess, sys, urllib.request, zipfile
from pathlib import Path

DESKTOP = Path(__file__).resolve().parent
RAIZ = DESKTOP.parent
CACHE = DESKTOP / 'cache'
PACOTE = DESKTOP / 'pacote'
VENV_PY = RAIZ / '.venv' / 'Scripts' / 'python.exe'

# dependências que o app usa de fato (o freeze do .venv tem sobras de testes com PyInstaller e pywebview)
SOBRAS = {'pip', 'setuptools', 'altgraph', 'pefile', 'pyinstaller-hooks-contrib', 'bottle', 'proxy_tools', 'pythonnet', 'clr_loader', 'pywin32-ctypes'}

sys.path.insert(0, str(RAIZ / 'app'))
from motor import LLAMA, LLAMA_URL      # noqa: E402  (uma lista só: a mesma que o instalador baixa)

PTH = 'python312.zip\n.\n..\\app\n..\\ferramentas\nLib\\site-packages\nimport site\n'


def copia(src: Path, dst: Path, ignora=lambda n: False):
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.name == '__pycache__' or ignora(f.name):
            continue
        if f.is_dir():
            copia(f, dst / f.name, ignora)
        else:
            shutil.copy2(f, dst / f.name)


def sha_de(arq: Path) -> str:
    h = hashlib.sha256()
    with open(arq, 'rb') as f:
        for bloco in iter(lambda: f.read(1 << 20), b''):
            h.update(bloco)
    return h.hexdigest()


def garante(nome: str, sha: str) -> Path:
    """O zip do llama.cpp no cache (baixado se não estiver lá); recusa se o SHA-256 não bater."""
    CACHE.mkdir(exist_ok=True)
    alvo = CACHE / nome
    if not alvo.exists() or sha_de(alvo) != sha:
        print('baixando', nome)
        urllib.request.urlretrieve(LLAMA_URL + nome, alvo)
        if sha_de(alvo) != sha:
            alvo.unlink()
            raise SystemExit(f'{nome}: SHA-256 diferente do esperado')
    return alvo


def main():
    if PACOTE.exists():
        shutil.rmtree(PACOTE)
    py = PACOTE / 'python'
    with zipfile.ZipFile(CACHE / 'python-embed.zip') as z:
        z.extractall(py)
    (py / 'python312._pth').write_text(PTH, encoding='utf-8')

    freeze = subprocess.run([str(VENV_PY), '-m', 'pip', 'freeze'], capture_output=True, text=True, encoding='utf-8', check=True).stdout
    reqs = [l for l in freeze.splitlines() if l and l.split('==')[0].lower().replace('_', '-') not in SOBRAS]
    req_file = DESKTOP / 'requisitos-programa.txt'
    req_file.write_text('\n'.join(reqs) + '\n', encoding='utf-8')
    subprocess.run([str(VENV_PY), '-m', 'pip', 'install', '--quiet', '--no-warn-script-location', '--target', str(py / 'Lib' / 'site-packages'), '-r', str(req_file)], check=True)

    app = PACOTE / 'app'
    app.mkdir(parents=True)
    for f in (RAIZ / 'app').glob('*.py'):
        if not f.name.startswith(('regua', 'teste', 'medir_')) and not f.name.endswith('_antigo.py'):
            shutil.copy2(f, app / f.name)
    shutil.copy2(RAIZ / 'app' / 'modelos.json', app / 'modelos.json')
    shutil.copy2(RAIZ / 'app' / 'teste_publico.json', app / 'teste_publico.json')
    copia(RAIZ / 'app' / 'conversas', app / 'conversas')      # formato de conversa dos modelos que precisam do seu próprio
    copia(RAIZ / 'app' / 'static', app / 'static')
    (app / 'dados').mkdir()
    (PACOTE / 'livros').mkdir()      # a biblioteca começa vazia; o app a preenche

    fer = PACOTE / 'ferramentas'
    for nome in ('construir.py', 'bilingue.py', 'anotar.py', 'buscar.py'):
        shutil.copy2(RAIZ / 'ferramentas' / nome, fer / nome) if (fer.mkdir(exist_ok=True) or True) else None
    copia(RAIZ / 'ferramentas' / 'filtros', fer / 'filtros')
    copia(RAIZ / 'ferramentas' / 'estilo', fer / 'estilo')
    copia(RAIZ / 'ferramentas' / 'classico', fer / 'classico')
    copia(RAIZ / 'ferramentas' / 'ortografia', fer / 'ortografia', ignora=lambda n: n.endswith('.log'))
    copia(RAIZ / 'ferramentas' / 'bin', fer / 'bin')
    with zipfile.ZipFile(CACHE / 'pandoc.zip') as z:
        pandoc = next(n for n in z.namelist() if n.endswith('/pandoc.exe') or n == 'pandoc.exe')
        (fer / 'bin').mkdir(exist_ok=True)
        (fer / 'bin' / 'pandoc.exe').write_bytes(z.read(pandoc))
    for nome, sha, pasta in LLAMA:
        with zipfile.ZipFile(garante(nome, sha)) as z:
            z.extractall(fer / 'llama' / pasta)

    tamanho = sum(f.stat().st_size for f in PACOTE.rglob('*') if f.is_file()) / 1e6
    print(f'pacote pronto em {PACOTE} ({tamanho:.0f} MB, {len(reqs)} dependências)')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
