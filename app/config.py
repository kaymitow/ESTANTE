"""Configurações do app, num arquivo só: app/dados/config.json (fora do git; nunca sai desta máquina).

    config.le()                 tudo, com os padrões preenchidos
    config.grava({'rede': {'pesquisa': True}})     muda só o que foi passado
"""
import json
from pathlib import Path

ARQ = Path(__file__).resolve().parent / 'dados' / 'config.json'
PADRAO = {
    'papeis': {},                 # tradutor, geral, auditor, leitor, leitor2 -> nome do modelo ('' = automático)
    'rede': {                     # tudo desligado por padrão: o app não fala com a internet sem um clique seu
        'pesquisa': False,        # consultar dicionário/enciclopédia por um termo do glossário
        'edicoes': False,         # acervos abertos: procurar outras edições e buscar/baixar livros (Internet Archive, Gutenberg, Open Library)
        'modelo_fora': False,     # usar um modelo pela internet (o texto do livro sai da máquina)
        'fora_url': '', 'fora_chave': '', 'fora_modelo': '',
    },
    'processo': {                 # como o livro é processado (Configurações → Processamento)
        'juiz': True,             # um terceiro modelo decide as disputas entre tradutor e auditor
        'refazer_abrandado': True,      # bloco em que o tradutor rápido abrandou palavra forte é refeito pelo modelo maior, se instalado
        'aceite_automatico': False,     # ao terminar, aceita o que sobrou sem revisão (cada aceite vira commit automático). Desligado por padrão.
    },
}


def _funde(base, novo):
    for k, v in novo.items():
        base[k] = _funde(dict(base.get(k, {})), v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return base


def le():
    try:
        salvo = json.loads(ARQ.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        salvo = {}
    return _funde(json.loads(json.dumps(PADRAO)), salvo)


def grava(parcial):
    c = _funde(le(), parcial)
    ARQ.parent.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding='utf-8')
    return c


if __name__ == '__main__':
    assert _funde({'a': {'x': 1, 'y': 2}, 'b': 1}, {'a': {'y': 3}}) == {'a': {'x': 1, 'y': 3}, 'b': 1}
    assert le()['rede']['pesquisa'] in (True, False)
    print('ok')
