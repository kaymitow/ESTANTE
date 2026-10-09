"""Fila persistente (SQLite) do fluxo de dois modelos. Sobrevive a travamento e a reinício do servidor.

Um trabalho = um lote de itens (parágrafos) de um livro, para uma tarefa. O trabalhador processa POR MODELO, não por item:
    fase 'propor'    -> modelo A em todos os itens
    fase 'auditar'   -> modelo B em todos
    fase 'revisar'   -> modelo A só nos que tiveram problema
    fase 'reauditar' -> modelo B só nos revisados
    fase 'julgar'    -> um terceiro modelo (o juiz) só nos que ainda têm objeção: decide quem tem razão e, se for o auditor, conserta
Assim os dois modelos (que não cabem juntos na GPU) trocam de lugar poucas vezes por lote, em vez de duas vezes por item.
Cada passo é gravado na hora; ao reiniciar, o trabalhador continua do item que faltava.
"""
import json, sqlite3, threading, time, uuid
from pathlib import Path

import config
import duplo

DB = Path(__file__).resolve().parent / 'dados' / 'fila.db'
FASES = ['propor', 'auditar', 'revisar', 'reauditar', 'julgar', 'fim']
_trava = threading.RLock()
_acorda = threading.Event()
_con = None


def con():
    global _con
    if _con is None:
        DB.parent.mkdir(exist_ok=True)
        _con = sqlite3.connect(DB, check_same_thread=False)
        _con.row_factory = sqlite3.Row
        _con.executescript('''
            create table if not exists trabalho (id text primary key, livro text, tarefa text, a text, b text,
                estado text, fase text, criado real, atualizado real, segundos real default 0);
            create table if not exists item (trabalho text, k integer, i integer, raw text, prefixo text, fonte text,
                proposta text, checagem text, aud_ok integer, aud_prob text, revisado text, checagem2 text, aud2_ok integer, aud2_prob text,
                estado text default 'na fila', aceito integer default 0, segundos real default 0, primary key (trabalho, k));
        ''')
        colunas = [r[1] for r in _con.execute('pragma table_info(trabalho)')]
        if 'contexto' not in colunas:
            _con.execute("alter table trabalho add column contexto text default ''")
        if 'erro' not in colunas:
            _con.execute("alter table trabalho add column erro text default ''")
        if 'juiz' not in [r[1] for r in _con.execute('pragma table_info(item)')]:
            _con.execute('alter table item add column juiz text')        # decisão do juiz (JSON)
            _con.execute('alter table item add column julgado text')     # texto final quando o juiz consertou
        if 'votos' not in [r[1] for r in _con.execute('pragma table_info(item)')]:
            _con.execute('alter table item add column votos text')       # votos do votante (JSON), guardados para o trabalho retomar sem votar de novo
        _con.commit()
    return _con


def exe(sql, args=()):
    with _trava:
        c = con().execute(sql, args)
        con().commit()
        return c


def um(sql, args=()):
    with _trava:
        return con().execute(sql, args).fetchone()


def todos(sql, args=()):
    with _trava:
        return con().execute(sql, args).fetchall()


# ---------- API usada pelas rotas ----------
def criar(livro, tarefa, itens, a=duplo.A_PADRAO, b=duplo.B_PADRAO, contexto=''):
    tid = uuid.uuid4().hex[:8]
    agora = time.time()
    with _trava:
        con().execute('insert into trabalho (id, livro, tarefa, a, b, estado, fase, criado, atualizado, contexto) values (?,?,?,?,?,?,?,?,?,?)',
                      (tid, livro, tarefa, a, b, 'rodando', 'propor', agora, agora, contexto))
        con().executemany('insert into item (trabalho, k, i, raw, prefixo, fonte) values (?,?,?,?,?,?)',
                          [(tid, k, it['i'], it['raw'], it['prefixo'], it['fonte']) for k, it in enumerate(itens)])
        con().commit()
    _acorda.set()
    return tid


