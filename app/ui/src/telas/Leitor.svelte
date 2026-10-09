<script>
  // Leitor: o texto aprovado do livro para ler, marcar, anotar e citar. Não corrige nada (isso é a tela "Ler e corrigir").
  // ponytail: o texto é montado aqui a partir do Markdown (ênfase, quebras, notas viram número); imagens e tabelas não aparecem.
  // Passar pelo mesmo caminho do EPUB (Pandoc) quando isso fizer falta.
  import Botao from '../lib/Botao.svelte'
  import Chip from '../lib/Chip.svelte'
  import Progresso from '../lib/Progresso.svelte'
  import { api } from '../lib/api.js'
  import { contem } from '../lib/realce.js'
  import { simples, abnt, lugar } from '../lib/citacao.js'

  let { id } = $props()
  let linhas = $state(null)
  let livro = $state({ titulo: id, autor: '' })
  let marc = $state([])
  let erro = $state('')
  let cap = $state(0)
  let gaveta = $state('')          // '' | 'sumario' | 'marcacoes' | 'busca'
  let q = $state('')
  let menu = $state(null)          // { x, y, trecho, i, origem } sobre o trecho selecionado
  let anotando = $state(null)      // id da marcação cuja nota está aberta
  let copiado = $state('')
  let letra = $state(100)
  let artigo = $state()
  const CHAVE = 'estante.leitor.' + id      // só conveniência deste navegador: capítulo e tamanho da letra

  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const nivel = (raw) => raw.match(/^#+/)?.[0].length ?? 0
  // Markdown do livro -> HTML mínimo. Tudo é escapado antes; só entram as marcas que este código escreve.
  function html(raw) {
    let t = raw.replace(/^#+\s*/, '').replace(/\s*\{[.#][^}]*\}\s*$/, '').replace(/^>\s?/, '').replace(/\[(\d+\.)\]\{\.pnum\}/, '$1')
      .replace(/!?\[([^\]]*)\]\((?:[^()\s]|\([^()\s]*\))+\)/g, '$1').replace(/<br\s*\/?>/g, '\n')
    t = esc(t).replace(/\[\^([^\]]+)\]/g, '<sup>$1</sup>').replace(/(?<!\\)\*\*(.+?)(?<!\\)\*\*/g, '<strong>$1</strong>').replace(/(?<!\\)\*(.+?)(?<!\\)\*/g, '<em>$1</em>')
    return t.replace(/\\(.)/g, '$1').replace(/\n/g, '<br>')
  }
  const texto = (raw) => html(raw).replace(/<br>/g, '\n').replace(/<[^>]+>/g, '').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')

  // capítulos: cada título de nível 1 ou 2 abre um; o que vem antes do primeiro título é a abertura
  let caps = $derived.by(() => {
    const out = []
    for (const l of linhas ?? []) {
      const n = l.tipo === 'titulo' ? nivel(l.raw) : 0
      if (!out.length || (n && n <= 2)) out.push({ titulo: n ? texto(l.raw) : 'Abertura', nivel: n || 1, blocos: [] })
      out.at(-1).blocos.push(l)
    }
    return out
  })
  let atual = $derived(caps[Math.min(cap, caps.length - 1)])
  let total = $derived((linhas ?? []).length)
  let antes = $derived(caps.slice(0, cap).reduce((s, c) => s + c.blocos.length, 0))
  let achados = $derived(q.trim().length > 1 ? caps.flatMap((c, k) => c.blocos.filter((l) => contem(texto(l.raw), q)).map((l) => ({ k, l }))).slice(0, 80) : [])
  // onde cada marcação está hoje: na linha em que foi feita, se o trecho continua lá; senão em qualquer lugar do livro; senão "sem lugar"
  let onde = $derived.by(() => {
    const m = {}
    for (const x of marc) {
      const cand = (linhas ?? []).filter((l) => texto(l.raw).includes(x.trecho))
      m[x.id] = cand.find((l) => l.i === x.i) ?? cand[0] ?? null
    }
    return m
  })

  async function carrega() {
    try {
      linhas = await api(`/api/livro/${id}/linhas`); marc = await api(`/api/leitor/${id}/marcacoes`)
      livro = (await api('/api/livros')).find((b) => b.id === id) ?? livro
      try { const g = JSON.parse(localStorage.getItem(CHAVE) ?? '{}'); cap = g.cap ?? 0; letra = g.letra ?? 100 } catch { /* sem armazenamento: começa do início */ }
    } catch (e) { erro = e.message; linhas = linhas ?? [] }
  }
  $effect(() => { carrega() })
  $effect(() => { try { localStorage.setItem(CHAVE, JSON.stringify({ cap, letra })) } catch { /* idem */ } })

  // pinta as marcações do capítulo com a API de realce do navegador: o texto da página não é reescrito
  function intervalo(el, trecho) {
    const ini = el.textContent.indexOf(trecho)
    if (ini < 0) return null
    const r = new Range(); let pos = 0, posto = false
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const fim = pos + n.length
      if (!posto && ini < fim) { r.setStart(n, ini - pos); posto = true }
      if (posto && ini + trecho.length <= fim) { r.setEnd(n, ini + trecho.length - pos); return r }
      pos = fim
    }
    return null
  }
  $effect(() => {
    if (!artigo || !atual || !globalThis.CSS?.highlights) return
    const rs = []
    for (const x of marc) {
      const l = onde[x.id]; const el = l && artigo.querySelector(`[data-i="${l.i}"]`)
      const r = el && intervalo(el, x.trecho)
      if (r) rs.push(r)
    }
    CSS.highlights.set('marca', new Highlight(...rs))
    return () => CSS.highlights.delete('marca')
  })

  function selecionou() {
    const s = getSelection(); const trecho = s?.toString().replace(/\s+/g, ' ').trim()
    const el = s?.anchorNode?.parentElement?.closest('[data-i]')
    if (!trecho || trecho.length < 3 || !el || !artigo.contains(el)) { menu = null; return }
    const r = s.getRangeAt(0).getBoundingClientRect()
    const l = atual.blocos.find((b) => b.i === +el.dataset.i)
    // marcação só dentro de um parágrafo (é o que dá para reencontrar depois); citação vale para qualquer seleção
    menu = { x: r.left + r.width / 2, y: r.top, trecho, i: l.i, origem: l.pagina, cabe: texto(l.raw).replace(/\s+/g, ' ').includes(trecho) }
  }
  async function salva(nova) {
    try { marc = await api(`/api/leitor/${id}/marcacoes`, 'PUT', nova); erro = '' } catch (e) { erro = e.message }
  }
  function marca(comNota) {
    const l = atual.blocos.find((b) => b.i === menu.i)
    const cru = texto(l.raw); const p = cru.replace(/\s+/g, ' ').indexOf(menu.trecho)
    const x = { id: Date.now().toString(36), i: menu.i, trecho: cru.includes(menu.trecho) ? menu.trecho : menu.trecho, nota: '', cor: 'marca', origem: menu.origem, quando: new Date().toISOString().slice(0, 16) }
    if (p < 0) return
    salva([...marc, x]); getSelection().removeAllRanges(); menu = null
    if (comNota) { gaveta = 'marcacoes'; anotando = x.id }
  }
  async function copia(fn) {
    const t = fn(menu.trecho, livro, menu.origem)
    try { await navigator.clipboard.writeText(t); copiado = t } catch { copiado = t }
    menu = null; setTimeout(() => (copiado = ''), 6000)
  }
  function vai(k, i) { cap = k; gaveta = ''; setTimeout(() => (i ? artigo?.querySelector(`[data-i="${i}"]`)?.scrollIntoView({ block: 'center' }) : scrollTo({ top: 0 })), 60) }
  const capDe = (l) => caps.findIndex((c) => c.blocos.includes(l))
  function fichamento() {
    const t = `# Fichamento — ${livro.titulo}${livro.autor ? ' (' + livro.autor + ')' : ''}\n\n` + marc.map((x) => `> ${x.trecho}\n\n— ${lugar(onde[x.id]?.pagina ?? x.origem) || 'sem página registrada'}${x.nota ? '\n\n' + x.nota : ''}\n`).join('\n')
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([t], { type: 'text/markdown' })); a.download = `fichamento-${id}.md`; a.click(); URL.revokeObjectURL(a.href)
  }
  function tecla(e) {
    if (e.target.closest('input, textarea')) return
    if (e.key === 'ArrowRight' && cap < caps.length - 1) vai(cap + 1); else if (e.key === 'ArrowLeft' && cap > 0) vai(cap - 1); else if (e.key === 'Escape') { gaveta = ''; menu = null }
  }
