"""Rotas do fluxo de dois modelos: item único, lote (fila persistente) e leitura de página por imagem."""
import base64, re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import duplo
import fila
import pipeline

router = APIRouter()
RAIZ = Path(__file__).resolve().parent.parent
PREFIXO = re.compile(r'^(\[\d+\.\]\{\.pnum\}\s*)')      # numeração própria da fonte: fica fora do que vai ao modelo


def pasta_livro(nome):
    p = (RAIZ / 'livros' / nome).resolve()
    if p.parent != (RAIZ / 'livros').resolve() or not (p / 'texto' / 'livro.md').exists():
        raise HTTPException(404, 'livro não encontrado')
    return p


class Item(BaseModel):
    tarefa: str
    texto: str
    a: str = ''          # vazio = o modelo definido na tela Modelos para a tarefa
    b: str = ''


@router.post('/api/duplo')
def um_item(p: Item):
    if p.tarefa not in duplo.PROMPTS or p.tarefa == 'ler_pagina':
        raise HTTPException(400, 'tarefa inválida')
    a, b = duplo.escolhe(p.tarefa)
    return duplo.processa(p.tarefa, p.texto, p.a or a, p.b or b)


class PedidoLote(BaseModel):
    livro: str
    tarefa: str
    linhas: list[int]                 # índices de linha do livro.md
    a: str = ''          # vazio = o modelo definido na tela Modelos para a tarefa
    b: str = ''


@router.post('/api/lote')
def novo_lote(p: PedidoLote):
    if p.tarefa not in duplo.PROMPTS or p.tarefa == 'ler_pagina':
        raise HTTPException(400, 'tarefa inválida')
    md = pasta_livro(p.livro) / 'texto' / 'livro.md'
    linhas = md.read_text(encoding='utf-8').split('\n')
    itens = []
    for i in p.linhas:
        if not 0 <= i < len(linhas):
            continue
        raw = linhas[i]
        m = PREFIXO.match(raw)
        itens.append({'i': i, 'raw': raw, 'prefixo': m[1] if m else '', 'fonte': raw[len(m[1]):] if m else raw})
    if not itens:
        raise HTTPException(400, 'nenhuma linha válida')
    a, b = duplo.escolhe(p.tarefa)
    return {'id': fila.criar(p.livro, p.tarefa, itens, p.a or a, p.b or b), 'total': len(itens)}


@router.get('/api/lotes')
def lotes():
    """Trabalhos recentes (para a tela reencontrar um lote depois de fechar ou reiniciar)."""
    return fila.listar()


@router.get('/api/lote/{lid}')
def estado_lote(lid: str):
    e = fila.estado(lid)
    if not e:
        raise HTTPException(404)
    return e


@router.post('/api/lote/{lid}/parar')
def parar_lote(lid: str):
    fila.parar(lid)
    return {'ok': True}


@router.post('/api/lote/{lid}/pausar')
def pausar_lote(lid: str, continuar: bool = False):
    fila.pausar(lid, not continuar)
    return {'ok': True}


class Aceite(BaseModel):
    novo: str


@router.post('/api/lote/{lid}/aceito/{k}')
def aceito(lid: str, k: int, a: Aceite):
    """Registra na fila que o item foi aceito (a gravação no livro é feita por /api/editar)."""
    fila.marcar_aceito(lid, k, a.novo)
    return {'ok': True}


class PedidoOCR(BaseModel):
    livro: str
    scan: int
    a: str = ''          # vazio = o modelo definido na tela Modelos para a tarefa
    b: str = ''


@router.post('/api/ocr')
def ler_pagina(p: PedidoOCR):
    import pymupdf
    pdf = next((pasta_livro(p.livro) / 'fonte').glob('*.pdf'), None)
    if not pdf:
        raise HTTPException(404, 'sem PDF em fonte/')
    doc = pymupdf.open(str(pdf))
    if not 1 <= p.scan <= len(doc):
        raise HTTPException(400, f'página fora do intervalo (1–{len(doc)})')
    img = base64.b64encode(doc[p.scan - 1].get_pixmap(dpi=130).tobytes('jpeg', jpg_quality=80)).decode()
    a, b = duplo.escolhe('ler_pagina')
    r = duplo.processa('ler_pagina', '', p.a or a, p.b or b, imagem_b64=img)
    r['imagem'] = 'data:image/jpeg;base64,' + img
    return r


# ---------- pipeline do livro novo ----------
class ConfigPipeline(BaseModel):
    tarefa: str | None = None            # traduzir | traduzir_de | atualizar_pt | limpar_ocr | nenhuma
    paginas: list[int] | None = None     # [primeira, última] para processar só um trecho
    a: str | None = None
    b: str | None = None
    idioma: str | None = None
    rapido: bool | None = None           # rascunho rápido: motor clássico na CPU, sem auditor nem juiz
    ler_por_imagem: bool | None = None   # PDF de scan com texto por cima: True relê as páginas; False usa o texto do arquivo


@router.get('/api/pipeline/{livro}')
def pipeline_estado(livro: str):
    try:
        return pipeline.estado(livro)
    except FileNotFoundError:
        raise HTTPException(404, 'livro não encontrado')


@router.post('/api/pipeline/{livro}/iniciar')
def pipeline_iniciar(livro: str, c: ConfigPipeline):
    try:
        return pipeline.iniciar(livro, c.model_dump())
    except FileNotFoundError:
        raise HTTPException(404, 'livro não encontrado')
    except ValueError as ex:
        raise HTTPException(400, str(ex))


@router.post('/api/pipeline/{livro}/pausar')
def pipeline_pausar(livro: str):
    return pipeline.pausar(livro)


@router.get('/api/pipeline/{livro}/rascunho')
def pipeline_rascunho(livro: str):
    f = pipeline.pasta(livro) / 'revisao' / 'dados' / 'rascunho.json'
    if not f.exists():
        raise HTTPException(404, 'ainda não há rascunho')
    d = __import__('json').loads(f.read_text(encoding='utf-8'))
    for b in d['blocos']:          # leitura crítica: calculada na hora (não é gravada), a partir do original de cada bloco
        n, tr = duplo.risco(b.get('fonte') or '')
        b['risco'], b['trechos_risco'] = n, [list(t) for t in tr]
    return d
