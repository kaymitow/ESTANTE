// Tribunal com personagens: a lógica, sem desenho. Cada pose, pilha e reação sai de um fato dos dados do processamento
// (plano em docs/plano-3-ideias-e-afazeres.md, A1). Nada aqui inventa movimento: se o dado não mudou, a cena não muda.
// v = o que o modelo está fazendo agora ({ papel, texto }); c = contadores da fila (st.fila.conta); fase = fase da fila.

// Pose de cada personagem. parado = o texto não cresceu nas últimas consultas.
export function pose(v, fase, estado, parado = false) {
  const p = { tradutor: 'repouso', auditor: 'repouso', juiz: 'ausente', ato: '' }
  if (estado === 'concluido') return { ...p, ato: 'concluido' }
  if (estado === 'pausado' || estado === 'erro') return { ...p, juiz: fase === 'julgar' ? 'repouso' : 'ausente', ato: estado }
  if (fase === 'julgar') { p.juiz = 'repouso'; p.tradutor = p.auditor = 'olha-juiz' }
  const papel = v?.papel, tem = !!v?.texto
  const quem = { propondo: 'tradutor', corrigindo: 'tradutor', conferindo: 'auditor', julgando: 'juiz', sentenciando: 'juiz' }[papel]
  if (!quem) return p
  p.ato = papel
  if (parado && tem) p[quem] = 'espera'
  else if (!tem) p[quem] = { tradutor: 'folheia', auditor: 'limpa-lupa', juiz: 'repouso' }[quem]      // modelo carregando
  else p[quem] = { propondo: 'escreve', corrigindo: 'reescreve', conferindo: 'lupa', julgando: 'julga', sentenciando: 'escreve' }[papel]
  if (papel === 'conferindo' && tem) p.tradutor = 'olha-auditor'
  return p
}

// As seis pilhas. A soma é sempre igual a c.propostos: é a checagem de que a cena não perdeu nenhuma folha.
export function pilhas(c, temJuiz = true) {
  const n = (k) => c?.[k] ?? 0
  const julgados = n('causa_tradutor') + n('causa_auditor') + n('causa_usuario')
  const disputa = n('em_disputa') - julgados
  return {
    conferir: (n('propostos') - n('conferidos')) + (n('corrigidos') - n('reconferidos')),
    corrigir: n('com_problema') - n('corrigidos'),
    disputa: temJuiz ? disputa : 0,
    aprovados: (n('conferidos') - n('com_problema')) + (n('reconferidos') - n('em_disputa')) + n('causa_tradutor'),
    juiz: n('causa_auditor'),
    voce: n('causa_usuario') + (temJuiz ? 0 : disputa),
  }
}

// O que aconteceu entre duas consultas: [{ tipo, de, para }]. Mais de uma mudança de uma vez = sem animação (só os números mudam).
export function eventos(antes, depois) {
  if (!antes || !depois) return []
  const d = (k) => (depois[k] ?? 0) - (antes[k] ?? 0)
  const ev = []
  if (d('propostos') === 1) ev.push({ tipo: 'proposto', de: 'tradutor', para: 'conferir' })
  if (d('conferidos') === 1) ev.push(d('com_problema') === 1 ? { tipo: 'objecao', de: 'auditor', para: 'corrigir' } : { tipo: 'aprovado', de: 'auditor', para: 'aprovados' })
  if (d('corrigidos') === 1) ev.push({ tipo: 'corrigido', de: 'tradutor', para: 'conferir' })
  if (d('reconferidos') === 1) ev.push(d('em_disputa') === 1 ? { tipo: 'disputa', de: 'auditor', para: 'disputa' } : { tipo: 'aprovado', de: 'auditor', para: 'aprovados' })
  if (d('causa_tradutor') === 1) ev.push({ tipo: 'causa-tradutor', de: 'juiz', para: 'aprovados' })
  if (d('causa_auditor') === 1) ev.push({ tipo: 'causa-auditor', de: 'juiz', para: 'juiz' })
  if (d('causa_usuario') === 1) ev.push({ tipo: 'causa-usuario', de: 'juiz', para: 'voce' })
  const saltou = ['propostos', 'conferidos', 'corrigidos', 'reconferidos', 'causa_tradutor', 'causa_auditor', 'causa_usuario'].some((k) => Math.abs(d(k)) > 1)
  return saltou || ev.length > 1 ? [] : ev
}

// O auditor responde em JSON; a tela mostra os pares que já chegaram inteiros: [{ trecho, problema }], 'lendo' ou 'fiel'.
export function falaDoAuditor(texto) {
  const pares = [...(texto ?? '').matchAll(/\{\s*"trecho"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"problema"\s*:\s*"((?:[^"\\]|\\.)*)"\s*(?:,\s*"certo"\s*:\s*"(?:[^"\\]|\\.)*"\s*)?\}/g)]
    .map((m) => ({ trecho: m[1].replace(/\\(.)/g, '$1'), problema: m[2].replace(/\\(.)/g, '$1') }))
  if (pares.length) return pares
  return /\[\s*\]/.test(texto ?? '') ? 'fiel' : 'lendo'
}
