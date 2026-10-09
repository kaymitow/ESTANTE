"""Rotas de Configurações: preferências, rede opcional (consulta, outras edições, registro), sistema e cópia de segurança."""
import json, shutil, subprocess, sys, tempfile, time, zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

import config
import rede

router = APIRouter()
RAIZ = Path(__file__).resolve().parent.parent


def _publica(c):
    """A configuração como a tela vê: a chave do modelo de fora nunca volta, só se existe."""
    c = {**c, 'rede': {**c['rede'], 'fora_chave': '', 'tem_chave': bool(c['rede']['fora_chave'])}}
    return c


@router.get('/api/config')
def le_config():
    return _publica(config.le())


class Parcial(BaseModel):
    rede: dict | None = None
    processo: dict | None = None


class Download(BaseModel):
    url: str
    titulo: str = ''
    autor: str = ''


@router.put('/api/config')
def grava_config(p: Parcial):
    r = dict(p.rede or {})
    if r.get('fora_chave') == '':
        r.pop('fora_chave')                     # campo vazio = manter a chave que já está guardada
    permitidas = set(config.PADRAO['rede'])
    return _publica(config.grava({'rede': {k: v for k, v in r.items() if k in permitidas},
                                  'processo': {k: bool(v) for k, v in (p.processo or {}).items() if k in config.PADRAO['processo']}}))


@router.get('/api/rede/registro')
def registro():
    return rede.registro()


@router.get('/api/rede/consulta')
def consulta(termo: str, idioma: str = 'en'):
    try:
        return rede.consulta(termo, idioma)
    except rede.Desligado as ex:
        raise HTTPException(403, str(ex))


@router.get('/api/rede/edicoes')
def edicoes(titulo: str, autor: str = ''):
    try:
        return rede.edicoes(titulo, autor)
    except rede.Desligado as ex:
        raise HTTPException(403, str(ex))


@router.get('/api/rede/acervos')
def acervos(q: str):
    try:
        return rede.acervos(q)
    except rede.Desligado as ex:
        raise HTTPException(403, str(ex))


@router.get('/api/rede/arquivos')
def arquivos(id: str):
    try:
        return rede.arquivos(id)
    except rede.Desligado as ex:
        raise HTTPException(403, str(ex))
    except (OSError, ValueError, KeyError):
        raise HTTPException(502, 'o acervo não respondeu')


@router.post('/api/rede/baixar')
def baixar(d: Download):
    """Baixa para livros/ como arquivo solto, com nome "Título (Autor)" para a importação já preencher os campos."""
    try:
        f = rede.baixa(d.url, f'{d.titulo} ({d.autor})' if d.autor else d.titulo)
    except rede.Desligado as ex:
        raise HTTPException(403, str(ex))
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    except OSError:
        raise HTTPException(502, 'o acervo não respondeu ou o download foi interrompido')
    return {'arquivo': f.name, 'kb': round(f.stat().st_size / 1024)}


def _versao(cmd, arg='--version'):
    exe = shutil.which(cmd)
    if not exe:
        return None
    try:
        r = subprocess.run([exe, arg], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)
        return next((l.strip() for l in (r.stdout + r.stderr).split('\n') if l.strip() and 'major issue' not in l), 'instalado')[:80]
    except Exception:      # noqa: BLE001
        return 'instalado'


@router.get('/api/sistema')
def sistema():
    import motor
    disco = shutil.disk_usage(RAIZ)
    return {'python': sys.version.split()[0], 'pasta': str(RAIZ), 'biblioteca': str(RAIZ / 'livros'), 'placa': motor.placa(),
            'disco_livre_gb': round(disco.free / 1e9, 1),
            'componentes': [{'nome': n, 'para': para, 'versao': _versao(cmd)} for n, cmd, para in (
                ('Git', 'git', 'histórico de cada mudança'), ('Pandoc', 'pandoc', 'EPUB, Word e demais formatos'), ('Motor de IA (llama.cpp)', str(motor._binario()), 'modelos de IA locais'),
                ('XeLaTeX (MiKTeX)', 'xelatex', 'PDF'), ('Tectonic', shutil.which('tectonic') or str(RAIZ / 'ferramentas/bin/tectonic.exe'), 'PDF, quando não há MiKTeX'), ('Tesseract', 'tesseract', 'OCR clássico'), ('Calibre', 'ebook-convert', 'AZW3'))]}


MEDICOES = RAIZ / 'app/dados/medicoes.json'


def _medicoes():
    return json.loads(MEDICOES.read_text(encoding='utf-8')) if MEDICOES.exists() else []


@router.get('/api/medicoes')
def medicoes():
    """O último resultado do teste de erros plantados, guardado só neste computador."""
    lista = _medicoes()
    return {'ultima': lista[-1] if lista else None}


@router.post('/api/medicoes')
def medir_agora():
    """Roda o teste só com as checagens automáticas: instantâneo, não usa a placa. Com auditor e juiz, a linha de comando (app/medir.py)."""
    import medir
    m = medir.mede()
    MEDICOES.write_text(json.dumps(_medicoes() + [m], ensure_ascii=False, indent=1), encoding='utf-8')
    return {'ultima': m}


@router.get('/api/backup')
def backup():
    """Cópia de segurança da biblioteca inteira (textos, fontes, histórico), num .zip. Arquivos gerados (saida/) ficam de fora: dá para gerar de novo."""
    livros = RAIZ / 'livros'
    fd, nome = tempfile.mkstemp(suffix='.zip')
    __import__('os').close(fd)          # com o descritor aberto, o Windows não deixa apagar o arquivo depois do envio
    tmp = Path(nome)
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in livros.rglob('*'):
            if f.is_file() and 'saida' not in f.relative_to(livros).parts[1:2]:
                z.write(f, f.relative_to(livros.parent))
    return FileResponse(tmp, filename=f"estante-biblioteca-{time.strftime('%Y-%m-%d')}.zip", background=BackgroundTask(tmp.unlink))
