// Citação pronta a partir de um trecho do livro. A origem vem do marcador do texto ("scan 45 · impressa 31", "seção 3 do original" ou vazia).
export function lugar(origem) {
  const imp = /impressa\s+([^\s·]+)/.exec(origem ?? '')?.[1]
  if (imp && imp !== '?' && imp !== '—') return `p. ${imp}`
  const scan = /scan\s+(\d+)/.exec(origem ?? '')?.[1]
  if (scan) return `p. ${scan} do arquivo`
  const sec = /seção\s+(\d+)/.exec(origem ?? '')?.[1]
  return sec ? `seção ${sec}` : ''
}
const sobrenome = (autor) => (autor ?? '').trim().split(/\s+/).pop()?.toUpperCase() ?? ''
export function simples(trecho, { titulo, autor }, origem) {
  return `“${trecho}” — ${[autor, titulo, lugar(origem)].filter(Boolean).join(', ')}.`
}
// ABNT (citação direta curta): "trecho" (SOBRENOME, Título, p. X). Sem o ano, que o app não conhece: quem cita completa.
export function abnt(trecho, { titulo, autor }, origem) {
  return `“${trecho}” (${[sobrenome(autor), titulo, lugar(origem)].filter(Boolean).join(', ')}).`
}

// autoteste: node app/ui/src/lib/citacao.js
if (typeof process !== 'undefined' && process.argv[1]?.endsWith('citacao.js')) {
  const eq = (a, b) => { if (a !== b) throw new Error(`${a} != ${b}`) }
  const livro = { titulo: 'Livro de exemplo', autor: 'Autor de exemplo' }
  eq(lugar('scan 45 · impressa 31'), 'p. 31'); eq(lugar('scan 45 · impressa ?'), 'p. 45 do arquivo'); eq(lugar('seção 3 do original'), 'seção 3'); eq(lugar(''), '')
  eq(simples('Uma noite destas', livro, 'scan 4 · impressa 2'), '“Uma noite destas” — Autor de exemplo, Livro de exemplo, p. 2.')
  eq(abnt('Uma noite destas', livro, ''), '“Uma noite destas” (EXEMPLO, Livro de exemplo).')
  console.log('ok')
}
