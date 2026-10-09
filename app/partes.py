"""Partes para uma IA grande: os trechos que o app não tem certeza, com o original e a tradução atual, para copiar ou salvar.

O app não envia nada para fora: a pessoa copia o texto e cola numa IA grande por conta própria, e depois cola a resposta de volta
no lugar do trecho. Entram os blocos que pediam atenção e os que o juiz corrigiu, que ainda não foram aceitos.
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

import pipeline

router = APIRouter()
RAIZ = Path(__file__).resolve().parent.parent


def monta_partes(p: Path) -> tuple[str, int]:
    """Texto em português com as partes e a quantidade de partes."""
    r = pipeline._le(p / 'revisao' / 'dados' / 'rascunho.json') or {'blocos': []}
    try:
        titulo = json.loads((p / 'fonte' / 'dados' / 'source.json').read_text(encoding='utf-8')).get('title') or p.name
    except (OSError, ValueError):
        titulo = p.name
    partes = [b for b in r['blocos'] if not b.get('aceito') and b.get('status') in ('revisar', 'juiz')]
    out = [f'# Trechos para revisar: {titulo}', '',
           'Trechos que o app não tem certeza. Traduza de novo com uma IA grande, mantendo o sentido do original, os nomes e a '
           'ordem das frases. Depois cole a resposta no lugar de cada trecho.', '']
    for k, b in enumerate(partes, 1):
        pags = ', '.join(str(x) for x in b.get('paginas') or []) or '?'
        motivo = '; '.join(b.get('problemas') or []) or ('corrigido pelo juiz' if b.get('status') == 'juiz' else 'pede atenção')
        if b.get('status') == 'juiz' and b.get('problemas'):
            motivo = 'corrigido pelo juiz; ' + motivo
        out += [f'## {k}. Bloco {b["id"]} (páginas {pags})', '', f'Motivo: {motivo}', '',
                'Original:', '', *[f'> {ln}' for ln in (b.get("fonte") or "").split("\n")], '',
                'Tradução atual:', '', b.get('texto') or b.get('resultado') or '', '']
    if not partes:
        out.append('Nenhum trecho pede atenção. O livro está pronto.')
    return '\n'.join(out), len(partes)


def _pasta(livro: str) -> Path:
    p = RAIZ / 'livros' / livro
    if not (p / 'revisao' / 'dados' / 'rascunho.json').exists():
        raise HTTPException(404, 'este livro ainda não tem rascunho')
    return p


@router.get('/api/livro/{livro}/partes')
def partes(livro: str):
    texto, n = monta_partes(_pasta(livro))
    return {'texto': texto, 'n': n}


@router.post('/api/livro/{livro}/partes/salvar')
def salvar_partes(livro: str):
    p = _pasta(livro)
    texto, n = monta_partes(p)
    (p / 'saida').mkdir(exist_ok=True)
    (p / 'saida' / 'partes-para-revisar.md').write_text(texto, encoding='utf-8', newline='\n')
    return {'arquivo': 'partes-para-revisar.md', 'n': n}
