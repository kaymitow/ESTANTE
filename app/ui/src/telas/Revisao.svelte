<script>
  import Chip from '../lib/Chip.svelte'
  import Botao from '../lib/Botao.svelte'
  import Progresso from '../lib/Progresso.svelte'
  import { api } from '../lib/api.js'

  let { id } = $props()
  let blocos = $state(null)      // null = carregando
  let erro = $state('')
  let filtro = $state('revisar')
  let sel = $state(null)         // id do bloco aberto
  let texto = $state('')         // texto em edição do bloco aberto
  let verPagina = $state(false)
  let ocupado = $state(false)
  let relendo = $state(null)      // página do scan sendo relida agora
  let releitura = $state({})      // página -> texto da leitura nova (só para consulta: nada entra no livro sozinho)
  async function rele(n) {
    relendo = n
    try { const r = await api('/api/ocr', 'POST', { livro: id, scan: n }); releitura = { ...releitura, [n]: r.resultado || '(os modelos não devolveram texto)' }; erro = '' }
    catch (e) { erro = e.message } finally { relendo = null }
  }

  const FILTROS = [
    { id: 'revisar', nome: 'Pedem atenção', f: (b) => !b.aceito && b.status === 'revisar' },
    { id: 'andamento', nome: 'Em andamento', f: (b) => b.status === 'andamento' },
    { id: 'juiz', nome: 'Corrigidos pelo juiz', f: (b) => !b.aceito && b.status === 'juiz' },
    { id: 'aprovado', nome: 'Aprovados pelos modelos', f: (b) => !b.aceito && b.status === 'aprovado' },
    { id: 'aceito', nome: 'Aceitos por você', f: (b) => b.aceito },
    { id: 'todos', nome: 'Todos', f: () => true },
  ]
  const conta = (fid) => blocos.filter(FILTROS.find((x) => x.id === fid).f).length
  // leitura crítica: ordem por nota de risco (mais risco primeiro) e os trechos suspeitos sublinhados na fonte. Só ordem: nada muda no bloco
  let critica = $state(false)
  let lista = $derived(blocos ? (() => { const l = blocos.filter(FILTROS.find((x) => x.id === filtro).f); return critica ? [...l].sort((a, b) => (b.risco ?? 0) - (a.risco ?? 0)) : l })() : [])
  // parte o original em trechos normais e suspeitos (com o motivo), para sublinhar
  const partesFonte = (b) => { const t = b.fonte ?? ''; const out = []; let i = 0; for (const [s, e, m] of [...(b.trechos_risco ?? [])].sort((x, y) => x[0] - y[0])) { if (s < i) continue; out.push({ t: t.slice(i, s) }, { t: t.slice(s, e), motivo: m }); i = e } out.push({ t: t.slice(i) }); return out }
  let atual = $derived(blocos?.find((b) => b.id === sel) ?? null)
  let aceitos = $derived(blocos ? blocos.filter((b) => b.aceito).length : 0)
  let mudou = $derived(atual && texto.trim() !== textoDe(atual))

  // comparações com outras cópias do livro (feitas na tela do livro): o bloco que difere mostra aqui o que a outra cópia diz
  let copias = $state([])
  $effect(() => { fetch(`/api/copias/${id}`).then((r) => (r.ok ? r.json() : [])).then((c) => (copias = c)).catch(() => {}) })
  let outras = $derived(atual ? copias.flatMap((c) => {
    const d = c.diferencas.find((x) => x.id === atual.id)
    return d ? [{ arquivo: c.arquivo, ...d }] : c.ausentes.some((x) => x.id === atual.id) ? [{ arquivo: c.arquivo, ausente: true }] : []
  }) : [])

  function textoDe(b) { return b.texto || b.resultado }
  function abre(b) { sel = b?.id ?? null; texto = b ? textoDe(b) : '' }

  async function carrega() {
    try {
      const r = await fetch(`/api/pipeline/${id}/rascunho`)
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || r.statusText)
      blocos = j.blocos
      if (!conta('revisar')) filtro = conta('juiz') ? 'juiz' : conta('aprovado') ? 'aprovado' : conta('andamento') ? 'andamento' : 'todos'
      abre(blocos.filter(FILTROS.find((x) => x.id === filtro).f)[0])
    } catch (e) { erro = e.message; blocos = [] }
  }
  $effect(() => { carrega() })

  async function manda(corpo) {
    ocupado = true; erro = ''
    try {
      const r = await fetch(`/api/revisao/${id}/aceitar`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || r.statusText)
      return true
    } catch (e) { erro = e.message; return false } finally { ocupado = false }
  }

  async function aceita(desfazer = false) {
    const b = atual
    if (!b || ocupado) return
    const i = lista.indexOf(b)
    const prox = lista[i + 1] ?? lista[i - 1] ?? null
    const editado = !desfazer && mudou ? texto.trim() : null
    if (!(await manda({ ids: [b.id], desfazer, ...(editado !== null ? { texto: editado } : {}) }))) return
    b.aceito = !desfazer
    if (editado !== null) b.texto = editado
    if (filtro !== 'todos') abre(prox)
  }

  async function mudaTipo(nivel) {
    const b = atual
    if (!b || !(await manda({ ids: [b.id], nivel }))) return
    b.tipo = nivel ? 'titulo' : 'paragrafo'; b.nivel = nivel || null
  }

  async function aceitaAprovados() {
    if (await manda({ aprovados: true })) { for (const b of blocos) if (b.status === 'aprovado') b.aceito = true; abre(lista[0]) }
  }

  function passo(d) { const i = lista.indexOf(atual); const b = lista[i + d]; if (b) { abre(b); document.querySelector('.itens .on')?.scrollIntoView({ block: 'nearest' }) } }
  function tecla(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); aceita(atual?.aceito && !mudou); return }
    if (e.target.matches('textarea, input, select')) return
    if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); passo(1) }
    if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); passo(-1) }
  }
