"""Gera src/lib/fontes.css: as fontes extras que o usuário pode escolher em Configurações → Aparência.

    python gera_fontes.py        (dentro de app/ui, depois de npm install)

Pega dos pacotes @fontsource só os recortes latin e latin-ext (português e línguas europeias), para o app não carregar
dezenas de arquivos que nunca usa. As fontes vão embutidas no app: nada é buscado na internet. Para acrescentar uma fonte:
npm install do pacote, uma linha em PACOTES, rodar este script e pôr a opção em src/lib/aparencia.js.
"""
import re
from pathlib import Path

AQUI = Path(__file__).resolve().parent
# pacote -> arquivos CSS dele que interessam
PACOTES = {
    '@fontsource-variable/playfair-display': ['wght.css', 'wght-italic.css'],
    '@fontsource-variable/cormorant': ['wght.css', 'wght-italic.css'],
    '@fontsource-variable/space-grotesk': ['wght.css'],
    '@fontsource-variable/eb-garamond': ['wght.css', 'wght-italic.css'],
    '@fontsource-variable/lora': ['wght.css', 'wght-italic.css'],
    '@fontsource-variable/ibm-plex-sans': ['wght.css'],
    '@fontsource/atkinson-hyperlegible': ['latin-400.css', 'latin-ext-400.css', 'latin-700.css', 'latin-ext-700.css', 'latin-400-italic.css', 'latin-ext-400-italic.css'],
}
saida, n = ['/* Gerado por gera_fontes.py: não editar à mão. */'], 0
for pacote, arquivos in PACOTES.items():
    for arq in arquivos:
        css = (AQUI / 'node_modules' / pacote / arq).read_text(encoding='utf-8')
        for nome, bloco in re.findall(r'/\* ([\w-]+) \*/\s*(@font-face \{.*?\})', css, re.S):
            if not re.search(r'-latin(-ext)?-', nome):
                continue
            bloco = re.sub(r",\s*url\([^)]*\.woff\)\s*format\('woff'\)", '', bloco)               # só woff2
            bloco = bloco.replace('url(./files/', f'url(../../node_modules/{pacote}/files/')
            saida.append(bloco); n += 1
(AQUI / 'src' / 'lib' / 'fontes.css').write_text('\n'.join(saida) + '\n', encoding='utf-8', newline='\n')
print(n, 'recortes de fonte em src/lib/fontes.css')
