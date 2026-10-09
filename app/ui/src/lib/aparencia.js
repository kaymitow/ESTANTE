// Aparência do app, escolhida por quem usa. Fica só neste navegador (localStorage) e é aplicada antes de a tela aparecer.
// O que NÃO muda: o nome "Estante" e o desenho da marca (a cor dela acompanha o tema). Todo o resto é do usuário.

// cada tema define as mesmas dez cores de lib/tokens.css
const tema = (id, nome, o, fundo, superficie, petroleo, papel, apagado, linha, linhaForte, acento, ok, revisar) =>
  ({ id, nome, o, cores: { fundo, superficie, petroleo, papel, apagado, linha, 'linha-forte': linhaForte, acento, ok, revisar } })
export const TEMAS = [
  tema('noite', 'Noite', 'O original: preto de arquivo, vermelho de carimbo.', '#121212', '#1a1a1a', '#1d292c', '#f2efe8', '#9a958b', '#2c2c2c', '#4a4741', '#c82924', '#7fa98a', '#d4a24a'),
  tema('meia-noite', 'Meia-noite', 'Azul profundo, para noites longas de revisão.', '#0d1321', '#141b2d', '#1a2a3f', '#e8ecf4', '#8f9ab0', '#232c42', '#3d4a66', '#5b8cff', '#6fbf9a', '#e0b45a'),
  tema('floresta', 'Floresta', 'Verde escuro com dourado.', '#0f1612', '#16201a', '#1b2b24', '#ecefe6', '#93a093', '#243027', '#40513f', '#d9a441', '#86c49a', '#e08a4a'),
  tema('terminal', 'Terminal', 'Fósforo verde sobre preto.', '#050805', '#0b110b', '#0f1a0f', '#b7f5c0', '#5f9a6a', '#143018', '#2a5a32', '#39ff6a', '#7dffa0', '#ffd24a'),
  tema('papel', 'Papel', 'Claro, cor de página.', '#f4f0e6', '#ebe6d9', '#dfe5e2', '#1a1917', '#6b665c', '#d6d0c1', '#a39c8c', '#b3241f', '#3f7350', '#8a5a0a'),
  tema('sepia', 'Sépia', 'Claro e quente, descansa a vista.', '#f1e7d0', '#e8dcc0', '#ddd3bb', '#3b2f20', '#75654f', '#d9cbab', '#a8946f', '#9c3d1a', '#4f6f3e', '#85590f'),
  tema('nevoa', 'Névoa', 'Claro e neutro, com azul.', '#f6f7f9', '#eceef2', '#e3e8ee', '#15171c', '#5d6470', '#d8dce3', '#9aa2b0', '#2456e6', '#2f7d52', '#8a5a00'),
  tema('contraste', 'Alto contraste', 'Máxima legibilidade.', '#000000', '#0d0d0d', '#101010', '#ffffff', '#c8c8c8', '#5a5a5a', '#9a9a9a', '#ffd400', '#6dff9c', '#ffb347'),
]

const f = (id, nome, pilha, italico = true) => ({ id, nome, pilha, italico })
const SERIFA = 'Georgia, serif', SEM = "'Segoe UI', system-ui, sans-serif"
const F = {
  cinzel: f('cinzel', 'Cinzel', `'Cinzel Variable', ${SERIFA}`, false),      // não tem itálico: nos títulos o destaque fica só no recuo
  bodoni: f('bodoni', 'Bodoni Moda', `'Bodoni Moda Variable', ${SERIFA}`),
  playfair: f('playfair', 'Playfair Display', `'Playfair Display Variable', ${SERIFA}`),
  cormorant: f('cormorant', 'Cormorant', `'Cormorant Variable', ${SERIFA}`),
  garamond: f('garamond', 'EB Garamond', `'EB Garamond Variable', ${SERIFA}`),
  literata: f('literata', 'Literata', `'Literata Variable', ${SERIFA}`),
  lora: f('lora', 'Lora', `'Lora Variable', ${SERIFA}`),
  inter: f('inter', 'Inter', `'Inter Variable', ${SEM}`, false),
  plex: f('plex', 'IBM Plex Sans', `'IBM Plex Sans Variable', ${SEM}`, false),
  grotesk: f('grotesk', 'Space Grotesk', `'Space Grotesk Variable', ${SEM}`, false),
  atkinson: f('atkinson', 'Atkinson Hyperlegible', `'Atkinson Hyperlegible', ${SEM}`),      // desenhada para baixa visão
  mono: f('mono', 'IBM Plex Mono', "'IBM Plex Mono', Consolas, monospace", false),
  serifa: f('serifa', 'Serifada do sistema', SERIFA),
  sistema: f('sistema', 'Do sistema', SEM, false),
}
export const FONTES = {
  titulos: [F.cinzel, F.bodoni, F.playfair, F.cormorant, F.garamond, F.grotesk, F.mono],
  leitura: [F.literata, F.garamond, F.lora, F.playfair, F.atkinson, F.plex, F.serifa],
  interface: [F.inter, F.plex, F.grotesk, F.atkinson, F.sistema],
}
export const ACENTOS = ['#c82924', '#e0662a', '#d9a441', '#3fa66a', '#2bb3a3', '#5b8cff', '#8f6bff', '#e0559b', '#9a958b']
export const PADRAO = { tema: 'noite', acento: '', fundo: '', texto: '', titulos: 'cinzel', leitura: 'literata', interface: 'inter',
                        tamanho: 100, cantos: 'suaves', caixa: true, movimento: true, abertura: true, tribunal: 'personagens' }
const CHAVE = 'estante.aparencia'

