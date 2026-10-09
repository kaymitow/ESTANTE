// Realce de termos num trecho, ignorando acentos e maiúsculas, sem mexer no texto.
export const semAcento = (s) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
export const termos = (q) => q.trim().split(/\s+/).map(semAcento).filter((t) => t.length > 1)
export const contem = (texto, q) => { const b = semAcento(texto); const ts = termos(q); return ts.length > 0 && ts.every((t) => b.includes(t)) }
export function partes(trecho, q) {
  const base = semAcento(trecho); const marcas = new Array(trecho.length).fill(false)
  for (const t of termos(q)) for (let i = base.indexOf(t); i >= 0; i = base.indexOf(t, i + 1)) marcas.fill(true, i, i + t.length)
  const out = []
  for (let i = 0; i < trecho.length; i++) { const m = marcas[i]; if (out.length && out.at(-1).m === m) out.at(-1).t += trecho[i]; else out.push({ m, t: trecho[i] }) }
  return out
}
