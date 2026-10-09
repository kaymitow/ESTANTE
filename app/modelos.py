"""Modelos de IA: catálogo, o que está instalado, baixar, remover, trazer um modelo próprio e dizer quem faz o quê.

Os modelos são arquivos GGUF numa pasta do usuário (motor.PASTA); o motor (llama.cpp) é que os carrega. Nada é baixado sem um clique do usuário,
e só o que está em modelos.json pode ser baixado (do Hugging Face, com SHA-256 conferido).
Papéis (gravados em app/dados/config.json):
  tradutor  propõe as traduções            geral    propõe nas outras tarefas (português antigo, limpeza)
  auditor   confere a fidelidade           leitor / leitor2   leem a página escaneada, um sem ver a leitura do outro
"""
import hashlib, re, threading, urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config
import duplo
import motor

router = APIRouter()
PAPEIS = ('tradutor', 'geral', 'auditor', 'juiz', 'votante', 'leitor', 'leitor2')
BAIXANDO: dict[str, dict] = {}        # nome -> {estado, feito, total, erro}


def _do_catalogo(nome):
    return next((c for c in motor.CATALOGO if c['nome'] == nome), None)


@router.get('/api/catalogo')
def catalogo():
    inst = motor.instalados()
    nomes = {m['nome'] for m in inst}
    placa = motor.placa()
    cat = [dict(m, instalado=m['nome'] in nomes, cabe=None if not placa else m['gb'] * 1.15 <= placa['gb'])      # folga para o contexto
           for m in motor.CATALOGO]
    c = config.le()
    papeis = c['papeis']
    em_uso = {p: (papeis.get(p) or duplo.padrao(p, nomes)) for p in PAPEIS}
    erro = '' if motor._binario().is_file() else 'o motor de IA (llama.cpp) não está em ferramentas/llama; rode o preparo do programa'
    return {'catalogo': cat, 'instalados': inst, 'papeis': papeis, 'em_uso': em_uso, 'placa': placa, 'baixando': BAIXANDO, 'erro': erro,
            'pasta': str(motor.PASTA), 'proprios': c.get('modelos_proprios') or {}, 'carregado': motor.carregado(),
            'fora': c['rede']['fora_modelo'] if c['rede']['modelo_fora'] and c['rede']['fora_url'] else ''}


class Nome(BaseModel):
    nome: str