</script>

<svelte:window onkeydown={tecla} />

<header class="barra">
  <a class="rotulo volta" href="#livro/{id}">← Livro</a>
  <span class="onde"><strong>{livro.titulo}</strong>{#if atual} · {atual.titulo}{/if}</span>
  <span class="ferr">
    <button class="rotulo" aria-pressed={gaveta === 'busca'} onclick={() => (gaveta = gaveta === 'busca' ? '' : 'busca')}>Buscar</button>
    <button class="rotulo" aria-label="Letra menor" onclick={() => (letra = Math.max(80, letra - 10))}>A−</button>
    <button class="rotulo" aria-label="Letra maior" onclick={() => (letra = Math.min(160, letra + 10))}>A+</button>
    <button class="rotulo" aria-pressed={gaveta === 'sumario'} onclick={() => (gaveta = gaveta === 'sumario' ? '' : 'sumario')}>Sumário</button>
    <button class="rotulo" aria-pressed={gaveta === 'marcacoes'} onclick={() => (gaveta = gaveta === 'marcacoes' ? '' : 'marcacoes')}>Marcações ({marc.length})</button>
  </span>
</header>
{#if erro}<p role="alert"><Chip estado="erro">{erro}</Chip></p>{/if}
{#if copiado}<p class="aviso" aria-live="polite"><Chip estado="ok">Citação copiada</Chip> <span class="rotulo">{copiado}</span></p>{/if}

{#if gaveta === 'sumario'}
  <nav class="gaveta" aria-label="Sumário"><ol>{#each caps as c, k}<li class:aqui={k === cap} class:sub={c.nivel > 1}><button onclick={() => vai(k)}>{c.titulo}</button></li>{/each}</ol></nav>
{:else if gaveta === 'busca'}
  <div class="gaveta"><input type="search" bind:value={q} placeholder="Buscar neste livro" aria-label="Buscar neste livro" />
    <ol>{#each achados as a}<li><button onclick={() => vai(a.k, a.l.i)}><span class="rotulo">{caps[a.k].titulo}</span> {texto(a.l.raw).slice(0, 160)}</button></li>
      {:else}{#if q.trim().length > 1}<li class="rotulo">Nada encontrado.</li>{/if}{/each}</ol></div>
{:else if gaveta === 'marcacoes'}
  <div class="gaveta">
    {#if marc.length}<div><Botao variante="texto" onclick={fichamento}>Exportar fichamento (.md)</Botao></div>{/if}
    <ol>{#each marc as x (x.id)}
      {@const l = onde[x.id]}
      <li class="marcacao">
        <button class="trecho" disabled={!l} onclick={() => vai(capDe(l), l.i)}>«{x.trecho}»</button>
        <span class="rotulo">{l ? lugar(l.pagina) || caps[capDe(l)]?.titulo : 'sem lugar: o trecho mudou ou saiu do texto'}</span>
        {#if anotando === x.id}
          <textarea rows="3" value={x.nota} aria-label="Nota" onblur={(e) => { salva(marc.map((m) => (m.id === x.id ? { ...m, nota: e.currentTarget.value } : m))); anotando = null }}></textarea>
        {:else if x.nota}<p class="nota">{x.nota}</p>{/if}
        <span class="acoes"><button class="rotulo" onclick={() => (anotando = x.id)}>{x.nota ? 'Editar nota' : 'Anotar'}</button>
          <button class="rotulo" onclick={() => salva(marc.filter((m) => m.id !== x.id))}>Tirar</button></span>
      </li>
    {:else}<li class="rotulo">Nenhuma marcação ainda. Selecione um trecho do texto para marcar, anotar ou copiar a citação.</li>{/each}</ol>
  </div>
{/if}

{#if linhas === null}
  <Progresso rotulo="Abrindo o livro" />
{:else if !linhas.length}
  <p class="leitura vazio">Este livro ainda não tem texto aprovado. Aceite blocos na <a href="#revisao/{id}">revisão</a>.</p>
{:else}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <article bind:this={artigo} style:font-size="{letra}%" onmouseup={selecionou} onkeyup={selecionou}>
    {#each atual.blocos as l (l.i)}
      {#if l.tipo === 'titulo'}<svelte:element this={'h' + Math.min(4, nivel(l.raw) + 1)} data-i={l.i}>{@html html(l.raw)}</svelte:element>
      {:else}<p class="leitura" class:citacao={l.raw.startsWith('>')} data-i={l.i} title={lugar(l.pagina)}>{@html html(l.raw)}</p>{/if}
    {/each}
  </article>
  <footer class="pe">
    <Botao variante="texto" disabled={cap === 0} onclick={() => vai(cap - 1)}>← Capítulo anterior</Botao>
    <span class="rotulo">{Math.round(100 * (antes + atual.blocos.length) / total)}% · capítulo {cap + 1} de {caps.length}</span>
    <Botao variante="texto" disabled={cap >= caps.length - 1} onclick={() => vai(cap + 1)}>Próximo capítulo →</Botao>
  </footer>
{/if}

{#if menu}
  <div class="menu" style:left="{menu.x}px" style:top="{menu.y}px" role="toolbar" aria-label="Trecho selecionado">
    {#if menu.cabe}<button onclick={() => marca(false)}>Marcar</button><button onclick={() => marca(true)}>Anotar</button>{/if}
    <button onclick={() => copia(simples)}>Copiar citação</button><button onclick={() => copia(abnt)}>ABNT</button>
  </div>
{/if}

<style>
  .barra { position: sticky; top: 0; z-index: 3; display: flex; flex-wrap: wrap; gap: var(--e3) var(--e6); align-items: baseline; padding: var(--e4) 0; background: var(--fundo); border-bottom: 1px solid var(--linha); }
  .onde { flex: 1 1 14rem; color: var(--apagado); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .onde strong { color: var(--papel); font-weight: 500; }
  .ferr { display: flex; flex-wrap: wrap; gap: var(--e4); }
  .ferr button, .acoes button { all: unset; cursor: pointer; font-family: var(--mono); font-size: var(--t-rotulo); text-transform: uppercase; letter-spacing: 0.18em; color: var(--apagado); border-bottom: 1px solid transparent; }
  .ferr button:hover, .ferr button[aria-pressed='true'], .acoes button:hover { color: var(--papel); border-color: var(--acento); }
  .ferr button:focus-visible, .acoes button:focus-visible, .gaveta button:focus-visible, .menu button:focus-visible { outline: 1px solid var(--acento); outline-offset: 3px; }
  .aviso { padding: var(--e3) 0; display: flex; gap: var(--e4); align-items: baseline; flex-wrap: wrap; }
  .gaveta { display: grid; gap: var(--e4); padding: var(--e4) 0 var(--e6); border-bottom: 1px solid var(--linha); max-height: 50vh; overflow: auto; }
  .gaveta ol { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--e2); }
  .gaveta li button { all: unset; cursor: pointer; color: var(--apagado); } .gaveta li button:hover:not(:disabled), .gaveta li.aqui button { color: var(--papel); }
  .gaveta li.sub { padding-left: var(--e6); }
  .marcacao { display: grid; gap: var(--e2); padding: var(--e3) 0 var(--e3) var(--e4); border-left: 1px solid var(--acento); }
  .marcacao .trecho { font-family: var(--leitura); color: var(--papel); } .marcacao .trecho:disabled { cursor: default; color: var(--apagado); }
  .nota { margin: 0; color: var(--apagado); white-space: pre-wrap; } .acoes { display: flex; gap: var(--e4); }
  textarea { width: 100%; }
  article { max-width: 66ch; margin: 0 auto; padding: var(--e8) 0 var(--e12, 64px); }
  article p { margin: 0 0 1em; line-height: 1.7; } article h2, article h3, article h4 { margin: 1.6em 0 0.7em; line-height: 1.15; }
  .citacao { color: var(--apagado); font-style: italic; padding-left: var(--e8); }
  article :global(sup) { font-size: 0.7em; color: var(--apagado); }
  :global(::highlight(marca)) { background: color-mix(in srgb, var(--acento) 34%, transparent); }
  .vazio { padding: var(--e8) 0; }
  .pe { display: flex; flex-wrap: wrap; gap: var(--e4); justify-content: space-between; align-items: center; padding: var(--e6) 0 var(--e12, 64px); border-top: 1px solid var(--linha); max-width: 66ch; margin: 0 auto; }
  .menu { position: fixed; z-index: 5; transform: translate(-50%, calc(-100% - 8px)); display: flex; gap: 1px; background: var(--linha-forte); border: 1px solid var(--linha-forte); border-radius: var(--raio); overflow: hidden; }
  .menu button { all: unset; cursor: pointer; padding: var(--e2) var(--e4); background: var(--superficie, var(--fundo)); font-family: var(--mono); font-size: var(--t-rotulo); text-transform: uppercase; letter-spacing: 0.14em; }
  .menu button:hover { background: var(--acento); color: var(--fundo); }
</style>
