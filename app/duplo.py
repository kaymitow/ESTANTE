"""Dois modelos que conversam: A propõe, B audita, A revisa se B achar problema.

Fluxo por item (tradução, atualização de português, limpeza de OCR, leitura de página):
  1. A produz o resultado.
  2. Checagens automáticas: recusa/aviso moralizante, tamanho (omissão ou invenção), números e nomes da fonte.
  3. B (outro modelo) recebe a FONTE e o resultado de A e responde se há omissão, suavização, erro de número/nome ou acréscimo.
  4. Se B apontar problemas, A revisa uma vez com a crítica de B; B audita de novo.
  5. Status final: "aprovado" (tudo limpo), "revisar" (alguma checagem falhou ou os dois seguem discordando).
Nada é gravado aqui: o resultado vai para a fila de revisão e só o usuário aceita.
"""
import json, math, re, sys, threading, time, unicodedata, urllib.request
from pathlib import Path
from collections import Counter
from difflib import SequenceMatcher

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'ferramentas' / 'ortografia'))
import classico   # noqa: E402  (motor clássico de tradução, opcional)
import motor   # noqa: E402  (llama.cpp: sobe o modelo pedido e troca quando preciso)
import regras   # noqa: E402  (grafia do português antigo: léxico + regras, sem modelo)

A_PADRAO = 'qwen3-vl:30b-a3b-instruct'      # dupla "qualidade máxima" (não cabe em 12 GB de placa; ~2,4x mais lenta)
B_PADRAO = 'gemma4:26b'
# dupla rápida, medida em docs/benchmark (régua de 07/10/2026): mesma semelhança da dupla grande, 13,8 contra 33,8 s por mil caracteres
TRADUTOR = 'translategemma:12b'
OCR = 'glm-ocr:latest'      # leitor dedicado de 0,9 B (2,2 GB), 5 s por página. Fica como SEGUNDO leitor (conferência): ele acerta mais palavras,
                            # mas às vezes moderniza a grafia por conta própria e deixa cabeçalho e sobra no fim; o texto que entra no livro é o do primeiro leitor
LEVE = 'qwen3-vl:8b-instruct'               # nos testes empatou com o de 30B em leitura de página, alemão e português antigo


def padrao(papel, tem):
    """Modelo usado num papel quando o usuário não escolheu um: o melhor entre os instalados (tem = nomes no Ollama)."""
    ordem = {'tradutor': (TRADUTOR, A_PADRAO, LEVE), 'geral': (LEVE, A_PADRAO), 'auditor': (LEVE, B_PADRAO), 'leitor': (LEVE, A_PADRAO, B_PADRAO),
             'leitor2': (OCR, B_PADRAO, A_PADRAO, LEVE), 'juiz': (A_PADRAO, B_PADRAO, LEVE)}.get(papel)
    if not ordem:
        return None      # papel sem padrão (votante): vazio = o juiz faz as duas coisas
    # o auditor e o segundo leitor devem ser, se possível, um modelo diferente de quem propõe
    if papel == 'auditor' and TRADUTOR not in tem:
        ordem = (B_PADRAO, LEVE)
    return next((m for m in ordem if m in tem), ordem[0])


def escolhe(tarefa):
    """(proponente, auditor) para a tarefa: o que o usuário definiu na tela Modelos; senão, o melhor entre os instalados."""
    import config
    papeis = config.le()['papeis']
    tem = motor.nomes()
    a, b =('leitor', 'leitor2') if tarefa == 'ler_pagina' else ('tradutor', 'auditor') if tarefa.startswith('traduzir') else ('geral', 'auditor')
    ma, mb = papeis.get(a) or padrao(a, tem), papeis.get(b) or padrao(b, tem)
    if ma == mb and not papeis.get(b):          # quem confere não deve ser quem propôs, se houver outro instalado
        mb = next((m for m in (B_PADRAO, A_PADRAO) if m in tem and m != ma), mb)
    return ma, mb


# Recusa "forte": vale em qualquer ponto do texto. Recusa "fraca" (desculpa, sinto muito…): só conta no começo da resposta,
# porque essas palavras aparecem normalmente dentro do texto dos livros.
RECUSA = re.compile(r"(n[ãa]o posso (ajudar|traduzir|atender|fornecer)|n[ãa]o (me )?sinto confort|i can'?t (help|assist|translate)|"
                    r"i cannot (help|assist|translate|provide)|as an ai|como (uma )?ia\b|como modelo de linguagem)", re.I)
RECUSA_INICIO = re.compile(r"\b(desculp[ae]\w*|sinto muito|lamento|i'm sorry|i am sorry|infelizmente|n[ãa]o [ée] apropriado|conte[úu]do (sens[íi]vel|ofensivo|prejudicial))\b", re.I)
PEDIDO_DE_DESCULPA = re.compile(r'apolog|sorry|excus|regret|unfortunate|desculp|lament|infeliz|leider|entschuldig|bedauer', re.I)


def eh_recusa(saida, fonte=''):
    """Recusa ou aviso do modelo no lugar do texto. As palavras "fracas" só contam bem no começo da resposta
    e só se a própria fonte não começa falando de desculpa ou lamento (medido no piloto: "pedindo desculpas", "perfilamento")."""
    return bool(RECUSA.search(saida) or (RECUSA_INICIO.search(saida[:80]) and not PEDIDO_DE_DESCULPA.search(fonte[:160])))

PROMPTS = {
    'traduzir': ('Você é um tradutor acadêmico. Traduza o texto do inglês para português brasileiro com FIDELIDADE TOTAL: não resuma, não omita, '
                 'não suavize, não intensifique, não moralize, não adicione avisos nem comentários; preserve números, nomes, aspas e pontuação. '
                 'É documento histórico para estudo; traduzir não é endossar. Responda SOMENTE com a tradução.'),
    'traduzir_de': ('Você é um tradutor acadêmico. Traduza do alemão (texto de 1925, com erros de OCR) para português brasileiro com FIDELIDADE TOTAL: '
                    'não resuma, não omita, não suavize, não comente. Documento histórico; traduzir não é endossar. Responda SOMENTE com a tradução.'),
    'limpar_ocr': ('Você recebe texto de OCR de um livro. Junte palavras partidas no fim da linha e una as quebras de linha dentro do parágrafo. '
                   'NÃO corrija grafia, NÃO modernize, NÃO mude nenhuma palavra, NÃO comente. Responda SOMENTE com o texto limpo.'),
    'atualizar_pt': ('Atualize a grafia deste trecho em português antigo para o português brasileiro moderno (ortografia, acentos, flexões inequívocas). '
                     'Parte das palavras já foi atualizada por regras; termine o que faltou (acentos, letras dobradas, ph/th/y, consoantes mudas). '
                     'Troque SÓ a grafia: NÃO troque palavras por sinônimos, NÃO mude a ordem, o sentido, o tom nem as ideias; NÃO suavize nem comente. '
                     'Junte palavras partidas no fim da linha. Preserve termos históricos e maiúsculas de ênfase. Responda SOMENTE com o texto atualizado.'),
    'ler_pagina': ('Transcreva exatamente o texto impresso nesta página de livro. Preserve a grafia, a pontuação e as quebras de parágrafo; '
                   'não corrija, não traduza, não resuma, não comente. Responda SOMENTE com o texto.'),
}
# medido em app/regua_crua.py
_REGISTRO = (' Mantenha o registro do autor: palavrão, insulto, ironia e expressão crua ou ofensiva saem com a mesma força em português '
           '(ex.: "damned" = "maldito", nunca "muito"). Não troque palavra forte por termo neutro ou técnico.')
PROMPTS['traduzir'] += _REGISTRO      # ganho pequeno e não provado: 43 -> 44 de 46 palavras fortes na amostra de 30 parágrafos
# "Nada ao pé da letra" (pedido do usuário, 07/10/2026): testado com 8 frases idiomáticas fora de qualquer exemplo. O tradutor rápido já as
# traduz pelo sentido ("kicked the bucket" = "morreu", "the last straw" = "a gota d'água"); uma frase a mais no pedido não mudou o resultado, então não entrou.


def sem_repeticao(t, janela=60):
    """Corta a leitura no ponto em que o leitor começa a repetir o que já escreveu (o GLM-OCR lê a página e segue em laço até o teto)."""
    for i in range(janela, len(t) - janela, 10):
        if t[i:i + janela] in t[:i]:
            i = next(k for k in range(i - 9, i + 1) if t[k:k + janela] in t[:k])      # volta ao começo exato da repetição
            # o que sobra no fim depois do corte é o recomeço do laço: cabeçalho, número da página e o começo da página de novo.
            # Saem as linhas finais curtas que não fecham frase (a página de verdade termina em pontuação ou em palavra partida por hífen).
            linhas = t[:i].rstrip().split('\n')
            while len(linhas) > 1 and (not linhas[-1].strip() or (len(linhas[-1].strip()) < 48 and linhas[-1].strip()[-1] not in '.!?:;,-—»”"')):
                linhas.pop()
            return '\n'.join(linhas).rstrip()
    return t