def _baixa_arquivo(repo, remoto, destino, sha, st, rotulo):
    """Baixa um arquivo do Hugging Face para destino. Retoma se já houver um pedaço (.part); só vira o arquivo final se o SHA-256 conferir."""
    if destino.exists():
        return
    part = destino.with_name(destino.name + '.part')
    ja = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(f'https://huggingface.co/{repo}/resolve/main/{remoto}', headers={'Range': f'bytes={ja}-'} if ja else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        if ja and r.status != 206:      # o servidor ignorou o pedido de retomada: começa de novo
            ja = 0
        st.update(estado=f'baixando o {rotulo}', feito=ja, total=ja + int(r.headers.get('Content-Length') or 0))
        with open(part, 'ab' if ja else 'wb') as f:
            while bloco := r.read(1 << 20):
                f.write(bloco)
                st['feito'] += len(bloco)
    st['estado'] = f'conferindo o {rotulo}'
    h = hashlib.sha256()
    with open(part, 'rb') as f:
        for bloco in iter(lambda: f.read(1 << 20), b''):
            h.update(bloco)
    if h.hexdigest() != sha:
        part.unlink(missing_ok=True)
        raise RuntimeError(f'o {rotulo} baixado não confere (SHA-256 diferente); tente de novo')
    part.replace(destino)


def _puxa(nome):
    st = BAIXANDO[nome]
    m = _do_catalogo(nome)
    try:
        motor.PASTA.mkdir(parents=True, exist_ok=True)
        _baixa_arquivo(m['repo'], m['remoto'], motor.PASTA / m['arquivo'], m['sha256'], st, 'modelo')
        if m.get('mmproj'):
            mm = m['mmproj']
            _baixa_arquivo(m['repo'], mm['remoto'], motor.PASTA / mm['arquivo'], mm['sha256'], st, 'projetor de imagem')
        st['estado'] = 'pronto'
    except Exception as ex:      # noqa: BLE001
        st.update(estado='erro', erro=str(ex))


@router.post('/api/modelos/baixar')
def baixar(n: Nome):
    nome = n.nome.strip()
    if not _do_catalogo(nome):
        raise HTTPException(400, 'este modelo não está no catálogo do Estante')
    if BAIXANDO.get(nome, {}).get('estado') not in (None, 'pronto', 'erro'):
        return BAIXANDO[nome]
    BAIXANDO[nome] = {'estado': 'começando', 'feito': 0, 'total': 0, 'erro': ''}
    threading.Thread(target=_puxa, args=(nome,), daemon=True).start()
    return BAIXANDO[nome]


class Proprio(BaseModel):
    nome: str
    caminho: str        # arquivo .gguf no computador


@router.post('/api/modelos/proprio')
def proprio(p: Proprio):
    """Aponta para um arquivo GGUF que o usuário já tem. O arquivo fica onde está; o app só guarda o caminho."""
    arq = Path(p.caminho.strip().strip('"'))
    if not re.fullmatch(r'[\w.\-:]{2,80}', p.nome) or arq.suffix.lower() != '.gguf' or not arq.is_file():
        raise HTTPException(400, 'informe um nome simples e o caminho de um arquivo .gguf que exista')
    if _do_catalogo(p.nome):
        raise HTTPException(400, 'esse nome já é de um modelo do catálogo')
    config.grava({'modelos_proprios': {**(config.le().get('modelos_proprios') or {}), p.nome: str(arq)}})
    # um GGUF sem o formato de conversa embutido responde com as marcas cruas (visto no teste com arquivo real):
    # melhor avisar aqui do que deixar o usuário descobrir numa tradução
    aviso = ''
    try:
        resposta = duplo.chat(p.nome, [{'role': 'user', 'content': 'Responda só: ok'}], num_predict=12)
        if not resposta or '<|' in resposta:
            aviso = ('O modelo foi registrado, mas respondeu ao teste com marcas cruas ou em branco: o arquivo não traz o formato de conversa. '
                     'Ele pode não servir para traduzir nem para conferir.')
    except Exception as ex:      # noqa: BLE001
        aviso = f'O modelo foi registrado, mas não respondeu ao teste: {str(ex)[:200]}'
    return {'ok': True, 'aviso': aviso}


@router.post('/api/modelos/remover')
def remover(n: Nome):
    """Apaga os arquivos do catálogo (o modelo e o projetor de imagem). Um modelo próprio só sai da lista: o arquivo não é apagado."""
    if motor.carregado() == n.nome:
        motor.para()
    m = _do_catalogo(n.nome)
    proprios = dict(config.le().get('modelos_proprios') or {})
    if m is None and n.nome not in proprios:
        raise HTTPException(404, 'modelo não encontrado')
    try:
        for arq in ([m['arquivo'], m['mmproj']['arquivo']] if m and m.get('mmproj') else [m['arquivo']] if m else []):
            (motor.PASTA / arq).unlink(missing_ok=True)
    except OSError as ex:
        raise HTTPException(500, f'não foi possível remover: {ex}')
    proprios.pop(n.nome, None)
    config.grava({'modelos_proprios': proprios, 'papeis': {k: '' for k, v in config.le()['papeis'].items() if v == n.nome}})
    BAIXANDO.pop(n.nome, None)
    return {'ok': True}


class Papeis(BaseModel):
    papeis: dict[str, str]


@router.put('/api/modelos/papeis')
def define_papeis(p: Papeis):
    """Valor vazio = deixar o app escolher conforme o que está instalado."""
    return config.grava({'papeis': {k: p.papeis.get(k) or '' for k in PAPEIS}})['papeis']
