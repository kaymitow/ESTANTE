// Pedido ao servidor local. Devolve o JSON ou lança Error com a mensagem do servidor.
export async function api(u, metodo, corpo) {
  const r = await fetch(u, metodo ? { method: metodo, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo ?? {}) } : undefined)
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(j.detail || r.statusText)
  return j
}
