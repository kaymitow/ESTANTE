"""Modo lote: uma fila de livros para processar em sequência (deixar rodando de noite, por exemplo).

Um livro por vez: o próximo só começa quando nenhum outro está sendo processado, inclusive um que o usuário tenha começado à mão
(dois juntos disputariam a placa de vídeo). Livro que dá erro fica marcado com o motivo e a fila segue; livro que para numa pergunta
(camada de texto ruim, por exemplo) fica "esperando você" e a fila também segue. Nada é aceito sozinho: no fim, cada livro está
pronto para a Revisão, como se tivesse sido processado pela tela dele.

O estado fica em app/dados/fila_livros.json e sobrevive a reinício: o pipeline retoma sozinho o livro que estava rodando
(pipeline.retomar_todos) e o laço daqui só continua a fila.

    python app/fila_livros.py      autoteste, com um pipeline de mentira
"""
import json, threading, time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
ARQ = Path(__file__).resolve().parent / 'dados' / 'fila_livros.json'
VAZIA = {'itens': [], 'ligada': False, 'inicio_em': None, 'fim_em': None, 'aviso': ''}
_trava = threading.Lock()


def le():
    try:
        return {**VAZIA, **json.loads(ARQ.read_text(encoding='utf-8'))}
    except (OSError, ValueError):
        return json.loads(json.dumps(VAZIA))


def _grava(f):
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    ARQ.write_text(json.dumps(f, ensure_ascii=False, indent=1), encoding='utf-8')


def _proxima_hora(hhmm, depois_de):
    """Próxima vez que o relógio marca HH:MM depois do instante dado (segundos desde 1970)."""
    h, m = (int(x) for x in hhmm.split(':'))
    d = datetime.fromtimestamp(depois_de)
    alvo = d.replace(hour=h, minute=m, second=0, microsecond=0)
    return (alvo if alvo > d else alvo + timedelta(days=1)).timestamp()


def passo(pipe, agora=None):
    """Um passo da fila: olha o livro que está rodando, fecha o que terminou e começa o próximo. É chamado a cada poucos segundos pelo
    laço; pipe = o módulo pipeline (ou um de mentira, no teste). Devolve a fila como ficou."""
    agora = agora or time.time()
    with _trava:
        f = le()
        vivos = {n for n, t in pipe._threads.items() if t.is_alive()}
        atual = next((i for i in f['itens'] if i['estado'] == 'rodando'), None)
        if atual and atual['livro'] not in vivos:      # terminou, parou ou foi pausado: o que o pipeline deixou escrito diz qual
            try:
                st = pipe.estado(atual['livro'])
            except Exception as ex:      # noqa: BLE001  (livro apagado no meio, por exemplo)
                st = {'estado': 'erro', 'mensagem': str(ex)}
            atual['fim'] = agora
            if st.get('estado') == 'concluido':
                atual.update(estado='pronto', motivo='')
            elif st.get('estado') == 'erro' or 'o modelo não respondeu' in (st.get('mensagem') or ''):
                atual.update(estado='parou', motivo=st.get('mensagem') or 'erro sem mensagem')
            elif st.get('pergunta') or st.get('impedimento'):
                atual.update(estado='esperando', motivo=st.get('mensagem') or st.get('impedimento') or 'o app precisa de uma resposta sua na tela do livro')
            elif st.get('estado') == 'rodando':      # o servidor acabou de subir e o pipeline ainda vai retomar este livro: não é fim
                atual.pop('fim', None)
                try:
                    pipe.iniciar(atual['livro'])
                except Exception as ex:      # noqa: BLE001
                    atual.update(estado='parou', motivo=str(ex), fim=agora)
            else:      # pausado à mão na tela do livro: a fila respeita e para junto
                atual.update(estado='na fila', motivo='')
                f.update(ligada=False, aviso='A fila parou porque você pausou o livro que estava rodando. Ligue de novo para continuar.')
            atual = next((i for i in f['itens'] if i['estado'] == 'rodando'), None)
        if f['ligada'] and f['fim_em'] and agora >= f['fim_em']:      # hora de parar: pausa o livro (dá para retomar) e desliga a fila
            if atual:
                pipe.pausar(atual['livro'])
                atual.update(estado='na fila', motivo='')
            f.update(ligada=False, fim_em=None, inicio_em=None, aviso='A fila parou no horário marcado. Ligue de novo para continuar de onde parou.')
        elif f['ligada'] and not atual and not vivos and agora >= (f['inicio_em'] or 0):
            prox = next((i for i in f['itens'] if i['estado'] == 'na fila'), None)
            if not prox:
                f.update(ligada=False, inicio_em=None, fim_em=None, aviso='A fila terminou.')
            else:
                try:
                    pipe.iniciar(prox['livro'], prox.get('config') or None)
                    prox.update(estado='rodando', inicio=agora, motivo='')
                except Exception as ex:      # noqa: BLE001  (sem arquivo de origem, livro já com texto aprovado…): marca e segue
                    prox.update(estado='parou', motivo=str(ex), fim=agora)
        _grava(f)
        return f