// Compartilhar um tema: só o visual vai no texto (tamanho da letra, animações e abertura são de quem usa). Nada do texto colado é executado:
// só entram chaves conhecidas, com valores conferidos; cor ilegível continua barrada pela guarda de contraste de cores().
const VISUAL = ['tema', 'acento', 'fundo', 'texto', 'titulos', 'leitura', 'interface', 'cantos', 'caixa']
const PREFIXO = 'estante-tema:1:'
export const exporta = (a) => PREFIXO + btoa(unescape(encodeURIComponent(JSON.stringify(Object.fromEntries(VISUAL.map((k) => [k, a[k]]))))))
export function importa(txt) {
  txt = (txt ?? '').trim()
  if (!txt.startsWith(PREFIXO) || txt.length > 2000) throw new Error('Isto não parece um tema do Estante.')
  let d
  try { d = JSON.parse(decodeURIComponent(escape(atob(txt.slice(PREFIXO.length))))) } catch { throw new Error('O texto do tema está incompleto ou foi alterado.') }
  const cor = (v) => (v === '' || HEX.test(v) ? v : null)
  const fnt = (g, v) => (typeof v === 'string' && (v.startsWith('outra:') || FONTES[g].some((x) => x.id === v)) ? fonte(g, v).id : null)
  const ok = { tema: TEMAS.some((t) => t.id === d.tema) ? d.tema : null, acento: cor(d.acento ?? ''), fundo: cor(d.fundo ?? ''), texto: cor(d.texto ?? ''),
               titulos: fnt('titulos', d.titulos), leitura: fnt('leitura', d.leitura), interface: fnt('interface', d.interface),
               cantos: ['retos', 'suaves', 'redondos'].includes(d.cantos) ? d.cantos : null, caixa: typeof d.caixa === 'boolean' ? d.caixa : null }
  const ruins = Object.keys(ok).filter((k) => ok[k] === null)
  if (ruins.length) throw new Error('O tema tem valores que o app não aceita: ' + ruins.join(', ') + '.')
  if (ok.fundo && ok.texto && contraste(ok.fundo, ok.texto) < 3) throw new Error('As cores deste tema deixariam o texto ilegível.')
  return ok
}

export function le() {
  try {
    const salvo = JSON.parse(localStorage.getItem(CHAVE) ?? 'null')
    if (salvo) return { ...PADRAO, ...salvo }
    // preferências guardadas antes de existir este painel
    return { ...PADRAO, tema: localStorage.getItem('estante.tema') ?? 'noite', titulos: localStorage.getItem('estante.display2') ?? 'cinzel',
             abertura: (localStorage.getItem('estante.abertura') ?? 'sim') === 'sim' }
  } catch { return { ...PADRAO } }
}
export function grava(a) { try { localStorage.setItem(CHAVE, JSON.stringify(a)) } catch {} }

// contraste entre duas cores #rrggbb (WCAG): 1 = iguais, 21 = preto no branco
const luz = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
export const contraste = (a, b) => { const [x, y] = [luz(a), luz(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }
export const HEX = /^#[0-9a-f]{6}$/i

// fonte escolhida: uma das embutidas, ou "outra:Nome" = uma fonte instalada no computador de quem usa
export function fonte(grupo, valor) {
  if (valor?.startsWith('outra:')) {
    const nome = valor.slice(6).replace(/["';{}<>\\]/g, '').trim()
    if (nome) return f(valor, nome, `'${nome}', ${grupo === 'interface' ? SEM : SERIFA}`)
  }
  return FONTES[grupo].find((x) => x.id === valor) ?? FONTES[grupo][0]
}

// as cores que valem para uma escolha: tema, mais fundo/texto/destaque próprios se passarem na guarda de contraste
export function cores(a) {
  const t = TEMAS.find((x) => x.id === a.tema) ?? TEMAS[0]
  const c = { ...t.cores }
  const proprio = HEX.test(a.fundo) && HEX.test(a.texto) && contraste(a.fundo, a.texto) >= 3      // texto ilegível não é aplicado: ninguém fica preso numa tela em branco
  if (proprio) {
    const m = (p) => `color-mix(in srgb, ${a.texto} ${p}%, ${a.fundo})`
    Object.assign(c, { fundo: a.fundo, papel: a.texto, superficie: m(5), petroleo: m(8), linha: m(14), 'linha-forte': m(32), apagado: m(62) })
  }
  if (HEX.test(a.acento)) c.acento = a.acento
  return { c, base: proprio ? a.fundo : t.cores.fundo, proprio }
}

export function aplica(a) {
  const r = document.documentElement, { c, base } = cores(a)
  for (const [k, v] of Object.entries(c)) r.style.setProperty('--' + k, v)
  r.style.setProperty('--sobre-acento', contraste('#ffffff', c.acento) >= contraste('#111111', c.acento) ? '#ffffff' : '#111111')
  r.style.colorScheme = luz(base) > 0.35 ? 'light' : 'dark'      // barras de rolagem e campos nativos acompanham
  const t = fonte('titulos', a.titulos)
  r.style.setProperty('--display', t.pilha)
  r.style.setProperty('--leitura', fonte('leitura', a.leitura).pilha)
  r.style.setProperty('--ui', fonte('interface', a.interface).pilha)
  r.style.setProperty('--escala', String((a.tamanho || 100) / 100))
  r.style.setProperty('--raio', { retos: '0px', suaves: '2px', redondos: '10px' }[a.cantos] ?? '2px')
  r.style.setProperty('--caixa-titulos', a.caixa ? 'uppercase' : 'none')
  r.dataset.tituloItalico = t.italico ? 'sim' : 'nao'
  r.dataset.movimento = a.movimento ? 'sim' : 'nao'
}