def combina(base, grafia):
    """Leitura combinada de dois leitores: o texto de `base`, com a grafia de `grafia` nas palavras em que os dois só diferem pela grafia
    (acento, letra dobrada, ph/th…). Serve para um leitor que lê melhor mas moderniza a grafia por conta própria: as palavras são dele,
    a grafia da página vem do outro. Onde os dois leem palavras diferentes, fica a de `base`."""
    pb, pg = re.findall(r'\S+', base), re.findall(r'\S+', grafia)
    eb, eg = [_esqueleto(re.sub(r'\W', '', w)) for w in pb], [_esqueleto(re.sub(r'\W', '', w)) for w in pg]
    out = list(pb)
    for op, a0, a1, b0, b1 in SequenceMatcher(None, eb, eg, autojunk=False).get_opcodes():
        if op == 'equal':
            out[a0:a1] = pg[b0:b1]
    # as quebras de parágrafo são as da leitura de base
    it = iter(out)
    return re.sub(r'\S+', lambda _: next(it), base)


def tesseract(imagem, idioma='por'):
    """Leitura da página pelo Tesseract (leitor clássico, sem modelo), se estiver instalado; senão None. Só para conferência."""
    import shutil, subprocess
    exe = shutil.which('tesseract') or next((str(c) for c in (Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe'),) if c.exists()), None)
    dados = Path(__file__).resolve().parent.parent / 'ferramentas' / 'tessdata'
    if not exe or not (dados / f'{idioma}.traineddata').exists():
        return None
    r = subprocess.run([exe, 'stdin', 'stdout', '--tessdata-dir', str(dados), '-l', idioma, '--psm', '3'], input=imagem, capture_output=True, timeout=120)
    return r.stdout.decode('utf-8', 'replace').strip() if r.returncode == 0 else None


def pedido_leitura(modelo):
    """Leitores dedicados só entendem o próprio comando; os gerais recebem o pedido completo."""
    return 'Text Recognition:' if 'glm-ocr' in modelo else PROMPTS['ler_pagina']


PARALELO = motor.PARALELO      # pedidos simultâneos ao motor (o regua.py lê daqui)
CTX = motor.CTX                # tokens de contexto por pedido
GPU = threading.BoundedSemaphore(PARALELO)      # fila, pipeline e pedidos avulsos não disputam a placa além disso


FORA = 'fora'     # nome do "modelo de fora" nos papéis
AO_VIVO = {}      # o que o modelo está escrevendo agora (para a tela mostrar o trabalho acontecendo)


def chat(modelo, mensagens, imagens=None, num_predict=2000, vivo=None, corta_repeticao=False, pedacos=None):
    """vivo = dados para a tela acompanhar (papel, fonte…); a resposta chega aos poucos e vai sendo guardada em AO_VIVO.
    pedacos = lista que recebe cada pedaço gerado com a probabilidade dele e das alternativas (o Ollama devolve; o modelo de fora, não)."""
    if modelo == FORA:                       # modelo pela internet, com endereço e chave do usuário (Configurações → Rede)
        if imagens:
            raise RuntimeError('o modelo de fora não lê páginas; escolha um modelo local como leitor')
        import rede
        if vivo is not None:
            AO_VIVO.clear(); AO_VIVO.update(vivo, modelo='modelo de fora', texto='', inicio=time.time())
        saida = rede.conversa_fora(mensagens, num_predict)
        if vivo is not None:
            AO_VIVO['texto'] = saida
        return saida
    corpo = {'messages': mensagens, 'stream': True, 'temperature': 0, 'max_tokens': num_predict, **motor.amostragem(modelo)}
    if imagens:       # a página do leitor vai como imagem numa parte da última mensagem
        ultima = mensagens[-1]
        corpo['messages'] = mensagens[:-1] + [{'role': ultima['role'], 'content': [{'type': 'text', 'text': ultima['content']}] +
                                               [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + b}} for b in imagens]}]
    if pedacos is not None:
        corpo.update(logprobs=True, top_logprobs=8)
    partes = []
    GPU.acquire()
    try:
        porta = motor.sobe(modelo)      # carrega o modelo (troca o atual, se preciso) e espera ele responder
        try:
            r = urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{porta}/v1/chat/completions', json.dumps(corpo).encode(),
                                                              {'Content-Type': 'application/json'}), timeout=900)
        except urllib.error.HTTPError as ex:      # o motor explica no corpo (contexto cheio, pedido inválido…)
            raise RuntimeError(f'{modelo}: {ex.read().decode("utf-8", "replace")[:400]}') from None
    except BaseException:
        GPU.release(); raise
    try:
        if vivo is not None:
            AO_VIVO.clear(); AO_VIVO.update(vivo, modelo=modelo, texto='', inicio=time.time())
        for linha in r:      # SSE: uma linha "data: {...}" por pedaço, e "data: [DONE]" no fim
            linha = linha.decode('utf-8', 'replace').strip()
            if not linha.startswith('data:') or linha == 'data: [DONE]':
                continue
            d = json.loads(linha[5:])
            if d.get('error'):
                raise RuntimeError(f"{modelo}: {d['error'].get('message', d['error'])}")
            escolha = d['choices'][0] if d.get('choices') else {}
            partes.append((escolha.get('delta') or {}).get('content') or '')
            if pedacos is not None:
                pedacos.extend((escolha.get('logprobs') or {}).get('content') or [])
            if corta_repeticao and len(partes) % 40 == 0 and sem_repeticao(''.join(partes)) != ''.join(partes):
                break                      # o leitor entrou em laço: fechar a conexão interrompe a geração
            if vivo is not None:
                AO_VIVO['texto'] = ''.join(partes)
    finally:
        r.close(); GPU.release()
    return (sem_repeticao(''.join(partes)) if corta_repeticao else ''.join(partes)).strip()


