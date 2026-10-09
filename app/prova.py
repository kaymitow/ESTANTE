"""Prova de fidelidade: para cada bloco do livro, de onde veio o texto, quem o aceitou e em qual commit.

    python app/prova.py <pasta-do-livro>              gera saida/prova.json e saida/prova.html
    python app/prova.py <pasta-do-livro> --conferir   confere o livro.md e os blocos com o que foi gravado

Nada novo é guardado além da data de cada aceite (revisao/dados/rascunho.json, campo aceito_em): os hashes são recalculados
dos arquivos, e o commit de um aceite é o primeiro commit do rascunho feito depois da hora dele (o commit sai logo depois
da gravação). Bloco aceito antes desta prova não tem data: aparece como "sem registro".
"""
import argparse, hashlib, html, json, sys, time
from pathlib import Path

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extras  # noqa: E402  (git da biblioteca)

router = APIRouter()
RAIZ = Path(__file__).resolve().parent.parent


def sha(b: bytes | str) -> str:
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode('utf-8')).hexdigest()


def texto_final(b: dict) -> str:
    return b.get('texto') or b.get('resultado') or ''


def caminho(b: dict) -> str:
    if b.get('tipo') == 'imagem':
        return 'imagem (sem texto)'
    if b.get('texto'):
        return 'editado à mão'
    quem = {'aprovado': 'aprovado pelos modelos', 'juiz': 'corrigido pelo juiz', 'revisar': 'pedia atenção'}.get(b.get('status'), str(b.get('status')))
    return f'aceito automaticamente ({quem})' if b.get('aceito_auto') else quem


def commits(rascunho: Path) -> list[tuple[str, int]]:
    """Commits que mexeram no rascunho, do mais antigo para o mais novo: (hash, hora em segundos)."""
    r = extras.git('log', '--format=%H %ct', '--', str(rascunho))
    out = [(h, int(ct)) for h, ct in (l.split() for l in r.stdout.splitlines() if l.strip())]
    return sorted(out, key=lambda x: x[1])


def commit_do_aceite(hora: float, cs: list[tuple[str, int]]) -> str | None:
    """Primeiro commit feito na hora do aceite ou depois dela."""
    return next((h for h, ct in cs if ct >= int(hora)), None)


def monta(pasta: Path) -> dict:
    fonte = json.loads((pasta / 'fonte/dados/source.json').read_text(encoding='utf-8'))['blocks']
    rasc = pasta / 'revisao/dados/rascunho.json'
    r = json.loads(rasc.read_text(encoding='utf-8'))
    fonte_por_id = {b['id']: b.get('text', '') for b in fonte}
    cs = commits(rasc)
    blocos = []
    for b in r['blocos']:
        item = {'id': b['id'], 'pagina': b.get('paginas') or [], 'fonte_sha': sha(fonte_por_id.get(b['id'], b.get('fonte', ''))),
                'resultado_sha': sha(texto_final(b)), 'caminho': caminho(b), 'aceito': bool(b.get('aceito')), 'texto': texto_final(b)}
        if b.get('aceito'):
            if b.get('aceito_em'):
                item['aceito_em'] = time.strftime('%d/%m/%Y %H:%M', time.localtime(b['aceito_em']))
                item['commit'] = commit_do_aceite(b['aceito_em'], cs) or 'sem commit correspondente'
            else:
                item['commit'] = 'sem registro (aceito antes da prova)'
        blocos.append(item)
    arq_fonte = next((f for f in (pasta / 'fonte').glob('*') if f.is_file() and f.suffix.lower() != '.json'), None)
    ids_fonte, ids_rasc = set(fonte_por_id), {b['id'] for b in r['blocos']}
    return {
        'livro': pasta.name, 'gerado': time.strftime('%d/%m/%Y %H:%M'),
        'fonte_arquivo': arq_fonte.name if arq_fonte else None,
        'fonte_arquivo_sha': sha(arq_fonte.read_bytes()) if arq_fonte else None,
        'livro_md_sha': sha((pasta / 'texto/livro.md').read_bytes()),
        'totais': {'blocos_fonte': len(fonte), 'blocos_rascunho': len(r['blocos']), 'aceitos': sum(i['aceito'] for i in blocos),
                   'pendentes': sum(not i['aceito'] for i in blocos),
                   'sem_registro': sum(i.get('commit', '').startswith('sem registro') for i in blocos),
                   'fecha': ids_fonte == ids_rasc and len(fonte) == len(r['blocos'])},
        'blocos': blocos,
    }