</script>

<svelte:window onkeydown={tecla} />

<header class="topo">
  <a class="rotulo volta" href="#livro/{id}">← Livro</a>
  <h2>Revisão</h2>
  {#if blocos?.length}
    <div class="barra"><Progresso valor={aceitos / blocos.length} rotulo="{aceitos} de {blocos.length} blocos no livro" /></div>
  {/if}
</header>

{#if blocos === null}
  <Progresso rotulo="Abrindo o rascunho" />
{:else if !blocos.length}
  <div class="vazio">{#if erro}<Chip estado="erro">{erro}</Chip>{/if}<p class="leitura">O rascunho aparece aqui quando o processamento do livro termina.</p></div>
{:else}
  <div class="filtros" role="tablist" aria-label="Filtro">
    {#each FILTROS as f}
      <button role="tab" aria-selected={filtro === f.id} class:on={filtro === f.id} onclick={() => { filtro = f.id; abre(lista[0]) }}>{f.nome}<span class="rotulo">{conta(f.id)}</span></button>
    {/each}
    <button class="alterna" aria-pressed={critica} title="Ordena pelos blocos com mais sinais de risco (expressão, fala, itálico) e sublinha os trechos na fonte" onclick={() => (critica = !critica)}>Leitura crítica</button>
    {#if conta('aprovado')}
      <span class="lote"><Botao disabled={ocupado} onclick={aceitaAprovados}>Aceitar os {conta('aprovado')} aprovados</Botao>
        <span class="rotulo">Títulos e blocos em dúvida ficam de fora</span></span>
    {/if}
  </div>
  {#if erro}<p class="erro" role="alert"><Chip estado="erro">{erro}</Chip></p>{/if}

  <div class="mesa">
    <ul class="itens">
      {#each lista as b (b.id)}
        <li><button class:on={sel === b.id} onclick={() => abre(b)}>
          <span class="rotulo">{b.md ? 's.' : 'p.'} {b.paginas[0]}{b.tipo === 'titulo' ? ' · título' : b.tipo === 'imagem' ? ' · imagem' : ''}</span>
          <i class={b.aceito ? 'aceito' : b.status}></i>
          <span class="trecho">{textoDe(b)}</span>
        </button></li>
      {:else}
        <li class="nada rotulo">Nada neste filtro.</li>
      {/each}
    </ul>

    {#if atual}
      {#key atual.id}
        <article>
          <div class="cab">
            {#if atual.aceito}<Chip estado="ok">Aceito · no livro</Chip>{:else if atual.status === 'aprovado'}<Chip estado="ok">Aprovado pelos modelos</Chip>{:else if atual.status === 'andamento'}<Chip>Em andamento · só leitura por enquanto</Chip>{:else if atual.status === 'juiz'}<Chip estado="revisar">Corrigido pelo juiz · confira</Chip>{:else}<Chip estado="revisar">Pede atenção</Chip>{/if}
            <span class="rotulo">{atual.id} · {atual.md ? 'seção' : 'página' + (atual.paginas.length > 1 ? 's' : '')} {atual.paginas.join('–')}</span>
            {#if atual.tipo !== 'imagem'}
              <select class="tipo" aria-label="Tipo do bloco" value={atual.tipo === 'titulo' ? (atual.nivel || 1) : 0} onchange={(e) => mudaTipo(+e.currentTarget.value)} disabled={ocupado}>
                <option value={0}>Parágrafo</option><option value={1}>Título 1</option><option value={2}>Título 2</option><option value={3}>Título 3</option>
              </select>
            {/if}
            {#if !atual.md}<button class="rotulo alterna" onclick={() => (verPagina = !verPagina)} aria-pressed={verPagina}>{verPagina ? 'Ver texto da fonte' : 'Ver a página'}</button>{/if}
          </div>

          {#if atual.problemas.length}
            <ul class="problemas">{#each atual.problemas as p}<li>{p}</li>{/each}</ul>
          {/if}
          {#each outras as o}
            <div class="outra">
              <span class="rotulo">Outra cópia · {o.arquivo}</span>
              {#if o.ausente}<p>Este bloco não está na outra cópia.</p>
              {:else}
                {#each o.mudancas as m}<p class="muda"><span class="antes">{m.antes ? '…' + m.antes : ''}</span> <del>{m.nosso || '∅'}</del> <ins>{m.outra || '∅'}</ins></p>{/each}
                {#if o.total > o.mudancas.length}<span class="rotulo">e mais {o.total - o.mudancas.length}</span>{/if}
              {/if}
              <span class="rotulo">Riscado: a sua fonte · em verde: a outra cópia · nada disso muda o texto</span>
            </div>
          {/each}

          <div class="lados">
            <section>
              <div class="rotulo">Fonte</div>
              {#if verPagina && !atual.md}
                {#each atual.paginas as n}<img src="/api/livro/{id}/pagina/{n}" alt="Página {n} do arquivo de origem" loading="lazy" />
                  <button class="elo" disabled={relendo !== null} onclick={() => rele(n)}>{relendo === n ? 'Relendo (leva cerca de um minuto)…' : `Reler a página ${n} com os modelos`}</button>
                  {#if releitura[n]}<p class="rotulo">Leitura nova da página {n} · copie o que servir para o seu texto</p><p class="leitura fonte releitura">{releitura[n]}</p>{/if}
                {/each}
              {:else}
                <p class="leitura fonte">{#if critica}{#each partesFonte(atual) as p}{#if p.motivo}<mark class="suspeito" title={p.motivo}>{p.t}</mark>{:else}{p.t}{/if}{/each}{:else}{atual.fonte}{/if}</p>
              {/if}
            </section>
            <section>
              <div class="rotulo">Resultado{mudou ? ' · editado' : ''}</div>
              <textarea class="leitura" bind:value={texto} rows={Math.max(6, Math.ceil(texto.length / 55))} spellcheck="false" aria-label="Texto do bloco"></textarea>
            </section>
          </div>

          <div class="botoes">
            {#if atual.aceito && !mudou}
              <Botao disabled={ocupado} onclick={() => aceita(true)}>Tirar do livro</Botao>
            {:else}
              <Botao variante="cheio" disabled={ocupado || !texto.trim()} onclick={() => aceita()}>{mudou ? 'Aceitar com a edição' : 'Aceitar'}</Botao>
            {/if}
            {#if mudou}<Botao variante="texto" onclick={() => (texto = textoDe(atual))}>Desfazer edição</Botao>{/if}
            <span class="rotulo atalhos">Ctrl+Enter aceita · J / K muda de bloco</span>
          </div>

          {#if atual.trocas?.length}
            <details>
              <summary class="rotulo">Grafias trocadas por regra ({atual.trocas.length})</summary>
              <p class="trocas">{atual.trocas.join(' · ')}</p>
            </details>
          {/if}
          {#if atual.status === 'juiz' && atual.antes_do_juiz}
            <div class="fala"><span class="rotulo">Como o tradutor tinha escrito, antes do juiz</span><p>{atual.antes_do_juiz}</p></div>
          {/if}
          {#if atual.conversa.length}
            <details>
              <summary class="rotulo">Conversa dos modelos ({atual.conversa.length})</summary>
              {#each atual.conversa as c}<div class="fala"><span class="rotulo">{c.quem}</span><p>{c.disse}</p></div>{/each}
            </details>
          {/if}
        </article>
      {/key}
    {:else}
      <article class="vazio"><p class="leitura">{aceitos === blocos.length ? 'Tudo aceito. O livro está montado.' : 'Escolha um bloco na lista.'}</p></article>
    {/if}
  </div>
{/if}

<style>
  .topo { padding-bottom: var(--e6); border-bottom: 1px solid var(--linha); display: grid; gap: var(--e3); }
  .volta { text-decoration: none; justify-self: start; } .volta:hover { color: var(--papel); }
  .barra { max-width: 34rem; margin-top: var(--e3); }
  .vazio { padding: var(--e12) 0; display: grid; gap: var(--e4); justify-items: start; }
  .erro { padding-top: var(--e4); }

  .filtros { display: flex; flex-wrap: wrap; gap: var(--e2) var(--e8); align-items: center; padding: var(--e4) 0; border-bottom: 1px solid var(--linha); }
  .filtros > button { all: unset; cursor: pointer; display: flex; gap: var(--e2); align-items: baseline; color: var(--apagado); padding: var(--e2) 0; border-bottom: 1px solid transparent; transition: color var(--rapido), border-color var(--medio) var(--curva); }
  .filtros > button:hover { color: var(--papel); }
  .filtros > button.on { color: var(--papel); border-color: var(--acento); }
  .filtros > button:focus-visible { outline: 1px solid var(--acento); outline-offset: 3px; }
  .lote { margin-left: auto; display: flex; gap: var(--e4); align-items: center; flex-wrap: wrap; }

  .mesa { display: grid; grid-template-columns: minmax(14rem, 20rem) minmax(0, 1fr); gap: var(--e8); align-items: start; }
  .itens { list-style: none; margin: 0; padding: 0; position: sticky; top: 0; max-height: 100vh; overflow-y: auto; border-right: 1px solid var(--linha); }
  .itens button { all: unset; box-sizing: border-box; cursor: pointer; width: 100%; display: grid; grid-template-columns: 1fr auto; gap: var(--e1) var(--e2); padding: var(--e3) var(--e4) var(--e3) var(--e3);
    border-bottom: 1px solid var(--linha); border-left: 2px solid transparent; transition: background var(--rapido), border-color var(--rapido); }
  .itens button:hover { background: var(--superficie); }
  .itens button.on { background: var(--superficie); border-left-color: var(--acento); }
  .itens button:focus-visible { outline: 1px solid var(--acento); outline-offset: -1px; }
  .itens i { width: 6px; height: 6px; border-radius: 50%; align-self: center; background: var(--revisar); }
  .itens i.juiz { background: var(--acento); }
  .itens i.aprovado { background: var(--ok); } .itens i.aceito { background: transparent; border: 1px solid var(--ok); }
  .trecho { grid-column: 1 / -1; font-family: var(--leitura); font-size: 0.9rem; color: var(--apagado); display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .on .trecho { color: var(--papel); }
  .nada { padding: var(--e6) var(--e3); }

  article { padding: var(--e6) 0 var(--e16); display: grid; gap: var(--e6); min-width: 0; animation: entra var(--medio) var(--curva) both; }
  @keyframes entra { from { opacity: 0; transform: translateY(8px); } }
  .cab { display: flex; flex-wrap: wrap; gap: var(--e3) var(--e6); align-items: center; }
  .alterna { all: unset; cursor: pointer; margin-left: auto; font-family: var(--mono); font-size: var(--t-rotulo); text-transform: uppercase; letter-spacing: 0.22em; color: var(--apagado); border-bottom: 1px solid var(--linha-forte); }
  .alterna:hover { color: var(--papel); border-color: var(--acento); } .alterna:focus-visible { outline: 1px solid var(--acento); outline-offset: 3px; }
  .tipo { font-family: var(--mono); font-size: var(--t-rotulo); text-transform: uppercase; letter-spacing: 0.12em; padding: var(--e1) var(--e2); }
  .problemas { margin: 0; padding: var(--e3) var(--e4) var(--e3) var(--e8); border-left: 2px solid var(--revisar); background: var(--superficie); color: var(--revisar); display: grid; gap: var(--e1); }
  .outra { display: grid; gap: var(--e2); padding: var(--e3) var(--e4); border-left: 2px solid var(--linha-forte); }
  .outra p { margin: 0; overflow-wrap: anywhere; } .outra .antes { color: var(--apagado); }
  .outra del { color: var(--revisar); } .outra ins { color: var(--ok); text-decoration: none; }
  .lados { display: grid; grid-template-columns: 1fr 1fr; gap: var(--e8); align-items: start; }
  .lados section { display: grid; gap: var(--e3); min-width: 0; }
  .fonte { color: var(--apagado); white-space: pre-wrap; }
  .suspeito { background: none; color: var(--papel); text-decoration: underline wavy var(--revisar); text-underline-offset: 0.25em; }
  img { width: 100%; border: 1px solid var(--linha); background: #fff; }
  textarea { field-sizing: content; width: 100%; max-width: none; resize: vertical; color: var(--papel); background: transparent; border: 0; border-left: 1px solid var(--linha-forte); padding: 0 0 0 var(--e4); transition: border-color var(--rapido); }
  textarea:focus-visible { outline: none; border-left-color: var(--acento); }
  .botoes { display: flex; flex-wrap: wrap; gap: var(--e6); align-items: center; }
  .atalhos { margin-left: auto; }
  details { border-top: 1px solid var(--linha); padding-top: var(--e4); }
  summary { cursor: pointer; } summary:hover { color: var(--papel); }
  .fala { display: grid; gap: var(--e1); padding: var(--e3) 0; border-bottom: 1px solid var(--linha); }
  .fala p { color: var(--apagado); white-space: pre-wrap; }
  .trocas { font-family: var(--mono); font-size: 0.8125rem; color: var(--apagado); padding-top: var(--e3); }

  @media (max-width: 1100px) { .lados { grid-template-columns: 1fr; } }
  @media (max-width: 900px) { .mesa { grid-template-columns: 1fr; } .itens { position: static; max-height: 16rem; border-right: 0; } .lote { margin-left: 0; } }
  @media (prefers-reduced-motion: reduce) { article { animation: none; } }
  .releitura { white-space: pre-wrap; border-left: 1px solid var(--ok); padding-left: var(--e4); }
</style>