def romano(n):
    if not 0 < n < 4000:
        return '(?!)'
    r = ''
    for v, c in ((1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')):
        r += c * (n // v); n %= v
    return r


def numeros(s):
    return set(re.findall(r'\d+', MARCA.sub('', s)))      # os números das marcas (<a1>) não são do texto


MARCA = re.compile(r'</?[aib]\d+>|<n\d+/>|<br>')      # marcas postas por pipeline.mascara: têm de voltar todas, iguais
# Alertas objetivos: nem o juiz libera, só consertando (decisão do usuário em 07/10/2026). Itálico, quebra de linha, negação, tamanho,
# frase a mais e palavra forte o juiz pode liberar, conferindo contra a fonte.
TRAVAS = ('número da fonte', 'menos frases', 'idioma da fonte', 'recusa', 'inventado', 'resultado vazio', 'comentário do modelo', 'glossário:')


def trava(problema):
    return any(t in problema for t in TRAVAS) or ('marcação diferente' in problema and bool(re.search(r'</?a\d|<n\d', problema)))      # link ou nota perdidos


def ajusta(fonte, saida):
    """Conserto mecânico, sem mexer em palavra: tira o ponto final que o modelo acrescenta a título ou linha que não tinha,
    e o itálico ou negrito que o modelo pôs por conta própria num trecho que não tinha nenhum."""
    f, s = fonte.rstrip(), saida.strip()
    if f and s.endswith('.') and not s.endswith('..') and (f[-1].isalnum() or f[-1] in '’\''):
        s = s[:-1].rstrip()
    if '*' not in f and '*' in s:
        s = s.replace('*', '')
    return re.sub(r'</?[ib]\d+>', '', s) if not re.search(r'<[ib]\d+>', f) else s


FRASE = re.compile(r'(?<=[.!?…])["”’»)\]*]*\s+(?=["“‘«(\[*]*[A-ZÀ-Ý0-9])')
COMUNS = {'en': set('the of and to that is in it for with as was be this are not by on or which they have from their'.split()),
          'de': set('der die und das ist nicht den von zu mit sich des dem ein eine auch als wir sie für auf'.split()),
          'pt': set('de que não uma para com os das dos como mais se em por é ao as do da no na um e o a'.split())}
ORIGEM = {'traduzir': 'en', 'traduzir_de': 'de'}

# Leitura crítica (sem modelo): onde a tradução tem mais chance de sair errada. Só sinais da fonte inglesa, lista própria e curta.
# Medido ou não: ver docs/roteiro-historico.md (a ordem só entra se separar os blocos que o usuário corrigiu).
VERBOS_COMUNS = set('get got put take took give gave look come came go went make made set turn break bring call carry check cut drop fall hold keep let pick pull push run show sit stand wake walk work wear write fill fix pay pass hand sort step shut throw'.split())
_VERBO_PARTICULA = re.compile(r"\b([A-Za-z]+)\s+(up|off|out|down|over|away|back)\b", re.I)
_ITALICO_OU_EXCLAMACAO = re.compile(r"[*_][^*_\n]+[*_]|!")
_FALA_CURTA = re.compile(r"[\"“”][^\"“”\n]{1,60}[\"“”]")


def _e_verbo(palavra: str) -> bool:
    """A palavra é um dos verbos comuns, em qualquer forma simples (take, takes, took, turned, turning)."""
    w = palavra.lower()
    if w in VERBOS_COMUNS:
        return True
    cortes = [w[:-1] if w.endswith('s') else w, w[:-2] if w.endswith('ed') else w, w[:-1] if w.endswith('d') else w,
              w[:-3] if w.endswith('ing') else w, w[:-3] + 'e' if w.endswith('ing') else w]
    return any(c in VERBOS_COMUNS for c in cortes) or any(v + 'ed' == w or v + 'ing' == w for v in VERBOS_COMUNS)


def risco(origem: str) -> tuple[int, list[tuple[int, int, str]]]:
    """Nota de risco de um bloco da fonte (número de sinais) e os trechos com o motivo de cada um: (início, fim, motivo)."""
    trechos = [(m.start(), m.end(), 'verbo + partícula') for m in _VERBO_PARTICULA.finditer(origem) if _e_verbo(m.group(1))]
    trechos += [(m.start(), m.end(), 'itálico ou exclamação') for m in _ITALICO_OU_EXCLAMACAO.finditer(origem)]
    trechos += [(m.start(), m.end(), 'frase curta em fala') for m in _FALA_CURTA.finditer(origem) if len(m.group(0).split()) <= 6]
    return len(trechos), sorted(trechos)
COMENTARIO = re.compile(r'\b(traduzid[oa]s? como|foi traduzid[oa]|a tradução|nota do tradutor|N\. ?do ?T\.|o revisor|na fonte original|texto original diz)\b', re.I)
COMENTARIO_NA_FONTE = re.compile(r'translat|übersetz|reviewer|original text', re.I)
NEGA = {'en': re.compile(r"\b(not|no|never|nor|neither|cannot|nothing|none|nobody|without)\b|n't", re.I),
        'de': re.compile(r'\b(nicht|kein\w*|nie|niemals|nichts|niemand|weder|ohne)\b', re.I),
        'pt': re.compile(r'\b(não|nunca|nem|jamais|nada|nenhum|nenhuma|ninguém|sem)\b', re.I)}


# Palavra forte do inglês -> radicais que a mantêm fortes em português. Se a fonte tem a palavra e o resultado não tem nenhum radical, o bloco é apontado.
# ponytail: lista fixa, só inglês e só palavra isolada; não vê abrandamento por paráfrase. Medida em app/regua_crua.py; ampliar a lista conforme os casos reais.
FORTES = [(re.compile(rf'\b({en})\b', re.I), re.compile(pt, re.I)) for en, pt in (
    (r'damn(ed)?|goddamn(ed)?', r'maldi|danad|desgraç|diab|porra|droga|amaldiço|pra valer'),
    (r'hell', r'infern|diabo'), (r'(bull)?shit\w*|crap', r'merda|bosta|porcaria|cagad'), (r'fuck\w*', r'fod|porra|caralh|merda|ferr'),
    (r'bastards?', r'bastard|desgraçad|canalha|put'), (r'idiot\w*|morons?|moronic|cretin\w*|imbecil\w*', r'idiot|imbec|cretin|estúpid|retardad|débil'),
    (r'stupid\w*', r'estúpid|estupid|idiot|burr|imbec'), (r'scum', r'escória|ralé|escum'), (r'filth\w*', r'imund|sujeir|porcaria|nojent|obscen'),
    (r'vile', r'\bvil\b|\bvis\b|repugn|abjet|desprez|torpe'), (r'malodorous|stink\w*|stench|stank|reek\w*', r'fed[eoi]|fétid|malcheiros|podr|catinga|odor|cheir'),
    (r'slaughter\w*|massacr\w*', r'massacr|matança|abat|chacin|carnific'), (r'genocid\w*', r'genoc'),
    (r'rap(e[ds]?|ing|ists?)', r'estupr|violent|violaç'), (r'murder\w*', r'assassin|homic|mata'), (r'terror', r'terror'),
    (r'hat(e[ds]?|ing|red|eful)', r'odi|ódio|odei|detest|rancor'), (r'loath\w*', r'abomin|detest|odi|ódio|repugn|nojo|aversão'),
    (r'despis\w*|contempt\w*', r'desprez|detest|desdém|desdenh'), (r'disgust\w*', r'nojo|nojent|repugn|repuls|asco|enoj'),
    (r'savage\w*', r'selvag|bárbar|feroz|ferocid'), (r'barbar\w+', r'b[áa]rb[áa]r'), (r'degenera\w*', r'degener'), (r'parasit\w*', r'paras[ií]t'),
    (r'vermin', r'verme|praga|parasit'), (r'whor\w+|sluts?', r'put|prostitu|meretriz|vadia|vagabund'), (r'retard(ed|s)?', r'retard'),
    (r'lunatic\w*|insan\w+', r'lunátic|louc|insan|dement|malu'), (r'zombi\w*', r'zumbi'), (r'cannibal\w*', r'cann?ibal'), (r'slave\w*', r'escrav'),
    (r'tyran\w+', r'tiran'), (r'ugl(y|iness|ier|iest)', r'fei|horr|horrend'), (r'horr(or|ors|ible|ibly|ific|endous)', r'horr|terrív|pavor|medonh'),
    (r'atroci\w+', r'atroc'), (r'brutal\w*', r'brut'), (r'evil\w*', r'\bmal\b|\bmales\b|malign|pervers|maldade|malvad|\bmau\b|\bmaus\b|\bmá\b|\bmás\b|maléf|diab'),
    (r'catastroph\w+', r'cat[áa]str[óo]f|desastr'), (r'garbage|trash', r'lixo|porcaria'), (r'kill(s|ed|ing|ers?)?', r'\bmat[aoe]|assassin|mort|extermin'),
    (r'thug\w*', r'bandid|marginal|capanga|brutamont|delinq|vândal'), (r'dement\w+', r'dement|louc|insan'), (r'pervert\w*|perver[st]\w+', r'pervers|pervert|deprav|tarad'),
    # ampliação de 07/10/2026, com os casos lidos no piloto e no gabarito do juiz; falso alarme conferido em app/regua_erros.py e nos blocos aprovados do piloto
    (r'losers?', r'perdedor|fracassad|derrotad|otári|zé-ningu'), (r'dupes?', r'otári|tol[oa]s?\b|trouxa|ingênu|ludibri|engan|papalv|idiot|iludid|manobra'),
    (r'dirty?', r'suj|imund|porcari|podr|lama|baixari|obscen|sórdid|terra|chão|poeira|barro'), (r'purg(e[ds]?|ing)', r'expurg|purg|depur|limp|elimin|extirp'),
    (r'obnoxious', r'repugn|odios|detest|insuport|desagrad|irritant|ofensiv|nojent|abomin|execr'),
    (r'(out)?rage[ds]?|raging|enraged|outrageous', r'fúri|furi|raiva|\bira\b|cólera|indign|ultraj|revolt|escândal|escandal|absurd'),
    (r'crush(ed|es|ing)?', r'esmag|tritur|aniquil|destr[uo]|derrot|massacr|arras|sufoc|oprim'),
    (r'destroy(s|ed|ing|ers?)?|destruction|destructive', r'destru|destro|aniquil|arras|arruin|acab|devast'),
    (r'suffer(s|ed|ing|ings)?', r'sofr|padec|\bpenar|aguent|suport|amarg'), (r'violen(t|ce|tly)', r'violen|violên|brutal|agress'),
    (r'humiliat\w+', r'humilh|vexa|rebaix|degrad'), (r'disast(er|ers|rous|rously)', r'desastr|cat[áa]str[óo]f|calamid|tr[áa]g|ruín|ruin'),
    (r'scorn\w*', r'desprez|esc[áa]rn|desdém|desdenh|zomb'), (r'corrupt\w*', r'corrup|corromp|podr|deprav|vicia|suborn'),
    (r'cowards?|cowardly|cowardice', r'covard|medros|poltr'), (r'traitors?|treason\w*|betray\w*', r'trai[dçr]|traiç|traíd|revel|denunci|evidenc|mostr|entreg|delat'), (r'liars?', r'mentiros|mentir'),
    (r'fools?|foolish\w*', r'tol[oa]|idiot|est[úu]pid|bob[oa]|imbec|insensat|néscio|parvo|burr|louc|ridícul|engan'), (r'ignoran(t|ce)', r'ignor'),
    (r'racis[tm]s?', r'racis'), (r'fascis[tm]s?', r'fascis'), (r'nazis?m?', r'nazi'), (r'bigot\w*', r'intoler|preconceit|fan[áa]t|sectár|bigot|carola|racis'),
    (r'nigg(er|ers|a|as)', r'crioul|negr|neguinh|pret[oa]s?\b|macac'), (r'fagg?ots?', r'bich[ao]|viad|maric|boiola'),
    (r'bitch(es)?', r'vadia|cadela|put|megera|vaca|desgraçad'), (r'cunts?', r'bucet|vadia|put|xoxot|desgraçad|vagabund'),
    (r'assholes?|arseholes?', r'cuz[ãa]o|cuzões|babaca|idiot|escrot|otári|imbec|canalha|desgraçad'), (r'piss(ed|es|ing)?', r'mij|put[oa]|irrit|merda|emput|furi|raiva'),
    # expressões (a lista já não vê só palavra isolada)
    (r'good riddance', r'vai tarde|foi tarde|ainda bem|que bom que|livr|bons ventos|sem saudade'), (r'sons? of (a )?bitch(es)?', r'filh[oa]s? d[ae] put|desgraçad|canalha'),
    (r'shut up', r'cal[ae]|calem|quiet'),
)]

# Alemão. Sem livro alemão traduzido na estante, o falso alarme desta lista só foi medido em amostra pequena (docs/benchmark/crua-*-alemao.md):
# os radicais em português aceitam de propósito muitas saídas, para errar por omissão e não por alarme.
FORTES_DE = [(re.compile(rf'\b({de})\b', re.I), re.compile(pt, re.I)) for de, pt in (
    (r'verdammt\w*|verflucht\w*|Fluch\w*', r'maldi|danad|amaldiço|desgraç|diab|praga|pragu'), (r'Hölle\w*|höllisch\w*', r'infern|diab'),
    (r'Schei(ß|ss)\w*|Dreck\w*|Mist', r'merda|bosta|porcaria|imund|suj|lixo|excrement|esterc|lama'), (r'Schwein\w*|Säue?', r'porc|suín|canalha|imund'),
    (r'Hure\w*|Dirne\w*', r'put|prostitu|meretriz|rameira|vadia'),
    (r'Lump\w*|Schuft\w*|Schurke\w*|Halunke\w*|Gauner\w*', r'canalha|patife|velhac|pulha|safad|bandid|trapaceir|vigarist|malandr|biltre|vil'),
    (r'Gesindel|Pöbel\w*|Abschaum|Auswurf', r'ralé|escória|gentalha|canalha|populacho|plebe|turba|escum|refugo|gentinha'),
    (r'Parasit\w*|Schmarotzer\w*|Blutsauger\w*|Ungeziefer|Schädling\w*', r'paras[ií]t|sanguessug|verme|praga|chup|nociv|daninh'),
    (r'Verräter\w*|Verrat\w*|verraten\w*', r'trai[dçr]|traiç|traíd'), (r'Feigling\w*|feige\w*|Feigheit', r'covard|pusil'),
    (r'Lügner\w*|Lüge\w*|verlogen\w*|Betrüger\w*|(?-i:Betrugs?)|Betrügerei\w*|betrüg\w*|Schwindel\w*|Schwindler\w*', r'mentir|mentiros|engan|fraud|trapaç|burl|embust|falcatru|vigar|logr|impostor|charlat'),
    (r'Mord\w*|Mörder\w*|ermord\w*', r'assassin|homic|mort|mata'),
    (r'vernicht\w*|ausrott\w*|ausmerz\w*|zerstör\w*|zertrümmer\w*|zerschlag\w*', r'aniquil|extermin|destru|destro|elimin|erradic|arras|esmag|despedaç|extirp|arruin|desmantel'),
    (r'Hass|Haß|hass\w+|haß\w+|gehass\w*|gehaß\w*|verhass\w*|verhaß\w*', r'ódio|odi[ao]|odei|detest|rancor|execr'), (r'veracht\w*|verächtlich\w*', r'desprez|desdém|desdenh'),
    (r'Ekel\w*|ekelhaft\w*|widerlich\w*|Abscheu\w*|abscheulich\w*', r'nojo|nojent|repugn|repuls|asco|abomin|horr|execr|avers'),
    (r'Schande\w*|schändlich\w*|Schmach\w*|schmachvoll\w*|schamlos\w*', r'vergonh|inf[âa]m|ignom[íi]n|desonr|opróbr|ultraj|descarad|despudor|afront|vexa|esc[âa]ndal|abomin|torpe|indign|vil\b|vis\b'),
    (r'entartet\w*|Entartung\w*', r'degener'), (r'minderwertig\w*|Minderwertigkeit\w*', r'inferior'),
    (r'Sklave\w*|Sklaverei|versklav\w*|Knechtschaft|Knecht\w*|knecht\w*|geknecht\w*', r'escrav|serv[oia]|servid|jugo|subjug|capacho|lacai|cativ|vassal|criad'),
    (r'Tyrann\w*', r'tiran'), (r'Bestie\w*|bestialisch\w*|viehisch\w*', r'best[ai]|fera|animal|brut'),
    (r'dumm\w*|Dummheit\w*|Dummkopf\w*|Idiot\w*|Trottel\w*|Narr|Narren|blöd\w*', r'burr|est[úu]pid|idiot|imbec|tol[oa]|parvo|néscio|bob[oa]|palerm|insensat|asn'),
    (r'grausam\w*|Grausamkeit\w*|brutal\w*|Brutalität\w*|Greuel\w*|Gräuel\w*', r'cruel|crueld|brut|atroc|horr|barbár|barbar|ferocid|feroz'), (r'Wucher\w*', r'usur|agiot|especul|açambarc|extors|ganânc'),
    (r'Pest|Seuche\w*|verpest\w*|Gift\w*|vergift\w*|giftig\w*', r'peste|praga|pestil|venen|epidem|flagel|infest|empest|tóxic|toxic|contamin'),
    (r'verfault\w*|Fäulnis|morsch\w*|verkommen\w*|verrott\w*', r'podr|apodrec|p[úu]tr|corromp|corrup|decad|carcom|deprav|degrad'),
    (r'Raub\w*|Räuber\w*|plünder\w*|ausplünder\w*|Plünderung\w*|ausbeut\w*|Ausbeut\w*', r'roub|ladr|saque|pilh|rapin|espoli|explor|despoj|rapac'),
    (r'erbärmlich\w*|jämmerlich\w*|elend\w*|Elend\w*', r'mis[ée]r|lastim|deplor|desgraç|penos|lament|penúria|infeli'), (r'Verbrech\w*', r'crim|delinq|bandid|malfeit|delit'),
    (r'Teufel\w*|teuflisch\w*|satanisch\w*', r'diab|dem[ôo]n|sat[âa]n|infern'),
)]
FORTES_DE_IDIOMA = {'en': FORTES, 'de': FORTES_DE}


def abrandadas(fonte, saida, origem='en'):
    """Palavras fortes da fonte (inglês ou alemão) com menos equivalentes fortes no resultado do que ocorrências na fonte.
    Conta as ocorrências: palavra dita cinco vezes e mantida em quatro também é apontada. Medido em 07/10/2026: pega 6 de 12 abrandamentos
    plantados (4 só pela presença), com 1 falso alarme a mais em 232 traduções revisadas e 2 alertas a mais nos 321 blocos do piloto."""
    perdidas = set()
    for de, pt in FORTES_DE_IDIOMA.get(origem, ()):
        nf, ns = len(de.findall(fonte)), len(pt.findall(saida))
        if nf > ns:
            perdidas.add(de.search(fonte)[0].lower() + (f' ({ns} de {nf})' if ns else ''))
    return sorted(perdidas)


def _esqueleto(w):
    """A palavra sem o que as reformas ortográficas mexeram (acentos, letras dobradas, ph/th/y…): para ver se ainda é a mesma palavra."""
    w = ''.join(c for c in unicodedata.normalize('NFD', w.lower()) if unicodedata.category(c) != 'Mn')
    for a, b in (('ph', 'f'), ('th', 't'), ('rh', 'r'), ('y', 'i'), ('k', 'c'), ('w', 'v'), ("'", ''), ('-', ''), ('mpt', 'nt'), ('pt', 't'), ('ct', 't'),
                 ('gn', 'n'), ('mn', 'n'), ('sc', 'c'), ('z', 's'), ('ue', 'ui'), ('oe', 'oi'), ('ae', 'ai')):
        w = w.replace(a, b)
    return re.sub(r'(.)\1+', r'\1', w)


def frases(t):
    return [f for f in FRASE.split(MARCA.sub(' ', t).strip()) if f.strip()]


def ficou_na_lingua_da_fonte(saida, origem):
    """Frases do resultado (6+ palavras) que continuam no idioma da fonte: sinal de trecho não traduzido."""
    achadas = []
    for f in frases(saida):
        p = re.findall(r"[a-zà-ÿ]+", f.lower())
        o, d = sum(w in COMUNS[origem] for w in p), sum(w in COMUNS['pt'] for w in p)
        if len(p) >= 6 and o >= 3 and o > 2 * d:
            achadas.append(f)
    return achadas


def fora_do_glossario(fonte, saida, contexto):
    """Termos decididos (linhas "- termo = tradução" do contexto) que aparecem na fonte e não saíram como decidido."""
    prob = []
    for m in re.finditer(r'^- (.+?) = (.+)$', contexto or '', re.M):
        termo, usar = m[1].strip(), m[2].strip()
        if re.search(rf'\b{re.escape(termo)}', fonte, re.I):
            # compara pelo começo de cada palavra, para aceitar plural e flexão ("atividades substitutivas" ~ "atividade substitutiva"),
            # e conta: o termo tem de sair como decidido tantas vezes quantas aparece na fonte
            padrao = r'\W+'.join(re.escape(w[:max(4, len(w) - 2)] if len(w) > 3 else w) + r'\w*' for w in re.findall(r'\w+', usar))
            if len(re.findall(padrao, saida, re.I)) < len(re.findall(rf'\b{re.escape(termo)}', fonte, re.I)):
                prob.append(f'glossário: "{termo}" deveria sair como "{usar}"')
    return prob


PREFIXOS = ('anti', 'auto', 'contra', 'extra', 'hiper', 'infra', 'inter', 'macro', 'mega', 'micro', 'mini', 'multi', 'neo', 'paleo', 'pós', 'pos', 'pré', 'pre',
            'proto', 'pseudo', 'semi', 'sobre', 'sub', 'super', 'supra', 'tecno', 'tele', 'ultra', 'socio', 'sócio', 'bio', 'eco', 'geo', 'etno', 'anarco', 'cripto', 'tecno', 'não', 're', 'des')


REFAZER = ('abrandamento', 'não existe em português')      # alertas objetivos que o tradutor pequeno não conserta: o bloco vai para o modelo maior


def inventadas(fonte, saida):
    """Palavras da tradução que não existem em português e não vêm da fonte: "máscaros", "fdido", "merds" (vistas num livro inteiro).
    Ficam de fora: palavra igual a uma da fonte (termo mantido), palavra que começa como uma da fonte (termo do autor aportuguesado:
    "neocameralista"), prefixo + palavra que existe ("supercorporações") e nome próprio. Sem o dicionário, lista vazia."""
    if regras.existe('casa') is None:
        return []
    da_fonte = {w.lower() for w in re.findall(r'[^\W\d_]+', fonte)}
    raizes = {w[:5] for w in da_fonte if len(w) >= 5}
    sem_acento = lambda w: ''.join(c for c in unicodedata.normalize('NFD', w) if unicodedata.category(c) != 'Mn')      # noqa: E731
    out = []
    for w in dict.fromkeys(re.findall(r'(?<![\w-])[a-zà-ÿ]{5,}(?![\w-])', MARCA.sub(' ', saida))):
        if w in da_fonte or sem_acento(w)[:5] in raizes or regras.existe(w):
            continue
        # prefixo + palavra que existe (com o r ou o s dobrado depois do prefixo: neorreacionário) e advérbio em -mente de adjetivo que existe
        resto = [w[len(p):] for p in PREFIXOS if w.startswith(p) and len(w) - len(p) >= 4]
        if any(regras.existe(r) or (r[:2] in ('rr', 'ss') and regras.existe(r[1:])) for r in resto):
            continue
        if w.endswith('mente') and (regras.existe(w[:-5]) or regras.existe(w[:-6] + 'o')):
            continue
        out.append(w)
    return out


def checagens(fonte, saida, tarefa, contexto=''):
    prob = []
    if eh_recusa(saida, fonte):
        prob.append('possível recusa ou aviso moralizante')
    if tarefa != 'ler_pagina' and fonte:
        r = len(saida) / max(1, len(fonte))
        curto = len(fonte) < 60        # em linha curta (data, título) a proporção engana: "May 3, 2012" -> "3 de maio de 2012" dá 1,5×
        if tarefa in ('limpar_ocr', 'atualizar_pt') and not 0.85 <= r <= 1.15 and (not curto or abs(len(saida) - len(fonte)) > 12):
            prob.append(f'tamanho fora do esperado ({r:.2f}×): omissão ou acréscimo')
        if tarefa.startswith('traduzir') and (abs(len(saida) - len(fonte)) > 40 if curto else not 0.85 <= r <= 1.4):      # 0,91 a 1,31 na referência
            prob.append(f'tamanho suspeito ({r:.2f}×)' + (': o modelo pode ter inventado texto' if r > 2 else ''))
        faltam = sorted(n for n in numeros(fonte) - numeros(saida) if not re.search(rf'\b{romano(int(n))}\b', saida))      # "18th century" -> "século XVIII" vale
        if faltam:
            prob.append('número da fonte ausente no resultado: ' + ', '.join(faltam))
        mf, ms = Counter(MARCA.findall(fonte)), Counter(MARCA.findall(saida))
        if mf != ms:        # link, nota ou quebra de linha que sumiu ou apareceu
            prob.append('marcação diferente da fonte' + (f"; faltam as marcas {' '.join((mf - ms).elements())}" if mf - ms else '')
                        + (f"; marcas a mais: {' '.join((ms - mf).elements())}" if ms - mf else ''))
        vazias = re.findall(r'<([aib]\d+)>\s*</\1>', saida)
        if vazias:
            prob.append('marcação diferente da fonte; marca sem texto dentro: ' + ' '.join(f'<{v}></{v}>' for v in vazias))
        if fonte.count('*') != saida.count('*'):
            prob.append('itálico ou negrito diferente da fonte')
        if tarefa == 'atualizar_pt':
            # o que tem cara de grafia antiga, mais o que não está no dicionário de hoje (falso alarme medido num livro atual: 1,4% das palavras distintas)
            velhas = sorted(set(regras.sobras(saida)) | set(regras.desconhecidas(saida)))
            if velhas:
                prob.append('grafia antiga ou palavra fora do dicionário atual: ' + ', '.join(velhas[:8]))
            # atualizar é trocar grafia, não palavra: as palavras, sem acento e sem letra dobrada, têm de ser as mesmas e na mesma ordem
            pf, ps = [_esqueleto(w) for w in regras.PALAVRA.findall(fonte)], [_esqueleto(w) for w in regras.PALAVRA.findall(saida)]
            igual = SequenceMatcher(None, pf, ps, autojunk=False).ratio() if pf else 1
            if igual < 0.93:
                prob.append(f'o texto mudou além da grafia ({igual:.0%} das palavras iguais): palavra trocada, tirada ou acrescentada')
        if tarefa in ORIGEM:
            ff, fs = frases(fonte), frases(saida)
            # medido em app/regua_erros.py: tradução fiel quase nunca muda o número de frases (228 de 232 na referência; 40 de 40 nos modelos)
            if len(ff) >= 2 and len(fs) < len(ff):
                prob.append(f'menos frases que a fonte ({len(fs)} contra {len(ff)}): possível omissão')
            elif len(ff) >= 2 and len(fs) > len(ff):
                prob.append(f'mais frases que a fonte ({len(fs)} contra {len(ff)}): possível acréscimo')
            else:
                for x, y in zip(ff, fs):      # mesma contagem: cada frase deve ter tamanho parecido com a da fonte (0,81 a 1,32 na referência)
                    if len(x) > 40 and not 0.6 <= len(y) / len(x) <= 1.7:
                        prob.append(f'frase com tamanho muito diferente da fonte ({len(y) / len(x):.2f}×): "{y[:60]}"')
                        break
            if len(NEGA[ORIGEM[tarefa]].findall(fonte)) > len(NEGA['pt'].findall(saida)):
                prob.append('menos negações que a fonte: conferir se algum "não" se perdeu (sentido invertido)')
            for f in ficou_na_lingua_da_fonte(saida, ORIGEM[tarefa])[:2]:
                prob.append(f'trecho ficou no idioma da fonte: "{f[:80]}"')
            # visto no piloto: ao corrigir, o modelo às vezes escreve a observação do revisor dentro do texto ("… traduzido como … é aceitável")
            if COMENTARIO.search(saida) and not COMENTARIO_NA_FONTE.search(fonte):
                prob.append(f'possível comentário do modelo dentro do texto: "{COMENTARIO.search(saida)[0]}"')
            if abrandadas(fonte, saida, ORIGEM[tarefa]):
                prob.append('palavra forte da fonte sem equivalente forte no resultado (possível abrandamento): ' + ', '.join(abrandadas(fonte, saida, ORIGEM[tarefa])))
            if inventadas(fonte, saida):      # palavra que não é português nem vem da fonte: erro objetivo, o modelo maior refaz o bloco
                prob.append('palavra que não existe em português: ' + ', '.join(inventadas(fonte, saida)[:8]))
            prob += fora_do_glossario(fonte, saida, contexto)
    if not saida.strip():
        prob.append('resultado vazio')
    return prob


# Medido em app/regua_erros.py (30 parágrafos, erros injetados): este pedido em dois níveis pega mais que o anterior
# (sozinho: acréscimo 100%, "não" perdido 83%, número 80%, suavização 3 de 4), mas é fraco em omissão (47%): por isso as checagens automáticas.
AUDITORIA = ('Você é um revisor rigoroso de fidelidade. Compare a FONTE com o RESULTADO de outra IA para a tarefa "{tarefa}", frase por frase.\n'
             'ERROS DE FIDELIDADE (graves): frase ou trecho omitido; trecho acrescentado que não está na fonte; sentido invertido ou alterado '
             '(um "não" perdido, sujeito trocado); SUAVIZAÇÃO ou intensificação (palavra forte, crua ou ofensiva trocada por uma branda, ou o contrário); '
             'número, nome ou data diferente; trecho deixado em outro idioma; comentário ou aviso que não está na fonte.\n'
             # as notas de estilo saíram do pedido: ninguém as usava e o auditor gastava tempo escrevendo-as em todo bloco
             'Não comente estilo, naturalidade nem pontuação: só fidelidade.\n'
             'Responda SOMENTE com JSON, começando pela fidelidade: {{"fidelidade": [{{"trecho": "palavras exatas do RESULTADO", "problema": "o que está errado", "certo": "como o trecho deveria ficar, em português"}}]}}. '
             'Lista vazia se não houver. Só é erro de fidelidade o que faria o leitor entender outra coisa ou perder algo que o autor escreveu; preferir outra palavra de mesmo sentido '
             'NÃO é erro e não entra na lista (exemplos que NÃO são erro: "A book by" → "Um livro de"; "Baby" → "Amor"; "limp home" → "mancando para casa"; "the bad guys" → "os bandidos"). '
             'Se o "certo" que você escreveria já é o que está no RESULTADO, não há erro: não liste. Sinônimo com o mesmo sentido e a mesma força NÃO é erro. Grafia modernizada NÃO é erro.'
             # aprendido lendo as disputas do piloto (80 blocos): o auditor listava trecho correto, pedia para deixar palavra em inglês e dizia faltar o que estava lá
             ' Traduzir um termo ou uma expressão idiomática pelo sentido NÃO é erro: nunca peça para manter palavra no idioma da fonte; palavra ou frase que FICOU no idioma da fonte é erro. '
             'Liste SÓ o que está errado: se o trecho está correto, não o cite. Antes de dizer que falta algo, confira se não está no RESULTADO com outras palavras. '
             'No máximo três erros, os mais graves.')
# objeção que o próprio auditor desmente ("tradução correta", "não é erro"…), sem um "mas" depois: não reprova (7 de uma vez num bloco do piloto)
CONCEDE = re.compile(r'(tradução (está )?corret|não há erro|não é (um )?erro|fidelidade está corret|é fiel|está corret|é aceitável|mantém o sentido)(?!.*\b(mas|porém|contudo|no entanto)\b)', re.I | re.S)


MORALISMO = re.compile(r'ofensiv|pejorativ\w* e vulgar|politicamente|inapropriad|(inadequad|inaceit[áa]ve)\w*[^.]{0,40}(modern|context|socia|p[úu]blic)|n[ãa]o [ée] (comum|aceit[áa]vel) (em|no) portugu', re.I)


GRANDE = 'bloco grande demais para o modelo ler inteiro de uma vez'      # o que o usuário lê quando um passo foi pulado por não caber no contexto


def _cabe(resposta, *textos):
    """O pedido (textos) mais a resposta (em tokens) cabem no contexto do motor? Sem motor para contar, vale a conta por cima:
    3 caracteres por token (português e inglês dão perto de 4) e 300 de folga para o formato de conversa."""
    # ponytail: estimativa por caracteres; se um dia errar para menos, o motor recusa o pedido e o trabalho pausa com o erro dele. Contar de verdade = /tokenize do llama-server
    return sum(len(t) for t in textos) / 3 + resposta + 300 <= motor.CTX


def _teto(fonte):
    """Limite de tokens da resposta que traduz ou refaz um bloco. Linha curta (título, data): justo, porque foi aí que um modelo inventou um
    parágrafo inteiro no piloto. Bloco longo: cresce com a fonte (0,6 token por caractere, umas 1,6× o tamanho dela). Com o limite fixo de 2000,
    parágrafo de mais de uns 6 mil caracteres saía cortado no meio; assim a resposta só bate no limite se já estiver bem maior que a fonte,
    e isso a checagem de tamanho acusa."""
    return max(2000, int(len(fonte) * 0.6)) if len(fonte) > 300 else max(80, len(fonte))


def _partes(fonte, limite):
    """Reparte um bloco que não cabe no contexto em pedaços de até `limite` caracteres, em fim de frase (sem pontuação, num espaço)."""
    cortes = [m.end() for m in FRASE.finditer(fonte)]      # corta DEPOIS do espaço entre as frases: FRASE.split comeria as aspas de fechamento
    partes, atual = [], ''
    for frase in (fonte[i:j] for i, j in zip([0] + cortes, cortes + [len(fonte)])):
        while len(frase) > limite:
            corte = frase.rfind(' ', 0, limite) + 1 or limite
            partes += [atual, frase[:corte]] if atual else [frase[:corte]]
            atual, frase = '', frase[corte:]
        if len(atual) + len(frase) > limite:
            partes.append(atual)
            atual = ''
        atual += frase
    return [p.strip() for p in partes + [atual] if p.strip()]


def auditar(b, tarefa, fonte, saida):
    """Devolve (fiel?, problemas). Só erro de fidelidade reprova; notas de estilo vêm na lista com o prefixo "estilo: " e não reprovam."""
    pedido = f'FONTE:\n{fonte}\n\nRESULTADO:\n{saida}'
    if b != FORA and not _cabe(1000, AUDITORIA, pedido):
        return False, [f'{GRANDE}: o auditor não conferiu']
    txt = chat(b, [{'role': 'system', 'content': AUDITORIA.format(tarefa=tarefa)}, {'role': 'user', 'content': pedido}], num_predict=1000,
               vivo={'papel': 'conferindo', 'fonte': fonte, 'resultado': saida})
    m = re.search(r'\{.*\}', txt, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        d = {}
    if 'fidelidade' in d:
        # objeção que se desmente: o "certo" que o auditor propõe já é o que está no resultado (visto num livro inteiro: "deve ser 'Barbeiro do Home'"
        # para um resultado que dizia "BARBEIRO DO HOME"). Sai da lista de erros sem gastar correção nem juiz.
        chapa = lambda t: re.sub(r'[\W_]+', ' ', str(t or '').lower()).strip()      # noqa: E731
        ja_esta = lambda x: isinstance(x, dict) and len(chapa(x.get('certo'))) >= 4 and chapa(x.get('certo')) in chapa(MARCA.sub(' ', saida))      # noqa: E731
        fmt = lambda x: (f"“{x.get('trecho', '')}”: {x.get('problema', '')}" + (f" (sugestão: {x['certo']})" if x.get('certo') else '')) if isinstance(x, dict) else str(x)      # noqa: E731
        todos = [fmt(x) for x in d['fidelidade'] or []]
        desmentidas = {fmt(x) for x in d['fidelidade'] or [] if ja_esta(x)}
        # o auditor às vezes reclama que a palavra é "ofensiva" ou "inadequada": isso é juízo sobre o autor, não erro de tradução (princípio do app)
        moral = {g for g in todos if MORALISMO.search(g) and not re.search(r'abrand|suaviz|atenu|mais brand|menos (forte|ofens|cru)|perde[u]? (a )?(for[çc]a|intensidade)', g, re.I)}
        graves = [g for g in todos if not CONCEDE.search(g) and g not in desmentidas and g not in moral]
        return not graves, graves + ['estilo: ' + str(e) for e in d.get('estilo') or []] + ['estilo: (o auditor citou, mas disse estar correto) ' + g for g in todos if g not in graves]
    if 'ok' in d:                                     # formato antigo
        return bool(d['ok']), [str(p) for p in d.get('problemas', [])]
    if '"fidelidade"' in txt:                         # resposta cortada no meio: valem as objeções que chegaram inteiras
        graves = [f'“{t}”: {p}' for t, p in re.findall(r'"trecho"\s*:\s*"(.*?)"\s*,\s*"problema"\s*:\s*"(.*?)"\s*(?:,\s*"certo"\s*:\s*"(?:[^"\\]|\\.)*"\s*)?\}', txt, re.S) if not CONCEDE.search(p)]
        if graves or re.search(r'"fidelidade"\s*:\s*\[\s*\]', txt):
            return not graves, graves
    return False, ['auditor não respondeu em formato válido: ' + txt[:120]]


# O juiz só vota; se alguma objeção procede, a correção é pedida à parte (revisar), porque num pedido só ele votava e não escrevia a sentença.
# Os exemplos vêm da leitura das disputas do piloto (metade de desenvolvimento; a outra metade ficou para medir: app/regua_juiz.py).
JUIZ = ('Você é o juiz de uma disputa de tradução. Um TRADUTOR produziu a VERSÃO a partir da FONTE. Um AUDITOR contestou alguns TRECHOS (ele erra muito: '
        'contesta trecho que está certo), e checagens automáticas deram ALERTAS. Você não vê o argumento do auditor, só o trecho contestado: julgue por conta própria.\n'
        'Para cada item, ache o trecho na FONTE e o correspondente na VERSÃO, compare os dois e decida:\n'
        'FIEL = a VERSÃO diz a mesma coisa, com a mesma força. Sinônimo, expressão idiomática traduzida pelo sentido, outra ordem de palavras e outra pontuação são FIEL. '
        'Termo traduzido para o português é FIEL (ninguém deve pedir para manter palavra no idioma da fonte).\n'
        'ERRO = a VERSÃO omite ou acrescenta conteúdo; inverte ou altera o sentido; abranda ou intensifica palavra forte, crua ou ofensiva; troca número, nome ou data; '
        'deixa trecho no idioma da fonte; perde ou cria marca (<a1>…</a1>, <i1>…</i1>, <n1/>, <br>, *…*).\n'
        'Exemplos de FIEL: "1930s" → "década de 1930"; "dim people" → "pessoas pouco inteligentes"; "nurture" → "criação"; "reckless" → "irresponsáveis"; "comments" → "comenta".\n'
        'Exemplos de ERRO: "authoritatively" → "de forma autoritária" (é "com autoridade"); "purge" → "campanha de difamação" (abrandou: é "expurgo"); '
        'palavra que ficou em inglês no meio da VERSÃO; explicação que a VERSÃO acrescentou e não está na FONTE.\n'
        'Responda com UMA linha por item, neste formato, e nada mais:\n'
        '1: FONTE «trecho» | VERSÃO «trecho» | FIEL\n2: FONTE «trecho» | VERSÃO «trecho» | ERRO — o que mudou, em poucas palavras')


def julgar(juiz, tarefa, fonte, versao, objecoes, contexto='', certeza=False):
    """Terceiro modelo julga cada objeção. Do auditor ele só recebe o trecho contestado, sem o argumento (com o argumento à vista, ele concordava com quase tudo).
    Devolve [(procede?, motivo, certeza)] na ordem das objeções; objeção sem voto legível fica de pé. A certeza (0 a 1) só é pedida ao modelo
    com certeza=True (réguas, ou limite ligado na configuração); sem isso vem None e o pedido ao modelo é o de sempre."""
    def item(o):
        m = re.match(r'“(.+?)”:', o, re.S)
        if 'formato válido' in o:
            return 'alerta automático: o auditor não concluiu a conferência; compare a VERSÃO inteira com a FONTE'
        return f'trecho contestado: «{m[1][:300]}»' if m else 'alerta automático: ' + o[:300]
    lista = '\n'.join(f'{k}. {item(o)}' for k, o in enumerate(objecoes, 1))
    if juiz != FORA and not _cabe(150 * len(objecoes) + 80, JUIZ, contexto, fonte, versao, lista):
        return [(True, GRANDE, None)] * len(objecoes)      # sem voto, a objeção fica de pé e o bloco vai para o usuário
    pedacos = [] if certeza else None
    txt = chat(juiz, [{'role': 'system', 'content': JUIZ + ('\n\n' + contexto if contexto else '')},
                      {'role': 'user', 'content': f'FONTE:\n{fonte}\n\nVERSÃO:\n{versao}\n\nITENS:\n{lista}'}], num_predict=150 * len(objecoes) + 80,
               vivo={'papel': 'julgando', 'fonte': fonte, 'resultado': versao, 'objecoes': objecoes}, pedacos=pedacos)
    # votos e motivos saem sempre do texto de verdade; os pedaços só servem para achar a probabilidade, e só se montarem o mesmo texto
    # (um pedaço pode vir com meia letra acentuada: aí as posições não batem e a certeza fica sem valor)
    montado = ''.join(p['token'] for p in pedacos or [])
    desloca = len(montado.rstrip()) - len(txt) if pedacos and txt and montado.rstrip().endswith(txt) else None      # modelo que pensa antes: os pedaços do raciocínio vêm na frente
    votos = {}
    for ml in re.finditer(r'^[ \t]*(\d+)[ \t]*[:.)][ \t]*(.*)$', txt, re.M):
        n, linha = ml[1], ml[2]
        m = re.search(r'\|\s*(FIEL|ERRO)\b\s*[—–:-]*\s*(.*)$', linha) or re.search(r'\b(FIEL|ERRO)\b\s*[—–:-]*\s*(.*)$', linha)
        if m:
            votos.setdefault(int(n), (m[1] == 'ERRO', m[2].strip() or linha.strip()[:160], None if desloca is None else _certeza(pedacos, desloca + ml.start(2) + m.start(1), m[1])))
    return [votos.get(k, (True, 'o juiz não se pronunciou', None)) for k in range(1, len(objecoes) + 1)]


def _certeza(pedacos, pos, voto):
    """Grau de certeza de um voto (0 a 1): no ponto do texto em que o juiz escreveu FIEL ou ERRO, quanto da probabilidade estava na palavra
    escolhida e quanto na outra. pos = posição da palavra no texto montado com os pedaços. Sem pedaços (modelo de fora), None."""
    ini = 0
    for p in pedacos:
        if ini <= pos < ini + len(p['token']):
            f = e = 0.0
            for alt in p.get('top_logprobs') or [p]:
                letra = alt['token'].strip(' *|—–-:«»"').upper()[:1]
                f += math.exp(alt['logprob']) if letra == 'F' else 0
                e += math.exp(alt['logprob']) if letra == 'E' else 0
            return round((f if voto == 'FIEL' else e) / (f + e), 3) if f + e else None
        ini += len(p['token'])
    return None


def sentenciar(juiz, tarefa, fonte, versao, problemas, contexto='', votos=None):
    """Leva o bloco ao juiz e aplica a decisão. Devolve {'texto', 'problemas' (o que sobra para o usuário), 'ganhou', 'votos', 'sentenca'}.
    ganhou: 'tradutor' (nenhuma objeção procede: a versão fica), 'auditor' (procede, e a correção do juiz passou nas checagens),
    'usuario' (procede e a correção não passou, ou sobrou alerta objetivo: vai para a revisão)."""
    import config
    minimo = config.le()['processo'].get('certeza_juiz', 0)
    votos = votos or julgar(juiz, tarefa, fonte, versao, problemas, contexto, certeza=minimo > 0)      # votos já dados por um votante à parte (fila) valem
    de_pe = [(p, m) for p, (procede, m, _) in zip(problemas, votos) if procede or trava(p)]      # alerta objetivo fica de pé mesmo se o juiz discordar
    # voto FIEL dado com pouca certeza não derruba a objeção: ela segue para o usuário, com o aviso. Limite em config.processo.certeza_juiz; 0 = desligado, que é o padrão (medido: a certeza do juiz não separou acerto de erro)
    incertos = [f'{p} (o juiz achou fiel, mas sem certeza: {round(c * 100)}%)' for p, (procede, _, c) in zip(problemas, votos)
                if not procede and not trava(p) and c is not None and c < minimo]
    r = {'texto': versao, 'problemas': [p for p, _ in de_pe] + incertos, 'ganhou': 'usuario', 'votos': votos, 'sentenca': None}
    if not de_pe:
        r['ganhou'] = 'usuario' if incertos else 'tradutor'
        return r
    if any('formato válido' in p for p, _ in de_pe):
        return r
    # quem conserta é o próprio juiz: medido no piloto, os modelos pequenos não corrigem o que lhes é apontado
    contexto = _com_guia(tarefa, fonte, contexto)      # a correção do juiz também abrandava (27 das 58 correções recusadas num livro inteiro)
    pontos = '\n'.join(f'- {p[:300]} ({m})' for p, m in de_pe)
    if juiz != FORA and not _cabe(_teto(fonte), _sistema(tarefa, contexto), fonte, versao, pontos):
        return r      # a correção não caberia no contexto e sairia cortada: o bloco vai para o usuário com as objeções
    r['sentenca'] = ajusta(fonte, chat(juiz, [{'role': 'system', 'content': _sistema(tarefa, contexto)}, {'role': 'user', 'content': fonte}, {'role': 'assistant', 'content': versao},
                                              {'role': 'user', 'content': 'Um juiz decidiu que estes pontos da sua versão estão errados:\n' + pontos +
                                               '\nReescreva a versão INTEIRA, do começo ao fim, em português, corrigindo só esses pontos e copiando o resto igual. '
                                               'Não deixe palavra no idioma da fonte. Responda SOMENTE com o texto final.'}],
                                       num_predict=_teto(fonte), vivo={'papel': 'sentenciando', 'fonte': fonte, 'critica': pontos, 'resultado': versao}))
    tipo = lambda p: p[:14]      # noqa: E731
    liberados = {tipo(p) for p, (procede, _, _) in zip(problemas, votos) if not procede}      # só o que o juiz julgou improcedente pode continuar na correção
    # a correção só é recusada pelo que ela PIORA: alerta que a versão anterior já tinha (uma frase a mais ou a menos num parágrafo longo, por exemplo)
    # não conta. Antes contava, e a versão antiga, com o erro apontado, era a que ficava (52 dos 76 blocos mandados ao usuário num livro inteiro).
    ja_tinha = {tipo(c) for c in checagens(fonte, versao, tarefa, contexto)}
    novos = [c for c in checagens(fonte, r['sentenca'], tarefa, contexto) if tipo(c) not in ja_tinha and (trava(c) or 'abrandamento' in c or tipo(c) not in liberados)]
    if any(r['sentenca'].count(x) != versao.count(x) for x in '?!'):      # visto no piloto: o juiz tirou interrogações do autor para acertar a contagem de frases
        novos.append('a correção mudou pontos de interrogação ou exclamação')
    # a correção não pode trazer palavra da fonte que a versão já tinha traduzido (visto no piloto: "réplica" voltou a ser "riposte")
    pal = lambda t: set(re.findall(r'[a-zà-ÿ]{5,}', MARCA.sub(' ', t)))      # noqa: E731  só minúsculas: nome próprio não conta
    voltou = sorted(w for w in (pal(r['sentenca']) - pal(versao)) & pal(fonte) if not regras.existe(w))      # "terror", "animal": iguais nas duas línguas
    if voltou:
        novos.append('palavra da fonte que voltou sem tradução: ' + ', '.join(voltou[:6]))
    if novos:
        r['problemas'] += ['a correção do juiz não passou nas checagens (' + '; '.join(novos)[:200] + '): ficou a versão anterior']
    else:
        r.update(texto=r['sentenca'], problemas=incertos, ganhou='auditor')
    return r


def juizes(a='', b=''):
    """Candidatos a juiz, em ordem: o escolhido na tela Modelos; senão o maior instalado que não esteja na disputa; por último os pequenos."""
    import config
    tem = motor.nomes()
    ordem =[config.le()['papeis'].get('juiz')] + [m for m in (A_PADRAO, B_PADRAO) if m not in (a, b)] + [LEVE, TRADUTOR]
    return list(dict.fromkeys(m for m in ordem if m and (m in tem or m == FORA)))


MARCAS = (' Se o texto tiver marcas como <a1>…</a1>, <i1>…</i1>, <n1/>, <br> ou *…*, mantenha cada uma exatamente igual, em volta do mesmo trecho: '
          'não traduza, não remova e não acrescente marcas.')


def _sistema(tarefa, contexto=''):
    return PROMPTS[tarefa] + MARCAS + ('\n\n' + contexto if contexto else '')


def _local(tarefa):
    """Modelo local para o papel de proponente (ignora a escolha 'fora')."""
    return padrao('tradutor' if tarefa.startswith('traduzir') else 'geral', motor.nomes())


def grande(menos=''):
    """Modelo maior instalado, para refazer blocos em que o tradutor rápido abrandou. Medido nos casos do piloto (docs/benchmark/crua-*):
    nem o reforço no pedido nem a correção pelos modelos pequenos recuperam a palavra forte; o de 30B recuperou 2 de 3."""
    tem = motor.nomes()
    return next((m for m in (A_PADRAO, B_PADRAO) if m in tem and m != menos), None)


def _sem_censura(tarefa, saida, refaz):
    """Serviço de fora que recusa, comenta ou devolve vazio é descartado: o bloco é refeito pelo modelo local."""
    if eh_recusa(saida) or not saida.strip():
        import rede
        rede._anota('—', 'o modelo de fora recusou ou cortou um bloco; refeito no modelo local')
        return refaz(_local(tarefa))
    return saida


# Palavras cruas do inglês e um equivalente igualmente cru. Os modelos trocam essas palavras por outras mais brandas ou as deixam em inglês
# (visto num livro inteiro: até o modelo grande escreveu "otário" e "caras esquisitos" para "faggot"). Dizer, no pedido daquele bloco, qual é
# o equivalente resolve a maior parte: medido em 28 blocos abrandados, sobraram 8 com o tradutor pequeno, sem precisar do modelo grande.
CRUAS = {r'fagg?ots?': 'viado', r'fuck(ing|ed|s|er|ers)?': 'porra, foder', r'shit(ty)?': 'merda', r'bullshit': 'merda, besteira', r'cunts?': 'vadia, buceta',
         r'whores?': 'puta', r'sluts?': 'vagabunda', r'bitch(es)?': 'vadia', r'piss(ed)?': 'mijo, puto', r'assholes?': 'cuzão', r'dicks?|cocks?': 'pau, pica',
         r'pussy': 'buceta', r'scum(bags?)?': 'escória', r'retard(ed|s)?': 'retardado', r'dykes?': 'sapatão', r'niggers?': 'crioulo', r'trann(y|ies)': 'traveco',
         r'damn(ed)?|goddamn': 'maldito', r'disgust(ing|ed|s)?': 'nojo, nojento', r'degenerates?': 'degenerado', r'rap(e|ed|es|ing)': 'estuprar',
         r'bastards?': 'desgraçado', r'morons?|idiots?': 'idiota', r'losers?': 'perdedor, fracassado', r'filth(y)?': 'imundo, imundície'}


def guia_cru(fonte):
    """Frase para o pedido de tradução deste bloco, se ele tiver palavras cruas: qual equivalente usar. '' se não tiver."""
    achou = dict.fromkeys((m[0].lower(), pt) for pat, pt in CRUAS.items() for m in [re.search(rf'\b({pat})\b', fonte, re.I)] if m)
    return ('Este trecho tem palavras cruas. Traduza cada uma por uma palavra igualmente crua em português, nunca por outra mais branda e nunca deixando em inglês: '
            + '; '.join(f'"{a}" → {b}' for a, b in achou) + '.') if achou else ''


def _com_guia(tarefa, fonte, contexto):
    g = guia_cru(fonte) if tarefa == 'traduzir' else ''
    return (contexto + '\n' if contexto and g else contexto) + g


def propor(tarefa, fonte, a=A_PADRAO, contexto=''):
    """Passo 1: o modelo A produz o resultado. contexto = texto extra para o prompt (ex.: glossário do livro)."""
    # linha curta (título, data): limita o tamanho da resposta, porque foi aí que um modelo inventou um parágrafo inteiro no piloto
    if a == classico.NOME:                 # rascunho rápido: motor clássico, sem modelo grande
        return ajusta(fonte, classico.traduz(fonte))
    contexto = _com_guia(tarefa, fonte, contexto)
    sistema = _sistema(tarefa, contexto)
    pede = lambda m, f=fonte: chat(m, [{'role': 'system', 'content': sistema}, {'role': 'user', 'content': f}], num_predict=_teto(f),   # noqa: E731
                                   vivo={'papel': 'propondo', 'fonte': f})
    if a == FORA:
        return ajusta(fonte, _sem_censura(tarefa, pede(a), pede))
    if _cabe(_teto(fonte), sistema, fonte):
        return ajusta(fonte, pede(a))
    # parágrafo que não cabe no contexto com a tradução dele: vai em pedaços, cortados em fim de frase, e volta emendado
    # ponytail: marca de link ou itálico que atravessa o corte fica desencontrada nos pedaços; a checagem de marcas acusa e o bloco vai para o usuário
    livre = motor.CTX - 300 - len(sistema) / 3      # tokens para o pedaço e a tradução dele, descontado o pedido (com o glossário)
    limite = max(500, int(min(livre / 0.94, (livre - 2000) * 3)))      # o maior pedaço que passa em _cabe; glossário que toma o contexto todo o motor recusa
    return ajusta(fonte, ' '.join(pede(a, parte) for parte in _partes(fonte, limite)))


def revisar(tarefa, fonte, saida, critica, a=A_PADRAO, contexto='', papel='corrigindo'):
    """Passo 3: o modelo A refaz corrigindo só o que foi apontado."""
    contexto = _com_guia(tarefa, fonte, contexto)
    if a != FORA and not _cabe(_teto(fonte), _sistema(tarefa, contexto), fonte, saida, critica):
        return saida      # a correção não caberia no contexto e sairia cortada: fica a versão que havia, e as objeções seguem adiante
    return ajusta(fonte, chat(a, [{'role': 'system', 'content': _sistema(tarefa, contexto)}, {'role': 'user', 'content': fonte},
                    {'role': 'assistant', 'content': saida},
                    {'role': 'user', 'content': f'Um revisor apontou: {critica}. Refaça corrigindo SÓ isso, mantendo a fidelidade total à fonte. '
                                                'Responda SOMENTE com o texto final.'}],
                             num_predict=_teto(fonte), vivo={'papel': papel, 'fonte': fonte, 'critica': critica, 'resultado': saida}))


def processa(tarefa, fonte='', a=A_PADRAO, b=B_PADRAO, imagem_b64=None):
    """Roda o fluxo completo para um item. Devolve dict com resultado, status e a 'conversa' entre os modelos."""
    t0 = time.time()
    conversa = []
    sistema = PROMPTS[tarefa]
    if tarefa == 'ler_pagina':
        saida = chat(a, [{'role': 'user', 'content': pedido_leitura(a)}], imagens=[imagem_b64], num_predict=2500, corta_repeticao=True)
        # a "fonte" para o auditor é a própria imagem: o auditor B lê a página também e a gente compara
        fonte_b = chat(b, [{'role': 'user', 'content': pedido_leitura(b)}], imagens=[imagem_b64], num_predict=2500, corta_repeticao=True)
        sim = SequenceMatcher(None, re.findall(r'\w+', saida.lower()), re.findall(r'\w+', fonte_b.lower()), autojunk=False).ratio()
        conversa.append({'quem': a, 'disse': f'Li a página ({len(saida)} caracteres).'})
        conversa.append({'quem': b, 'disse': f'Li a mesma página de forma independente. Concordância com {a}: {sim:.0%}.'})
        prob = checagens('', saida, tarefa)
        if sim < 0.85:
            prob.append(f'os dois modelos leram a página de formas diferentes (concordância {sim:.0%})')
        status = 'aprovado' if not prob else 'revisar'
        return {'resultado': saida, 'alternativa': fonte_b, 'status': status, 'problemas': prob, 'conversa': conversa, 'segundos': round(time.time() - t0, 1)}

    saida = chat(a, [{'role': 'system', 'content': sistema}, {'role': 'user', 'content': fonte}])
    conversa.append({'quem': a, 'disse': saida})
    prob = checagens(fonte, saida, tarefa)
    ok, pb = auditar(b, tarefa, fonte, saida)
    conversa.append({'quem': b, 'disse': 'Fiel.' if ok else 'Problemas: ' + '; '.join(pb)})
    if not ok or prob:
        critica = '; '.join(prob + pb)
        revisado = chat(a, [{'role': 'system', 'content': sistema}, {'role': 'user', 'content': fonte},
                            {'role': 'assistant', 'content': saida},
                            {'role': 'user', 'content': f'Um revisor apontou: {critica}. Refaça corrigindo SÓ isso, mantendo a fidelidade total à fonte. '
                                                        'Responda SOMENTE com o texto final.'}])
        conversa.append({'quem': a, 'disse': 'Revisão: ' + revisado})
        saida = revisado
        prob = checagens(fonte, saida, tarefa)
        ok, pb = auditar(b, tarefa, fonte, saida)
        conversa.append({'quem': b, 'disse': 'Fiel.' if ok else 'Ainda discordo: ' + '; '.join(pb)})
    final = prob + ([] if ok else pb)
    return {'resultado': saida, 'status': 'aprovado' if not final else 'revisar', 'problemas': final, 'conversa': conversa,
            'segundos': round(time.time() - t0, 1)}
