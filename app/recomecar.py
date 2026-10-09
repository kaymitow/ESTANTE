"""Refaz a transformação (tradução/atualização) de um livro, no todo ou em parte, mantendo extração e estrutura.

    python app/recomecar.py <pasta-do-livro>                      tudo do zero
    python app/recomecar.py <pasta-do-livro> --so-auditoria       mantém as propostas; refaz checagens, auditoria e correções
    python app/recomecar.py <pasta-do-livro> --blocos b00075,b00102     refaz só esses blocos (proposta, auditoria, correção)
    python app/recomecar.py <pasta-do-livro> --julgar             leva ao juiz os blocos que ainda têm objeção e não foram aceitos (nada mais muda)
    python app/recomecar.py <pasta-do-livro> --so-checagens       recalcula as checagens automáticas (sem modelo) e leva ao juiz só o que mudou

Rodar com o servidor PARADO; ao subir de novo ele retoma sozinho. Não toca em texto/livro.md nem em fonte/.
Serve depois de mudar prompt, modelo ou checagens, quando o que já foi feito não vale mais. Blocos já aceitos não são mexidos no livro.
"""
import json, sys
from pathlib import Path

import duplo
import fila

LIMPA = 'aud_ok=null, aud_prob=null, revisado=null, checagem2=null, aud2_ok=null, aud2_prob=null'
f = Path(__file__).resolve().parent.parent / 'livros' / sys.argv[1] / 'revisao' / 'dados' / 'pipeline.json'
st = json.loads(f.read_text(encoding='utf-8'))
tid = st.get('trabalho')
if tid and '--julgar' in sys.argv:
    # o que o usuário já aceitou não vai a julgamento: o aceite fica guardado no rascunho, não na fila
    aceitos = {b['id'] for b in json.loads((f.parent / 'rascunho.json').read_text(encoding='utf-8'))['blocos'] if b.get('aceito')}
    for r in fila.todos('select k, raw from item where trabalho=?', (tid,)):
        fila.exe('update item set aceito=?, juiz=null, julgado=null where trabalho=? and k=?', (int(r['raw'] in aceitos), tid, r['k']))
    fila.exe("update item set estado='na fila' where trabalho=? and aceito=0", (tid,))
    fila.exe("update trabalho set estado='rodando', fase='julgar', erro='' where id=?", (tid,))
    print(f'{len(aceitos)} blocos aceitos ficam como estão; os demais com objeção vão ao juiz')
elif tid and '--so-checagens' in sys.argv:
    # depois de mudar as checagens: recalcula sobre o texto que já existe (não usa modelo) e leva ao juiz só o que passar a ter alerta.
    # Os blocos que o juiz já julgou e os aceitos pelo usuário ficam como estão.
    aceitos = {b['id'] for b in json.loads((f.parent / 'rascunho.json').read_text(encoding='utf-8'))['blocos'] if b.get('aceito')}
    t = fila.um('select * from trabalho where id=?', (tid,))
    novos = 0
    for r in fila.todos('select * from item where trabalho=?', (tid,)):
        fila.exe('update item set aceito=? where trabalho=? and k=?', (int(r['raw'] in aceitos), tid, r['k']))
        if r['juiz'] or r['raw'] in aceitos or r['proposta'] is None:
            continue
        coluna, texto = ('checagem2', r['revisado']) if r['revisado'] is not None else ('checagem', r['proposta'])
        ch = json.dumps(duplo.checagens(r['fonte'], texto, t['tarefa'], t['contexto'] or ''), ensure_ascii=False)
        if ch != (r[coluna] or '[]'):
            novos += 1
            fila.exe(f"update item set {coluna}=?, estado='na fila' where trabalho=? and k=?", (ch, tid, r['k']))
    fila.exe("update trabalho set estado='rodando', fase='julgar', erro='' where id=?", (tid,))
    print(f'{novos} blocos mudaram de alerta; os que têm objeção e ainda não foram julgados vão ao juiz')
elif tid and '--blocos' in sys.argv:
    ids = sys.argv[sys.argv.index('--blocos') + 1].split(',')
    for i in ids:
        fila.exe(f"update item set proposta=null, checagem=null, {LIMPA}, estado='na fila' where trabalho=? and raw=?", (tid, i))
    fila.exe("update trabalho set estado='rodando', fase='propor', erro='' where id=?", (tid,))
    print(f'{len(ids)} blocos serão refeitos')
elif tid and '--so-auditoria' in sys.argv:
    t = fila.um('select * from trabalho where id=?', (tid,))
    for r in fila.todos('select k, fonte, proposta from item where trabalho=? and proposta is not null', (tid,)):
        fila.exe(f"update item set checagem=?, {LIMPA}, estado='na fila' where trabalho=? and k=?",
                 (json.dumps(duplo.checagens(r['fonte'], r['proposta'], t['tarefa'], t['contexto'] or ''), ensure_ascii=False), tid, r['k']))
    fila.exe("update trabalho set estado='rodando', fase='propor', erro='' where id=?", (tid,))
elif tid:
    fila.parar(st.pop('trabalho'))
st['feitas'] = [e for e in st['feitas'] if e not in ('transformacao', 'rascunho')]
st.update(progresso=0, estado='rodando', etapa='transformacao')
f.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8')
print('a transformação continua quando o servidor subir; etapas mantidas:', st['feitas'])
