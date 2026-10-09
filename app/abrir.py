"""Abre o Estante sem janela de terminal: sobe o servidor escondido, espera ele responder e abre a tela. Fechar a tela encerra o servidor.

    .venv\\Scripts\\pythonw.exe app\\abrir.py        (é o que o atalho da área de trabalho e o iniciar-app.bat chamam)

Com o Edge (vem no Windows), a tela é uma janela própria, com o ícone do app na barra de tarefas. Sem ele, abre no navegador padrão
e o servidor fica no ar até o computador desligar.
"""
import ctypes, os, subprocess, sys, time, urllib.request, webbrowser, winreg
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
PORTA = os.environ.get('ESTANTE_PORTA', '8765')
URL = f'http://127.0.0.1:{PORTA}/'
SEM_JANELA = subprocess.CREATE_NO_WINDOW


def no_ar():
    try:
        urllib.request.urlopen(URL + 'api/livros', timeout=2)
        return True
    except OSError:
        return False


def edge():
    for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            exe = winreg.QueryValue(raiz, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe')
            if Path(exe).is_file():
                return exe
        except OSError:
            pass
    return None


def avisa(texto):
    ctypes.windll.user32.MessageBoxW(0, texto, 'Estante', 0x10)


def main():
    servidor = None
    if not no_ar():
        (AQUI / 'dados').mkdir(exist_ok=True)
        log = open(AQUI / 'dados' / 'estante.log', 'a', encoding='utf-8')
        # python.exe com console escondido (e não pythonw): os programas que o app chama (pandoc, git, llama) herdam o console e não piscam janelas
        servidor = subprocess.Popen([str(Path(sys.executable).with_name('python.exe')), str(AQUI / 'servidor.py')], cwd=RAIZ, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, creationflags=SEM_JANELA, env={**os.environ, 'PYTHONUTF8': '1'})
        fim = time.time() + 90
        while not no_ar():
            if servidor.poll() is not None or time.time() > fim:
                servidor.kill()
                return avisa('O Estante não conseguiu iniciar. O motivo está em app\\dados\\estante.log.\n\nSe acabou de baixar o programa, rode o instalar.bat.')
            time.sleep(0.3)
    exe = edge()
    if not exe:
        webbrowser.open(URL)
        return
    # perfil próprio: sem ele o Edge entrega a janela ao navegador já aberto e este processo sai na hora, sem dar para saber quando a tela fechou
    janela = subprocess.Popen([exe, f'--app={URL}', f'--user-data-dir={AQUI / "dados" / "janela"}', '--no-first-run', '--no-default-browser-check'])
    janela.wait()
    if servidor:      # só quem subiu o servidor o encerra (a segunda abertura só traz outra janela); /T leva junto o motor de IA
        subprocess.run(['taskkill', '/pid', str(servidor.pid), '/T', '/F'], capture_output=True, creationflags=SEM_JANELA)


if __name__ == '__main__':
    main()