def _fala(ok, prob, prefixo):
    """Fala do auditor. Aprovado pode vir com notas de estilo, que não reprovam."""
    p = json.loads(prob or '[]')
    return ('Fiel.' + (' ' + ' '.join(p) if p else '')) if ok else prefixo + '; '.join(p)


def _conversa(r, a, b):
    c = []
    if r['proposta'] is not None:
        c.append({'quem': a, 'disse': r['proposta']})
    if r['aud_ok'] is not None:
        c.append({'quem': b, 'disse': _fala(r['aud_ok'], r['aud_prob'], 'Problemas: ')})
    if r['revisado'] is not None:
        c.append({'quem': a, 'disse': 'Revisão: ' + r['revisado']})
    if r['aud2_ok'] is not None:
        c.append({'quem': b, 'disse': _fala(r['aud2_ok'], r['aud2_prob'], 'Ainda discordo: ')})
    if r['juiz']:
        j = json.loads(r['juiz'])
        c.append({'quem': j['modelo'], 'papel': 'juiz', 'ganhou': j['ganhou'], 'disse': _sentenca(j, r['julgado'])})
    return c


def _sentenca(j, julgado):
    votos = ' '.join(f"({k}) {'procede' if v[0] else 'não procede'}{f' (certeza de {round(100 * v[2])}%)' if len(v) > 2 and v[2] is not None else ''}{': ' + v[1] if v[1] else ''}." for k, v in enumerate(j['votos'], 1))
    fim = {'tradutor': 'Causa do tradutor: a versão fica como está.', 'auditor': 'Causa do auditor. Versão corrigida: ' + (julgado or ''),
           'usuario': 'Não consegui resolver: vai para a sua revisão.'}[j['ganhou']]
    return f'Sentença: {votos} {fim}'


def _final(r):
    return r['julgado'] if r['julgado'] is not None else r['revisado'] if r['revisado'] is not None else r['proposta']


def _problemas(r):
    """Problemas que valem no fim: os que o juiz deixou de pé, se ele julgou; senão, os da última rodada feita."""
    if r['juiz']:
        return json.loads(r['juiz'])['problemas']
    if r['revisado'] is not None:
        return json.loads(r['checagem2'] or '[]') + ([] if r['aud2_ok'] else _graves(r['aud2_prob']))
    return json.loads(r['checagem'] or '[]') + ([] if r['aud_ok'] else _graves(r['aud_prob']))


def _graves(prob):
    return [p for p in json.loads(prob or '[]') if not p.startswith('estilo: ')]


def resumo(tid):
    """Estado do trabalho sem a lista de itens: barato, para a tela consultar várias vezes por segundo."""
    t = um('select * from trabalho where id=?', (tid,))
    if not t:
        return None
    linhas = todos('select estado, proposta is not null as p, aud_ok, checagem, revisado is not null as r, aud2_ok, checagem2, juiz from item where trabalho=?', (tid,))
    # progresso por passos: 2 por item (propor, auditar) + 2 para cada item que precisou de revisão
    precisa = sum(1 for r in linhas if r['aud_ok'] is not None and (not r['aud_ok'] or r['checagem'] not in (None, '', '[]')))
    passos = sum(r['p'] + (r['aud_ok'] is not None) + r['r'] + (r['aud2_ok'] is not None) for r in linhas)
    progresso = 1.0 if t['estado'] == 'concluido' else passos / max(1, 2 * len(linhas) + 2 * precisa)
    conta = {'propostos': sum(r['p'] for r in linhas), 'conferidos': sum(r['aud_ok'] is not None for r in linhas),
             'com_problema': precisa, 'corrigidos': sum(r['r'] for r in linhas),
             # para as pilhas do tribunal (ui/src/lib/cena.js): quantos voltaram ao auditor e quantos seguem em disputa depois disso
             'reconferidos': sum(r['aud2_ok'] is not None for r in linhas),
             'em_disputa': sum(1 for r in linhas if r['aud2_ok'] is not None and (not r['aud2_ok'] or r['checagem2'] not in (None, '', '[]'))),
             **{'causa_' + q: sum(1 for r in linhas if r['juiz'] and f'"ganhou": "{q}"' in r['juiz']) for q in ('tradutor', 'auditor', 'usuario')}}
    return {'conta': conta, 'progresso': round(progresso, 3), 'id': tid, 'livro': t['livro'], 'tarefa': t['tarefa'], 'fase': t['fase'], 'estado': t['estado'],
            'total': len(linhas), 'feito': sum(1 for r in linhas if r['estado'] in ('aprovado', 'revisar', 'cancelado')),
            'rodando': t['estado'] == 'rodando', 'segundos': round(t['segundos']), 'a': t['a'], 'b': t['b'], 'erro': t['erro'] or ''}


