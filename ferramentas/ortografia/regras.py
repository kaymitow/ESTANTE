"""Atualização de grafia do português antigo, palavra por palavra, sem modelo: léxico primeiro, regras gerais depois.

    from regras import moderniza, carrega
    texto, trocas = moderniza('O programma politico delle', carrega())      # -> 'O programa político dele', [('programma', 'programa'), …]

Só troca GRAFIA. Não mexe em vocabulário, ordem nem pontuação. Toda troca é devolvida em `trocas`, para a revisão mostrar.
O léxico (lexico.csv) vem de ferramentas/ortografia/minerar.py; as regras cobrem o que as reformas de 1911–1990 mudaram de forma regular.
Três camadas, da mais segura para a mais cautelosa:
  1. REGRAS    letras que o português atual não usa (ph, th, y, consoante dobrada…): trocadas sempre;
  2. acentos   a palavra que só existe acentuada no dicionário ganha o acento (politico → político);
  3. REPAROS   mudanças que também ocorrem em palavras atuais (ct, z/s, h mudo, ch grego…): só valem quando a palavra NÃO existe
               no dicionário e o resultado EXISTE. Sem isso "impacto" virava "impato" e "continue" virava "continui".
O que também existe sem acento, ou pode ser forma de verbo (pratica/prática), não é tocado: fica para o modelo e a revisão.
"""
import csv, functools, gzip, re
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PALAVRA = re.compile(r"[A-Za-zÀ-ÿ]+(?:[-'][A-Za-zÀ-ÿ]+)*")
# (padrão, troca): só mudanças regulares e seguras. Maiúscula inicial (nome próprio) fica de fora em palavra().
REGRAS = [(re.compile(p), t) for p, t in (
    (r'ph', 'f'), (r'rh', 'r'), (r'th', 't'), (r'y', 'i'),
    (r'(?<=[aeiou])ll(?=[aeiou])', 'l'), (r'mm', 'm'), (r'nn', 'n'), (r'tt', 't'), (r'pp', 'p'), (r'ff', 'f'), (r'cc(?=[aou])', 'c'), (r'gg', 'g'), (r'dd', 'd'), (r'bb', 'b'),
    (r'mpt', 'nt'), (r'^sc(?=[ie])', 'c'), (r"^d'", 'd'), (r"^n'", 'n'),
    (r'aes$', 'ais'), (r'ae$', 'ai'), (r'óe$', 'ói'), (r'^quasi$', 'quase'), (r'^póde$', 'pode'),
    # acento que as reformas tornaram obrigatório e que é regular pelo fim da palavra
    (r'encia(s?)$', r'ência\1'), (r'ancia(s?)$', r'ância\1'), (r'avel$', 'ável'), (r'ivel$', 'ível'), (r'uvel$', 'úvel'),
    (r'ario(s?)$', r'ário\1'), (r'orio(s?)$', r'ório\1'), (r'icio(s?)$', r'ício\1'),
)]
# Mudanças que também aparecem em palavra atual (pacto, continue, reza, casa…): cada uma só é aceita se a palavra de partida não existe e a de chegada existe.
REPAROS = [(re.compile(p), t) for p, t in (
    (r'(?<=[aeiou])ct(?=[aeiou])', 't'), (r'(?<![qg])ue$', 'ui'),                          # actual, director; possue, inclue
    (r'cç', 'ç'), (r'pç', 'ç'), (r'(?<=[aeiouóéí])pt', 't'),                                # acção, adopção, óptimo, escripto
    (r'(?<=[aeiou])h(?=[aeiou])', ''), (r'^h(?=[aeiou])', ''),                              # comprehender, prohibir, sahir; hontem, herva
    (r'(?<=[aeiou])hi', 'í'), (r'(?<=[aeiou])hu', 'ú'),      # o h marcava hiato: "ahi" é "aí", "sahia" é "saía". Com "ai" e "saia" também existindo, fica ambíguo e não é trocado
    (r'ãi(s?)$', r'ãe\1'),                                                                   # mãi
    (r'éia', 'eia'), (r'éa(s?)$', r'eia\1'), (r'ói(?=[acd])', 'oi'),                          # idéia, idéa, européa; heróico, jibóia
    (r'ezes$', 'eses'), (r'ez$', 'ês'), (r'eza(s?)$', r'esa\1'), (r'az$', 'ás'), (r'oz$', 'ôs'),      # portuguezes, mez, portugueza, atraz, poz
    (r'(?<=[aeiouáéíóú])z(?=[aeiou])', 's'), (r'(?<=[aeiou])s(?=[aeiou])', 'z'),            # apezar, empreza, quizer; realisar, civilisação
    (r'^e(?=[gdq])', 'i'),                                                                 # egual, edade, egreja
    (r'ch(?=[aourlnmt])', 'c'), (r'ch(?=[ei])', 'qu'),                                         # christão, technico; chimica, archivo
    (r'x(?=[tpcg])', 's'),                                                                 # extranho, exgotar, mixto
    (r'gn(?=[aeiou])', 'n'), (r'mn', 'n'), (r'gm', 'm'),                                    # signal, assignar; alumno, solemne; augmento
    (r'[âêô]', lambda m: {'â': 'a', 'ê': 'e', 'ô': 'o'}[m[0]]), (r'[èò]', lambda m: {'è': 'e', 'ò': 'o'}[m[0]]), (r'ü', 'u'),      # êle, tôda, sôbre; sòmente; freqüente
    (r'^k(?=[ei])', 'qu'), (r'ou', 'oi'),                                                   # kilo; cousa só se não existir (existe: fica)
)]
ANTIGA = re.compile(r"ph|th|mm|nn|tt|pp|ff|[aeiou]ll[aeiou]|y|mpt|aes$|[^qg]ue$|^d'", re.I)


