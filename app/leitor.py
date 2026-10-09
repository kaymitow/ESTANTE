"""Leitor: marcações e notas de quem lê. Ficam em <livro>/leitor/marcacoes.json, fora do texto do livro (o livro.md não é tocado).

Cada marcação guarda o próprio trecho, não o número da linha (as linhas mudam a cada aceite): a tela procura o trecho no texto e,
se ele sumiu, mostra a marcação como "sem lugar" em vez de apagá-la. O texto vem de /api/livro/<id>/linhas, o mesmo da correção.
"""
import json, time

from fastapi import APIRouter, HTTPException, Request

from extras import commit, pasta_livro

router = APIRouter()
CAMPOS = {'id': 40, 'trecho': 4000, 'nota': 4000, 'cor': 12, 'origem': 200, 'quando': 30}      # campo -> tamanho máximo
_ultimo = {}      # livro -> hora do último commit (é dado de leitura, não texto do livro: no máximo um commit por minuto)


def _arq(nome):
    return pasta_livro(nome) / 'leitor' / 'marcacoes.json'


@router.get('/api/leitor/{nome}/marcacoes')
def marcacoes(nome: str):
    f = _arq(nome)
    return json.loads(f.read_text(encoding='utf-8')) if f.exists() else []


@router.put('/api/leitor/{nome}/marcacoes')
async def grava(nome: str, req: Request):
    """Guarda a lista inteira de marcações. Só os campos conhecidos entram, com tamanho limitado."""
    lista = await req.json()
    if not isinstance(lista, list) or len(lista) > 5000:
        raise HTTPException(400, 'lista de marcações inválida')
    limpa = []
    for m in lista:
        if not isinstance(m, dict) or not str(m.get('trecho', '')).strip():
            raise HTTPException(400, 'marcação sem trecho')
        limpa.append({**{k: str(m.get(k, ''))[:n] for k, n in CAMPOS.items()}, 'i': int(m.get('i') or 0)})
    f = _arq(nome)
    f.parent.mkdir(exist_ok=True)
    f.write_text(json.dumps(limpa, ensure_ascii=False, indent=1), encoding='utf-8')
    if time.time() - _ultimo.get(nome, 0) > 60:
        _ultimo[nome] = time.time()
        commit(f'Marcações de leitura em {nome}', f)
    return limpa


if __name__ == '__main__':
    assert set(CAMPOS) == {'id', 'trecho', 'nota', 'cor', 'origem', 'quando'}
    print('ok')