def estado(tid):
    """Resumo + todos os itens com resultado, problemas e conversa (pesado em livro grande: usar só quando precisa dos itens)."""
    e = resumo(tid)
    if not e:
        return None
    e['itens'] = [{'i': r['i'], 'raw': r['raw'], 'prefixo': r['prefixo'], 'fonte': r['fonte'], 'estado': r['estado'],
                   'resultado': _final(r) or '',
                   'problemas': _problemas(r) if r['estado'] in ('aprovado', 'revisar') else [],
                   'conversa': _conversa(r, e['a'], e['b']), 'segundos': round(r['segundos'], 1), 'aceito': bool(r['aceito'])}
                  for r in todos('select * from item where trabalho=? order by k', (tid,))]
    return e


def listar(n=10):
    return [dict(r) for r in todos('select id, livro, tarefa, estado, fase, criado, (select count(*) from item where trabalho=trabalho.id) as total '
                                   'from trabalho order by criado desc limit ?', (n,))]


def parar(tid):
    exe("update trabalho set estado='cancelado', atualizado=? where id=? and estado in ('rodando','pausado')", (time.time(), tid))
    exe("update item set estado='cancelado' where trabalho=? and estado not in ('aprovado','revisar')", (tid,))


def pausar(tid, sim=True):
    exe('update trabalho set estado=?, atualizado=? where id=? and estado in (?, ?)',
        ('pausado' if sim else 'rodando', time.time(), tid, 'rodando', 'pausado'))
    if not sim:
        exe("update trabalho set erro='' where id=?", (tid,))
    _acorda.set()


def marcar_aceito(tid, k, novo_raw):
    exe('update item set aceito=1, raw=? where trabalho=? and k=?', (novo_raw, tid, k))


# ---------- trabalhador ----------
def _ativo(tid):
    t = um('select estado from trabalho where id=?', (tid,))
    return t and t['estado'] == 'rodando'


def _audita(tid, b, tarefa, fonte, saida):
    """Audita com b; se b não carrega (modelo grande sem memória livre), o trabalho segue com o auditor leve em vez de parar."""
    try:
        return (*duplo.auditar(b, tarefa, fonte, saida), b)
    except Exception:      # noqa: BLE001
        if b in (duplo.LEVE, duplo.FORA):
            raise
        r = duplo.auditar(duplo.LEVE, tarefa, fonte, saida)
        exe('update trabalho set b=? where id=?', (duplo.LEVE, tid))
        print(f'[fila] trabalho {tid}: o auditor {b} não respondeu; segue com {duplo.LEVE}', flush=True)
        return (*r, duplo.LEVE)