def html_de(p: dict) -> str:
    t = p['totais']
    linhas = '\n'.join(
        f"<tr><td>{html.escape(i['id'])}</td><td>{html.escape(', '.join(map(str, i['pagina'])))}</td><td>{html.escape(i['caminho'])}</td>"
        f"<td>{'sim' if i['aceito'] else 'não'}</td><td>{html.escape(i.get('aceito_em', ''))}</td><td>{html.escape(str(i.get('commit', ''))[:12])}</td></tr>"
        for i in p['blocos'])
    return f"""<!doctype html><meta charset="utf-8"><title>Prova de fidelidade: {html.escape(p['livro'])}</title>
<style>body{{font:14px system-ui;margin:2rem}}table{{border-collapse:collapse}}td,th{{border-bottom:1px solid #ccc;padding:.3rem .6rem;text-align:left}}code{{font-size:12px}}</style>
<h1>Prova de fidelidade</h1><p>{html.escape(p['livro'])} · gerado em {p['gerado']}</p>
<p>Fonte: {html.escape(p['fonte_arquivo'] or '(sem arquivo)')}<br><code>{p['fonte_arquivo_sha'] or ''}</code><br>livro.md: <code>{p['livro_md_sha']}</code></p>
<p>{t['blocos_fonte']} blocos na fonte, {t['blocos_rascunho']} no rascunho, {t['aceitos']} aceitos, {t['pendentes']} pendentes, {t['sem_registro']} sem registro. Fecha: {'sim' if t['fecha'] else 'não'}.</p>
<table><tr><th>bloco</th><th>página</th><th>caminho</th><th>aceito</th><th>aceito em</th><th>commit</th></tr>
{linhas}</table>"""


def gera(pasta: Path) -> dict:
    p = monta(pasta)
    (pasta / 'saida').mkdir(exist_ok=True)
    gravada = {**p, 'blocos': [{k: v for k, v in i.items() if k != 'texto'} for i in p['blocos']]}      # o texto já está no livro
    (pasta / 'saida/prova.json').write_text(json.dumps(gravada, ensure_ascii=False, indent=1), encoding='utf-8')
    (pasta / 'saida/prova.html').write_text(html_de(p), encoding='utf-8')
    return p


def conferir(pasta: Path) -> list[str]:
    """Problemas entre a prova gravada e os arquivos de agora (lista vazia = tudo bate)."""
    gravada = json.loads((pasta / 'saida/prova.json').read_text(encoding='utf-8'))
    agora = monta(pasta)
    erros = []
    if gravada['livro_md_sha'] != agora['livro_md_sha']:
        erros.append('livro.md mudou desde a prova')
    if gravada['fonte_arquivo_sha'] != agora['fonte_arquivo_sha']:
        erros.append('arquivo de origem mudou desde a prova')
    texto_md = ' '.join((pasta / 'texto/livro.md').read_text(encoding='utf-8').split())
    antes = {i['id']: i for i in gravada['blocos']}
    for i in agora['blocos']:
        if i['id'] not in antes:
            erros.append(f"{i['id']}: bloco novo, sem prova gravada")
            continue
        if antes[i['id']]['resultado_sha'] != i['resultado_sha']:
            erros.append(f"{i['id']}: texto do bloco mudou desde a prova")
        if i['aceito'] and ' '.join(i['texto'].split()) not in texto_md:
            erros.append(f"{i['id']}: o texto aceito não está igual no livro.md (editado à mão ali?)")
    return erros


@router.get('/api/livro/{livro}/prova')
def prova_do_livro(livro: str):
    """Gera a prova do livro (saida/prova.json e prova.html) e devolve o resumo."""
    pasta = RAIZ / 'livros' / livro
    if not (pasta / 'revisao/dados/rascunho.json').exists():
        raise HTTPException(404, 'este livro ainda não tem rascunho para provar')
    p = gera(pasta)
    return {'totais': p['totais'], 'arquivos': ['prova.json', 'prova.html']}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pasta', type=Path); ap.add_argument('--conferir', action='store_true')
    a = ap.parse_args()
    pasta = a.pasta if a.pasta.is_absolute() else RAIZ / 'livros' / a.pasta
    if a.conferir:
        erros = conferir(pasta)
        print('\n'.join(erros) if erros else 'ok: a prova bate com os arquivos')
        sys.exit(1 if erros else 0)
    p = gera(pasta)
    print(json.dumps(p['totais'], ensure_ascii=False))
    print(f"gravado em {pasta / 'saida/prova.json'}")
