"""Roda todos os testes que não precisam dos modelos de IA. Um comando, um veredito.

    python app/testes.py

Autotestes dos módulos (montagem do livro, marcas de link, checagens, grafia, configuração), entrada por EPUB quando há
um EPUB solto em livros/, e o aceite na revisão quando o servidor está no ar. Testes que usam os livros desta biblioteca
ou a placa (régua, régua de erros com auditor, pipeline de ponta a ponta) ficam à parte.
"""
import os, subprocess, sys, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
RAIZ = Path(__file__).resolve().parent.parent
PORTA = os.environ.get('ESTANTE_PORTA', '8765')
casos = [('configuração', ['app/config.py']), ('marcas, checagens e estrutura', ['app/pipeline.py']), ('montagem do livro no aceite', ['app/revisao.py']),
         ('grafia do português antigo', ['ferramentas/ortografia/regras.py']), ('notas e links de EPUB', ['app/epub.py']), ('de onde o app aceita baixar', ['app/rede.py']), ('comparação com outra cópia', ['app/copias.py']), ('título em português', ['app/extras.py']), ('fila de livros (modo lote)', ['app/fila_livros.py'])]
casos += [(f'entrada por EPUB (livro {i})', ['app/teste_epub.py', str(e)]) for i, e in enumerate(sorted((RAIZ / 'livros').glob('*.epub'))[:2], 1)]
if (RAIZ / 'app' / 'regua_erros.py').exists():          # só existe onde há a biblioteca de referência
    casos.append(('erros injetados × checagens automáticas', ['app/regua_erros.py', '--rotulo', 'teste']))
try:
    urllib.request.urlopen(f'http://127.0.0.1:{PORTA}/api/livros', timeout=3)
    casos.append(('aceite na revisão (servidor)', ['app/teste_revisao.py']))
except OSError:
    print('servidor fora do ar: o teste do aceite foi pulado')

falhas = 0
for nome, cmd in casos:
    r = subprocess.run([sys.executable] + cmd, cwd=RAIZ, capture_output=True, text=True, encoding='utf-8', errors='replace', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    ok = r.returncode == 0
    falhas += not ok
    print(f"{'ok    ' if ok else 'FALHOU'} {nome}")
    if not ok:
        print('       ' + (r.stderr or r.stdout).strip().replace('\n', '\n       ')[-600:])
print(f'\n{len(casos) - falhas} de {len(casos)} passaram')
sys.exit(1 if falhas else 0)