def _roda(t):
    tid, tarefa, a, b, ctx = t['id'], t['tarefa'], t['a'], t['b'], t['contexto'] or ''
    fase = t['fase']
    while fase != 'fim':
        if fase == 'propor':
            pend = todos('select * from item where trabalho=? and proposta is null order by k', (tid,))
        elif fase == 'auditar':
            pend = todos('select * from item where trabalho=? and proposta is not null and aud_ok is null order by k', (tid,))
        elif fase == 'revisar':
            pend = [r for r in todos('select * from item where trabalho=? and revisado is null order by k', (tid,))
                    if not r['aud_ok'] or json.loads(r['checagem'] or '[]')]
            # blocos com palavra forte abrandada vão por último e juntos: são refeitos pelo modelo maior, e assim ele só é carregado uma vez
            pend.sort(key=lambda r: any(x in (r['checagem'] or '') for x in duplo.REFAZER))
            maior = duplo.grande(menos=a) if config.le()['processo']['refazer_abrandado'] and any(x in (r['checagem'] or '') for r in pend for x in duplo.REFAZER) else None
        elif fase == 'julgar':
            pend = [r for r in todos('select * from item where trabalho=? and juiz is null and aceito=0 order by k', (tid,)) if _problemas(r)]
            juizes = duplo.juizes(a, b) if pend and tarefa.startswith('traduzir') and config.le()['processo']['juiz'] else []
            if not juizes:
                pend = []          # sem modelo para julgar: os blocos seguem para a revisão como estão
            # Dois tempos: se há um votante escolhido, ele vota todos os blocos primeiro (um modelo só na placa) e o juiz fica com a correção.
            # Medido em 07/10/2026: um modelo pequeno com limite de certeza votou melhor que o juiz grande, mas não corrige bem.
            votante, votos = config.le()['papeis'].get('votante'), {}
            if pend and votante and votante != juizes[0]:
                for r in pend:
                    if not _ativo(tid):
                        return
                    if r['votos']:      # já votado antes de uma interrupção
                        votos[r['k']] = json.loads(r['votos']); continue
                    try:
                        votos[r['k']] = duplo.julgar(votante, tarefa, r['fonte'], _final(r), _problemas(r), ctx, certeza=config.le()['processo'].get('certeza_juiz', 0) > 0)
                        exe('update item set votos=? where trabalho=? and k=?', (json.dumps(votos[r['k']], ensure_ascii=False), tid, r['k']))
                    except Exception:      # noqa: BLE001  o votante não carregou: o juiz vota, como antes
                        votos = {}
                        break
        else:
            pend = todos('select * from item where trabalho=? and revisado is not null and aud2_ok is null order by k', (tid,))
        for r in pend:
            if not _ativo(tid):
                return
            exe("update item set estado='processando' where trabalho=? and k=?", (tid, r['k']))
            t0 = time.time()
            try:
                if fase == 'propor':
                    s = duplo.propor(tarefa, r['fonte'], a, ctx)
                    exe('update item set proposta=?, checagem=? where trabalho=? and k=?',
                        (s, json.dumps(duplo.checagens(r['fonte'], s, tarefa, ctx), ensure_ascii=False), tid, r['k']))
                elif fase == 'auditar':
                    ok, pb, b = _audita(tid, b, tarefa, r['fonte'], r['proposta'])
                    exe('update item set aud_ok=?, aud_prob=? where trabalho=? and k=?', (int(ok), json.dumps(pb, ensure_ascii=False), tid, r['k']))
                elif fase == 'revisar':
                    critica = '; '.join(json.loads(r['checagem'] or '[]') + json.loads(r['aud_prob'] or '[]'))
                    # texto inventado não se conserta por cima, e o mesmo modelo inventa de novo (no piloto, "Part 3" virou um parágrafo, sempre igual):
                    # refaz do zero com o OUTRO modelo
                    s = None
                    if maior and any(x in critica for x in duplo.REFAZER) and 'inventado' not in critica:
                        try:
                            s = duplo.propor(tarefa, r['fonte'], maior, ctx)
                        except Exception:      # noqa: BLE001  o modelo maior não coube na memória agora: segue com a correção normal
                            maior = None
                    if s is None:
                        s = duplo.propor(tarefa, r['fonte'], b, ctx) if 'inventado' in critica else duplo.revisar(tarefa, r['fonte'], r['proposta'], critica, a, ctx)
                    # se a correção saiu pior (texto inventado, ou a observação do revisor escrita dentro do texto), ela é descartada: fica a proposta
                    if any('inventado' in pr or 'comentário do modelo' in pr for pr in duplo.checagens(r['fonte'], s, tarefa, ctx)) and 'inventado' not in critica:
                        s = r['proposta']
                    # idem se saiu cortada: num livro inteiro, três blocos foram ao usuário com um décimo do texto porque a "correção" parou no meio
                    elif len(s) < 0.5 * len(r['proposta'] or '') and 'tamanho suspeito' not in critica and 'acréscimo' not in critica:
                        s = r['proposta']
                    exe('update item set revisado=?, checagem2=? where trabalho=? and k=?',
                        (s, json.dumps(duplo.checagens(r['fonte'], s, tarefa, ctx), ensure_ascii=False), tid, r['k']))
                elif fase == 'julgar':
                    while True:
                        try:
                            d = duplo.sentenciar(juizes[0], tarefa, r['fonte'], _final(r), _problemas(r), ctx, votos=votos.get(r['k']))
                            break
                        except Exception:      # noqa: BLE001  o juiz não carregou: tenta o próximo candidato; sem nenhum, a fase termina
                            juizes.pop(0)
                            if not juizes:
                                d = None
                                break
                    if d is None:              # nenhum juiz carregou: os blocos seguem para a revisão como estão
                        exe("update item set estado='na fila' where trabalho=? and k=?", (tid, r['k']))
                        break
                    exe('update item set juiz=?, julgado=? where trabalho=? and k=?',
                        (json.dumps({'modelo': juizes[0] + (f' (votos: {votante})' if votos.get(r['k']) else ''), 'ganhou': d['ganhou'], 'votos': d['votos'], 'objecoes': _problemas(r), 'problemas': d['problemas']}, ensure_ascii=False),
                         d['texto'] if d['ganhou'] == 'auditor' else None, tid, r['k']))
                else:
                    ok, pb, b = _audita(tid, b, tarefa, r['fonte'], r['revisado'])
                    exe('update item set aud2_ok=?, aud2_prob=? where trabalho=? and k=?', (int(ok), json.dumps(pb, ensure_ascii=False), tid, r['k']))
            except Exception as ex:      # noqa: BLE001  (modelo fora do ar, tempo esgotado…): pausa o trabalho, não perde nada
                exe("update item set estado='na fila' where trabalho=? and k=?", (tid, r['k']))
                exe("update trabalho set estado='pausado', erro=?, atualizado=? where id=?", (f'{type(ex).__name__}: {ex}'[:300], time.time(), tid))
                print(f'[fila] trabalho {tid} pausado: {ex}', flush=True)
                return
            gasto = time.time() - t0
            exe("update item set estado='na fila', segundos=segundos+? where trabalho=? and k=?", (gasto, tid, r['k']))
            exe('update trabalho set segundos=segundos+?, atualizado=? where id=?', (gasto, time.time(), tid))
        # rascunho rápido (motor clássico): só a tradução e as checagens automáticas; sem auditor nem juiz, tudo segue para a revisão
        fase = 'fim' if a == duplo.classico.NOME else FASES[FASES.index(fase) + 1]
        exe('update trabalho set fase=? where id=?', (fase, tid))
    # fecha: estado final de cada item
    for r in todos('select * from item where trabalho=? order by k', (tid,)):
        exe('update item set estado=? where trabalho=? and k=?', ('aprovado' if not _problemas(r) else 'revisar', tid, r['k']))
    exe("update trabalho set estado='concluido', atualizado=? where id=?", (time.time(), tid))


def _laco():
    while True:
        t = um("select * from trabalho where estado='rodando' order by criado limit 1")
        if t:
            _roda(t)
        else:
            _acorda.wait(timeout=5)
            _acorda.clear()


def iniciar():
    """Chamar uma vez ao subir o servidor: retoma o que ficou pela metade."""
    exe("update item set estado='na fila' where estado='processando'")
    threading.Thread(target=_laco, daemon=True, name='fila').start()