def carrega(arq=AQUI / 'lexico.csv'):
    if not arq.exists():
        return {}
    with arq.open(encoding='utf-8') as f:
        return {r['antigo']: r['atual'] for r in csv.DictReader(f, delimiter=';')}


_ACENTOS = None


def acentos():
    """sem acento -> com acento, só para palavras que não existem sem ele (gerado por dicionario.py a partir do dicionário livre do LibreOffice)."""
    global _ACENTOS
    if _ACENTOS is None:
        arq = AQUI / 'acentos.csv.gz'
        _ACENTOS = {}
        if arq.exists():
            with gzip.open(arq, 'rt', encoding='utf-8') as f:
                _ACENTOS = {r['sem']: r['com'] for r in csv.DictReader(f, delimiter=';')}
    return _ACENTOS


# ---------- a palavra existe no português atual? ----------
_DIC = None


def _dicionario():
    """O dicionário livre do LibreOffice (VERO, pt_BR; LGPL 3 / MPL), lido inteiro, com as flexões, pela biblioteca spylls.
    Carrega uma vez, só quando é preciso (uns 10 s e 250 MB). Sem a biblioteca ou sem os arquivos, devolve False."""
    global _DIC
    if _DIC is None:
        try:
            from spylls.hunspell import Dictionary
            _DIC = Dictionary.from_files(str(AQUI / 'dic' / 'pt_BR'))
        except Exception:      # noqa: BLE001
            _DIC = False
    return _DIC


@functools.lru_cache(maxsize=300_000)
def existe(w):
    """A palavra é do português atual? True/False pelo dicionário; None se ele não está disponível (aí ninguém decide nada por ele).
    Medido em 07/10/2026: desfazer flexões por regra caseira deixava 12,6% das palavras de um livro atual de fora; a leitura completa resolve."""
    d = _dicionario()
    if not d:
        return None
    b = w.lower()
    return len(b) < 3 or "'" in b or bool(d.lookup(b))


def desconhecidas(texto):
    """Palavras do texto (minúsculas, 4+ letras) que não são do português atual: grafia antiga que sobrou, erro de leitura ou palavra de outra língua.
    Nomes próprios (maiúscula) ficam de fora. Sem o dicionário, lista vazia."""
    if existe('casa') is None:
        return []
    return sorted({w for w in PALAVRA.findall(texto) if len(w) >= 4 and not w[:1].isupper() and not existe(w)})


def _caixa(modelo, w):
    return w.upper() if modelo.isupper() and len(modelo) > 1 else w.capitalize() if modelo[:1].isupper() else w


def _repara(n):
    """Grafia antiga que as regras gerais não alcançam: um reparo (ou dois seguidos) só vale se chegar a uma palavra que existe,
    e só se chegar a UMA: "cousa" poderia ser "coisa" ou "couza", então fica como está e é apontada."""
    def passo(palavras):
        return {acentos().get(c, c) for p in palavras for padrao, troca in REPAROS for c in [padrao.sub(troca, p)] if c != p}
    um = passo([n])
    for cands in (um, passo(um)):
        validas = {c for c in cands if existe(c)}
        if validas:
            return validas.pop() if len(validas) == 1 else n
    return n