def _acordado(sim):
    """Windows: enquanto um livro é processado o computador não dorme sozinho; depois volta ao plano de energia dele. A chamada vale
    para a thread que a faz, por isso sai sempre do laço da fila (que vive enquanto o app vive), nunca de uma rota."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (0x00000001 if sim else 0))      # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    except (AttributeError, OSError):      # fora do Windows
        pass


def iniciar_laco(pipe):
    def laco():
        while True:
            try:
                passo(pipe)
                _acordado(any(t.is_alive() for t in pipe._threads.values()))
            except Exception:      # noqa: BLE001  a fila nunca derruba o app
                pass
            time.sleep(5)
    threading.Thread(target=laco, daemon=True, name='fila-de-livros').start()


# ---------- rotas ----------
class Entram(BaseModel):
    livros: list[str]
    config: dict | None = None      # mesma configuração da tela do livro (tarefa, rapido…); vazio = a que o livro já tem
    configs: dict[str, dict] | None = None      # por livro (ganha do config geral): a linha "rascunho rápido" da importação


class Horario(BaseModel):
    comecar: str | None = None      # 'HH:MM' ou vazio = agora
    parar: str | None = None        # 'HH:MM' ou vazio = até acabar


def _pipe():
    import pipeline
    return pipeline


def _blocos(pipe, livro):
    """Quantos blocos o livro tem para traduzir (o que o pipeline gravou na importação). 0 = não sabe."""
    try:
        return len(json.loads((pipe.pasta(livro) / 'fonte/dados/source.json').read_text(encoding='utf-8')).get('blocks') or [])
    except Exception:      # noqa: BLE001  (livro sem fonte ou apagado: não entra na conta)
        return 0


def estimativa(pipe, livro, rapido):
    """Segundos de trabalho previstos para o livro, pelo ritmo dos que já rodaram neste computador (rápido e completo separados).
    None = ainda não há histórico do tipo. Conta blocos, não páginas: é uma previsão, não promessa."""
    import duplo, fila
    seg = blo = 0
    for nome, a, s in fila.todos("select livro, a, segundos from trabalho where tarefa = 'traduzir' and estado = 'concluido' and segundos > 0"):
        if (a == duplo.classico.NOME) != rapido:
            continue
        n = _blocos(pipe, nome)
        if n:
            seg, blo = seg + s, blo + n
    n = _blocos(pipe, livro)
    return round(seg / blo * n) if blo and n else None


@router.get('/api/fila')
def ver():
    """A fila, com o que o pipeline sabe de cada livro (para a tela não precisar perguntar livro a livro)."""
    pipe, f = _pipe(), le()
    for i in f['itens']:
        try:
            st = pipe.estado(i['livro'])
            i['etapa'], i['progresso'], i['mensagem'] = st.get('etapa'), (st.get('fila') or {}).get('progresso', st.get('progresso')), st.get('mensagem', '')
            i['rascunho'], i['segundos'] = st.get('rascunho'), (st.get('fila') or {}).get('segundos')
            if i['estado'] == 'na fila':
                i['estimativa'] = estimativa(pipe, i['livro'], bool((i.get('config') or {}).get('rapido')))
        except Exception:      # noqa: BLE001
            i['sumiu'] = True
    f['outro_rodando'] = sorted(n for n, t in pipe._threads.items() if t.is_alive() and n not in {i['livro'] for i in f['itens'] if i['estado'] == 'rodando'})
    return f


@router.post('/api/fila')
def entram(e: Entram):
    pipe = _pipe()
    with _trava:
        f = le()
        ja = {i['livro'] for i in f['itens'] if i['estado'] in ('na fila', 'rodando')}
        for nome in e.livros:
            pipe.pasta(nome)      # 404 se não existe
            if nome not in ja:
                cfg = (e.configs or {}).get(nome) or e.config or {}
                f['itens'] = [i for i in f['itens'] if i['livro'] != nome] + [{'livro': nome, 'estado': 'na fila', 'motivo': '', 'config': cfg}]
        _grava(f)
    return ver()


@router.delete('/api/fila/{livro}')
def tira(livro: str):
    with _trava:
        f = le()
        if any(i['livro'] == livro and i['estado'] == 'rodando' for i in f['itens']):
            raise HTTPException(409, 'este livro está sendo processado: pause-o na tela dele antes de tirar da fila')
        f['itens'] = [i for i in f['itens'] if i['livro'] != livro]
        _grava(f)
    return ver()


@router.post('/api/fila/{livro}/mover')
def move(livro: str, para: int):
    """para = -1 sobe, +1 desce (só entre os que ainda esperam)."""
    with _trava:
        f = le()
        k = next((n for n, i in enumerate(f['itens']) if i['livro'] == livro and i['estado'] == 'na fila'), None)
        j = k + para if k is not None else None
        if j is not None and 0 <= j < len(f['itens']) and f['itens'][j]['estado'] == 'na fila':
            f['itens'][k], f['itens'][j] = f['itens'][j], f['itens'][k]
            _grava(f)
    return ver()


@router.post('/api/fila/ligar')
def liga(h: Horario):
    agora = time.time()
    try:
        inicio = _proxima_hora(h.comecar, agora) if h.comecar else None
        fim = _proxima_hora(h.parar, inicio or agora) if h.parar else None
    except ValueError:
        raise HTTPException(400, 'horário no formato HH:MM')
    with _trava:
        f = le()
        for i in f['itens']:      # "tentar de novo": o que parou ou esperava volta para a fila
            if i['estado'] in ('parou', 'esperando'):
                i.update(estado='na fila', motivo='')
        f.update(ligada=True, inicio_em=inicio, fim_em=fim, aviso='')
        _grava(f)
    return ver()


@router.post('/api/fila/desligar')
def desliga():
    """Para de começar livros novos. O que está rodando continua (pause-o na tela dele se quiser parar tudo)."""
    with _trava:
        f = le()
        f.update(ligada=False, inicio_em=None, fim_em=None, aviso='')
        _grava(f)
    return ver()


@router.post('/api/fila/limpar')
def limpa():
    with _trava:
        f = le()
        f['itens'] = [i for i in f['itens'] if i['estado'] != 'pronto']
        _grava(f)
    return ver()


if __name__ == '__main__':      # autoteste com um pipeline de mentira: ordem, erro que não trava, pergunta, pausa à mão, horário, reinício
    import tempfile

    class T:
        def __init__(self): self.vivo = True
        def is_alive(self): return self.vivo

    class Falso:
        def __init__(self): self._threads, self.st, self.pausados, self.iniciados = {}, {}, [], []

        def iniciar(self, livro, config=None):
            if livro == 'sem-arquivo':
                raise ValueError('o livro não tem arquivo de origem em fonte/')
            self.iniciados.append(livro); self._threads[livro] = T(); self.st[livro] = {'estado': 'rodando'}

        def estado(self, livro): return self.st[livro]
        def pausar(self, livro): self.pausados.append(livro); self._threads[livro].vivo = False; self.st[livro] = {'estado': 'pausado'}

        def acaba(self, livro, **st): self._threads[livro].vivo = False; self.st[livro] = st

    ARQ = Path(tempfile.mkdtemp()) / 'fila.json'
    p = Falso()
    it = lambda *n: [{'livro': x, 'estado': 'na fila', 'motivo': '', 'config': {}} for x in n]      # noqa: E731
    est = lambda f: [i['estado'] for i in f['itens']]      # noqa: E731
    _grava({**VAZIA, 'itens': it('a', 'sem-arquivo', 'b', 'c', 'd')})
    assert est(passo(p)) == ['na fila'] * 5 and not p.iniciados      # desligada: não faz nada
    _grava({**le(), 'ligada': True})
    assert est(passo(p))[0] == 'rodando' and est(passo(p)) == ['rodando', 'na fila', 'na fila', 'na fila', 'na fila']      # um por vez
    p.acaba('a', estado='concluido')
    f = passo(p); assert est(f)[:2] == ['pronto', 'parou'] and 'arquivo de origem' in f['itens'][1]['motivo']      # erro ao começar: marca e segue
    assert est(passo(p))[2] == 'rodando'
    p.acaba('b', estado='erro', mensagem='RuntimeError: x')
    f = passo(p); assert est(f)[2:4] == ['parou', 'rodando'] and f['itens'][2]['motivo'] == 'RuntimeError: x'      # erro no meio não trava a fila
    p.acaba('c', estado='pausado', pergunta='camada', mensagem='a camada de texto parece ruim')
    f = passo(p); assert est(f)[3:] == ['esperando', 'rodando'] and f['ligada']      # pergunta: espera você, a fila segue
    p.acaba('d', estado='pausado')      # pausado à mão
    f = passo(p); assert est(f)[4] == 'na fila' and not f['ligada'] and 'pausou' in f['aviso']
    # outro livro rodando por fora: a fila espera
    p._threads['fora'] = T(); _grava({**le(), 'ligada': True})
    assert est(passo(p))[4] == 'na fila'
    p._threads['fora'].vivo = False
    assert est(passo(p))[4] == 'rodando'
    # hora de parar: pausa o livro e desliga
    _grava({**le(), 'fim_em': 1000}); f = passo(p, agora=2000)
    assert p.pausados == ['d'] and est(f)[4] == 'na fila' and not f['ligada']
    # começar mais tarde
    _grava({**le(), 'ligada': True, 'inicio_em': 5000})
    assert est(passo(p, agora=4000))[4] == 'na fila' and est(passo(p, agora=5001))[4] == 'rodando'
    # reinício do servidor: o item diz "rodando", o pipeline ainda não subiu a thread e o estado do livro é "rodando" -> retoma, não fecha
    n = len(p.iniciados); p._threads.clear()
    f = passo(p); assert est(f)[4] == 'rodando' and len(p.iniciados) == n + 1
    assert _proxima_hora('23:30', datetime(2030, 1, 1, 22, 0).timestamp()) == datetime(2030, 1, 1, 23, 30).timestamp()
    assert _proxima_hora('06:00', datetime(2030, 1, 1, 22, 0).timestamp()) == datetime(2030, 1, 2, 6, 0).timestamp()
    print('ok')
