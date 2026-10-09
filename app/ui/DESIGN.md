# DESIGN.md — Estante

Como o app deve parecer e se comportar. Quem cria ou muda uma tela (pessoa ou assistente) lê isto antes.
O formato segue a ideia do DESIGN.md (um arquivo de texto que descreve o sistema de design); as regras de processo vêm de duas listas
públicas que valem a leitura: as Web Interface Guidelines da Vercel e a Taste Skill. Daqui só entrou o que serve a um app de trabalho.

## Identidade: "arquivo noturno"

Um arquivo de leitura, não um painel de startup. Preto de arquivo, papel, vermelho de carimbo.
Três vozes tipográficas, cada uma com um papel fixo:

| Voz | Fonte padrão | Onde |
|---|---|---|
| Lombada | Cinzel (títulos, caixa-alta) | nome das telas, dos livros, das etapas |
| Página | Literata (serifada) | todo texto de livro: fonte, tradução, leitor |
| Ficha | IBM Plex Mono, caixa-alta, espaçada | rótulos, contagens, estados, botões |
| Fala do app | Inter | explicações e campos |

A serifa aqui tem motivo (o produto é livro); a mono em caixa-alta é a etiqueta de arquivo. Quem usa pode trocar tema, cores e fontes
em Configurações → Aparência; por isso **nenhuma cor ou fonte é escrita direto numa tela**.

## Tokens (app/ui/src/lib/tokens.css)

- **Cor**: `--fundo`, `--superficie`, `--papel` (texto), `--apagado` (texto secundário), `--linha`, `--linha-forte`, `--acento` (um só), `--ok`, `--revisar`.
- **Significado fixo**: `--acento` = ação principal e "é aqui agora"; `--ok` = conferido/feito; `--revisar` = pede a sua atenção. Nunca usar uma dessas só para enfeitar.
- **Espaço**: escala de 4 (`--e1` … `--e24`). **Forma**: um raio só (`--raio`). **Movimento**: `--rapido`, `--medio`, `--lento`, com `--curva`.
- Página do original é sempre branca (`#fff`), porque é uma foto de papel: é a única cor fixa permitida.

## Regras de composição

1. **Linha antes de caixa.** Agrupar com fio (`border-top`), espaço e rótulo. Caixa com borda só quando o conteúdo é um objeto (um livro, um tema, um papel de modelo). Sem sombra para "dar profundidade"; sombra só em capa de livro.
2. **Um destaque por tela.** Um botão cheio (`--acento`) no máximo; o resto é contorno ou link sublinhado.
3. **Rótulo com parcimônia.** O rótulo em mono existe para dado (contagem, estado, nome de campo). Não pôr rótulo decorativo em cima de todo título.
4. **Texto de livro tem medida.** 60 a 70 caracteres por linha na leitura; na comparação lado a lado, as duas colunas com a mesma letra.
5. **Botão cabe numa linha** e diz o que faz ("Aceitar os 641 aprovados", não "Continuar"). Duas ações com a mesma intenção na mesma tela têm o mesmo nome.
6. **Campo tem nome.** Rótulo acima do campo; texto de exemplo nunca faz as vezes de rótulo. Erro aparece ao lado do campo e diz o que fazer.
7. **Todo estado desenhado.** Vazio (diz como encher), carregando (esqueleto com a forma do que vem, nunca tela em branco nem rodinha), erro (motivo real e o próximo passo), parcial e pronto.
8. **Toque.** Todo botão responde ao passar o mouse, ao foco (`:focus-visible`, contorno em `--acento`) e ao clique (`scale(0.98)`).
9. **Movimento com fato.** Só `transform` e `opacity`. Cada animação corresponde a algo que aconteceu nos dados; nada gira para parecer ocupado. Tudo funciona com as animações desligadas.
10. **Nada de dado de mentira.** Exemplo em tela, ajuda ou teste é inventado e plausível, nunca tirado de um livro da estante, e nunca número redondo demais.
11. **A IA nunca parece aprovada.** Texto de modelo ainda não aceito aparece em tinta clara (`--apagado`) ou marcado; só o que o usuário aceitou tem tinta cheia sem marca.
12. **Itálico em título** precisa de folga na linha (`line-height` de 1,1 ou mais) quando a palavra tem g, j, p, q, y.

## O que não entra

Brilho neon, degradê em texto, cursor desenhado, três cartões iguais em fila, ícone de biblioteca genérica no lugar de desenho próprio,
verbo de propaganda ("eleve", "revolucione"), número de versão como enfeite, tabela de "medições do projeto".

## Antes de entregar uma tela

- Olhar a tela em captura (Edge sem janela, perfil descartável), não só o código; nos temas Noite, Papel e Alto contraste.
- Largura de 1400, 900 e 560 px.
- Teclado: dá para chegar em tudo e ver onde está o foco.
- Conferir os arquivos mexidos contra as Web Interface Guidelines (acessibilidade, foco, formulários, animação).