def palavra(w, lexico):
    """Uma palavra em grafia atual. Léxico tem prioridade; nome próprio fora do léxico não é tocado."""
    b = w.lower()
    if b in lexico:
        return _caixa(w, lexico[b])
    if w[:1].isupper() and not w.isupper():
        return w
    n = b
    for padrao, troca in REGRAS:
        n = padrao.sub(troca, n)
    sabe = existe(n)
    if sabe is False:            # a palavra não existe: primeiro o acento que falta, depois os reparos de grafia
        com = acentos().get(n)
        n = com if com and existe(com) else _repara(n)
    elif sabe is None:           # sem dicionário: o que já era feito antes de ele existir
        n = acentos().get(n, n)
        n = re.sub(r'(?<![qg])ue$', 'ui', re.sub(r'(?<=[aeiou])ct(?=[aeiou])', 't', n))
    return _caixa(w, n)


def moderniza(texto, lexico=None):
    """Devolve (texto atualizado, [(antigo, atual), …] na ordem em que aparecem)."""
    lexico = carrega() if lexico is None else lexico
    trocas = []

    def troca(m):
        n = palavra(m[0], lexico)
        if n != m[0]:
            trocas.append((m[0], n))
        return n
    return PALAVRA.sub(troca, texto), trocas


def sobras(texto):
    """Palavras do texto que ainda parecem estar em grafia antiga (para a revisão apontar). Nomes próprios ficam de fora."""
    return sorted({w for w in PALAVRA.findall(texto) if not w[:1].isupper() and ANTIGA.search(w)})


if __name__ == '__main__':
    t, tr = moderniza('O programma politico delle, com theoria e philosophia; Thyssen e a ACÇÃO.', {'politico': 'político', 'delle': 'dele', 'acção': 'ação'})
    assert t == 'O programa político dele, com teoria e filosofia; Thyssen e a AÇÃO.', t
    assert ('programma', 'programa') in tr and len(tr) == 6
    assert palavra('que', {}) == 'que' and palavra('possue', {}) == 'possui' and palavra('naturaes', {}) == 'naturais' and palavra('agencias', {}) == 'agências'
    assert sobras('O programma politico de Thyssen, que possue philosophia.') == ['philosophia', 'possue', 'programma']
    if existe('casa') is not None:
        # palavra atual não é estragada (medido num romance de época: "disse" virava "dissê", "impacto" virava "impato")
        for w in ('continue', 'impacto', 'pacto', 'compacto', 'convicto', 'atue', 'beleza', 'casa', 'apesar', 'reza', 'chama', 'homem', 'sobre', 'você', 'disse', 'fez', 'sala', 'queria'):
            assert palavra(w, {}) == w, (w, palavra(w, {}))
        # grafia antiga que só o dicionário deixa consertar com segurança
        for antiga, atual in (('actual', 'atual'), ('director', 'diretor'), ('comprehender', 'compreender'), ('prohibir', 'proibir'), ('sahir', 'sair'), ('hontem', 'ontem'),
                              ('portuguez', 'português'), ('mezes', 'meses'), ('apezar', 'apesar'), ('empreza', 'empresa'), ('realisar', 'realizar'), ('civilisação', 'civilização'),
                              ('egual', 'igual'), ('edade', 'idade'), ('christão', 'cristão'), ('chimica', 'química'), ('technico', 'técnico'), ('extranho', 'estranho'),
                              ('alumno', 'aluno'), ('augmento', 'aumento'), ('êle', 'ele'), ('tôda', 'toda'), ('sòmente', 'somente'), ('freqüente', 'frequente'),
                              ('acção', 'ação'), ('adopção', 'adoção'), ('óptimo', 'ótimo'), ("n'um", 'num'), ('tranquillisar', 'tranquilizar'), ('inclue', 'inclui'),
                              ('idéa', 'ideia'), ('sahida', 'saída'), ('mãi', 'mãe')):
            assert palavra(antiga, {}) == atual, (antiga, palavra(antiga, {}))
        assert palavra('ahi', {}) == 'ahi'      # "ai" ou "aí": ambíguo, não é trocado
        assert desconhecidas('O homem compreende a idéa, mas o frent não; Thyssen sabe.') == ['frent', 'idéa']
    print('ok')
