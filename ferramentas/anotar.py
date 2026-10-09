"""Edição ANOTADA: junta comentários do editor ao livro SEM tocar no texto do autor.

O livro.md continua intacto. Os comentários ficam em livros/<livro>/texto/anotacoes.md e só entram
numa edição à parte (saída "<livro>-anotada.pdf/.epub"), em caixa separada, sempre rotulados
"Nota do editor". A edição de leitura normal nunca recebe comentários.

Formato de anotacoes.md (tudo antes do primeiro "## " é ignorado; use para lembretes):

    ## par:114
    Texto do comentário (pode ter vários parágrafos).

    ## inicia:O sistema crediário dos bancos é hoje orga-
    Comentário do parágrafo que COMEÇA com esse trecho (como está no livro.md, sem a marca [n.]).

- par:N       -> parágrafo numerado [N.] (texto com parágrafos numerados)
- inicia:TEXTO -> primeiro parágrafo cujo começo é TEXTO (ignora maiúsculas e acentos)
O comentário aparece logo DEPOIS do parágrafo. Âncora que não achar nada = erro (para você notar).
Uso direto:  python ferramentas/anotar.py livros/<livro>   (grava texto/.livro-anotado.md e mostra onde)
Normalmente: python ferramentas/construir.py livros/<livro> anotada
"""
import re, sys, unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')


def sem_acento(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()


def le_anotacoes(path):
    texto = path.read_text(encoding='utf-8')
    partes = re.split(r'(?m)^## (?=\S)', texto)[1:]
    out = []
    for p in partes:
        cab, _, corpo = p.partition('\n')
        out.append((cab.strip(), corpo.strip()))
    return out


def mesclar(livro):
    """Devolve o caminho de um Markdown temporário = livro.md + notas do editor."""
    texto_dir = Path(livro) / 'texto'
    notas = le_anotacoes(texto_dir / 'anotacoes.md')
    linhas = (texto_dir / 'livro.md').read_text(encoding='utf-8').split('\n')
    depois = {}                      # índice da linha -> blocos a inserir depois dela
    for cab, corpo in notas:
        achou = None
        m = re.fullmatch(r'par:(\d+)', cab)
        if m:
            marca = f'[{m[1]}.]{{.pnum}}'
            achou = next((i for i, l in enumerate(linhas) if l.startswith(marca)), None)
        elif cab.startswith('inicia:'):
            alvo = sem_acento(cab[len('inicia:'):].strip())
            for i, l in enumerate(linhas):
                if not l.strip() or l.startswith(('#', '<!--', ':::', '|', '>', '[^')):
                    continue
                base = sem_acento(re.sub(r'^\[\d+\.\]\{\.pnum\}\s*', '', re.sub(r'\\(.)', r'\1', l)))
                if base.startswith(alvo):
                    achou = i; break
        if achou is None:
            sys.exit(f'Âncora sem correspondência em livro.md: "{cab}"')
        bloco = ['', '::: anotacao', f'**Nota do editor.** {corpo}', ':::']
        depois.setdefault(achou, []).extend(bloco)
    saida = []
    for i, l in enumerate(linhas):
        saida.append(l)
        saida.extend(depois.get(i, []))
    destino = texto_dir / '.livro-anotado.md'
    destino.write_text('\n'.join(saida), encoding='utf-8', newline='\n')
    return destino


if __name__ == '__main__':
    print(mesclar(Path(sys.argv[1]).resolve()))
