"""Tradução por motor clássico, sem modelo grande: roda no processador, em frações de segundo por parágrafo (inglês -> português do Brasil).

    python app/classico.py --preparar      baixa o motor (2 bibliotecas pequenas) e o modelo de 66 MB; é a única hora em que usa a rede
    python app/classico.py "Some text."    traduz um trecho, para ver

Serve ao modo "rascunho rápido": o livro inteiro sai em minutos, sem auditor nem juiz. A qualidade é MENOR que a do tradutor por IA
(medido em 08/10/2026: erra sentido de expressão, tempo verbal e gênero), e por isso o rascunho vai inteiro para a revisão.
Usa CTranslate2 + SentencePiece (MIT/Apache) e o modelo aberto do projeto Argos (en -> pt-BR). Itálico, negrito e links do bloco
não passam pelo motor: as marcas são tiradas antes (ponytail: traduzir trecho a trecho entre as marcas se a ênfase fizer falta).
"""
import hashlib, io, re, subprocess, sys, urllib.request, zipfile
from pathlib import Path

NOME = 'motor-classico'
PASTA = Path(__file__).resolve().parent.parent / 'ferramentas' / 'classico'
MODELO = ('https://argos-net.com/v1/translate-en_pb-1_9.argosmodel', '1d1cd5e9540c6b38c258bed002a42d3b311b8a189acb74feaa311ef30d175c5b')
FRASE = re.compile(r'(?<=[.!?…])["”’»)\]*]*\s+(?=["“‘«(\[*]*[A-ZÀ-Ý0-9])')
MARCA = re.compile(r'</?[aib]\d+>|<n\d+/>|<br>')
_motor = None


def disponivel():
    try:
        import ctranslate2, sentencepiece      # noqa: F401
    except ImportError:
        return False
    return any(PASTA.glob('*/model/model.bin'))


def preparar():
    """Instala as duas bibliotecas no ambiente do app e baixa o modelo, conferindo o hash. Depois disso o motor não usa mais a rede."""
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--disable-pip-version-check', 'ctranslate2', 'sentencepiece'], check=True)
    if not any(PASTA.glob('*/model/model.bin')):
        dados = urllib.request.urlopen(urllib.request.Request(MODELO[0], headers={'User-Agent': 'Estante'}), timeout=300).read()
        if hashlib.sha256(dados).hexdigest() != MODELO[1]:
            sys.exit('o arquivo do modelo não confere com o hash esperado: nada foi instalado')
        PASTA.mkdir(parents=True, exist_ok=True)
        zipfile.ZipFile(io.BytesIO(dados)).extractall(PASTA)
    print('Motor clássico pronto.')


def traduz(texto):
    global _motor
    if _motor is None:
        import ctranslate2, sentencepiece
        base = next(PASTA.glob('*/model')).parent
        _motor = (ctranslate2.Translator(str(base / 'model'), device='cpu'), sentencepiece.SentencePieceProcessor(model_file=str(base / 'sentencepiece.model')))
    tr, sp = _motor
    fr = [f for f in FRASE.split(MARCA.sub(' ', texto)) if f.strip()]
    if not fr:
        return ''
    r = tr.translate_batch([sp.encode(f, out_type=str) for f in fr], beam_size=4, max_decoding_length=400)
    return ' '.join(' '.join(''.join(x.hypotheses[0]).replace('▁', ' ').split()) for x in r)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if sys.argv[1:] == ['--preparar']:
        preparar()
    elif disponivel():
        print(traduz(' '.join(sys.argv[1:]) or 'The bridge was built in 1874. It has never been closed.'))
    else:
        print('motor não instalado: rode  python app/classico.py --preparar')
