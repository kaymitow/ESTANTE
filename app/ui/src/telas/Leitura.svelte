<script>
  import Botao from '../lib/Botao.svelte'
  import Chip from '../lib/Chip.svelte'
  import Progresso from '../lib/Progresso.svelte'
  import { api } from '../lib/api.js'
  import { contem, partes } from '../lib/realce.js'

  let { id } = $props()
  let linhas = $state(null)
  let historico = $state([])
  let erro = $state('')
  let aberto = $state(null)      // índice da linha em edição
  let texto = $state('')
  let motivo = $state('')
  let ocupado = $state(false)
  let verHistorico = $state(false)
  let q = $state('')            // busca dentro deste livro (ignora acentos e maiúsculas)

  async function carrega() {
    try { linhas = await api(`/api/livro/${id}/linhas`); historico = await api(`/api/historico?livro=${id}&n=30`) }
    catch (e) { erro = e.message; linhas = linhas ?? [] }
  }
  $effect(() => { carrega() })

  // texto para leitura: tira a marcação do Markdown sem mexer nas palavras
  function limpo(raw) {
    return raw.replace(/^#+\s*/, '').replace(/\s*\{[.#][^}]*\}\s*$/, '').replace(/^>\s?/, '')
      .replace(/\[(\d+\.)\]\{\.pnum\}/, '$1').replace(/!?\[([^\]]*)\]\((?:[^()\s]|\([^()\s]*\))+\)/g, '$1')
      .replace(/<br\s*\/?>/g, '\n').replace(/\[\^[^\]]+\]/g, '').replace(/(?<!\\)\*/g, '').replace(/\\(.)/g, '$1')
  }
  let buscando = $derived(q.trim().length > 1)
  let mostradas = $derived(buscando ? (linhas ?? []).filter((l) => contem(limpo(l.raw), q)) : (linhas ?? []))
  const nivel = (raw) => Math.min(3, raw.match(/^#+/)?.[0].length ?? 1)
  function abre(l) { aberto = l.i; texto = l.raw; motivo = ''; erro = '' }
  async function salva(l) {
    if (texto === l.raw) { aberto = null; return }
    ocupado = true
    try { await api('/api/editar', 'POST', { livro: id, i: l.i, antigo: l.raw, novo: texto.replace(/\s*\n\s*/g, ' '), motivo }); aberto = null; await carrega() }
    catch (e) { erro = e.message } finally { ocupado = false }
  }

  // Lote avulso: marcar parágrafos, passar pelos dois modelos e aceitar as propostas uma a uma. Nada muda no livro sem o aceite.
  const TAREFAS = { limpar_ocr: 'Limpar erros de leitura', atualizar_pt: 'Atualizar português antigo', traduzir: 'Traduzir do inglês', traduzir_de: 'Traduzir do alemão' }
  let modoLote = $state(false)
  let marcadas = $state([])
  let tarefaLote = $state('limpar_ocr')
  let trabalho = $state(null)     // o lote em andamento ou terminado: { id, estado, progresso, itens }
  let fora = $state([])           // propostas descartadas (linhas)
  const marca = (i) => (marcadas = marcadas.includes(i) ? marcadas.filter((x) => x !== i) : [...marcadas, i])
  let propostas = $derived(Object.fromEntries((trabalho?.itens ?? []).map((it, k) => [it.i, { ...it, k }])
    .filter(([i, it]) => ['aprovado', 'revisar'].includes(it.estado) && !it.aceito && !fora.includes(i))))
  async function passa() {
    ocupado = true
    try { const r = await api('/api/lote', 'POST', { livro: id, tarefa: tarefaLote, linhas: marcadas }); trabalho = await api(`/api/lote/${r.id}`); marcadas = []; fora = []; modoLote = false; erro = '' }
    catch (e) { erro = e.message } finally { ocupado = false }
  }
  $effect(() => {
    if (trabalho?.estado !== 'rodando') return
    const lid = trabalho.id
    const t = setInterval(async () => { try { trabalho = await api(`/api/lote/${lid}`) } catch { /* servidor ocupado: tenta de novo */ } }, 2000)
    return () => clearInterval(t)
  })
  async function aceitaProposta(l, it) {
    ocupado = true
    const novo = (it.prefixo + it.resultado).replace(/\s*\n\s*/g, ' ')
    try {
      await api('/api/editar', 'POST', { livro: id, i: l.i, antigo: l.raw, novo, motivo: 'proposta dos modelos: ' + TAREFAS[trabalho.tarefa].toLowerCase() })
      await api(`/api/lote/${trabalho.id}/aceito/${it.k}`, 'POST', { novo })
      trabalho = await api(`/api/lote/${trabalho.id}`); await carrega(); erro = ''
    } catch (e) { erro = e.message } finally { ocupado = false }
  }
</script>

<header class="topo-tela">
  <a class="rotulo volta" href="#livro/{id}">← Livro</a>
  <h2>Corrigir o texto</h2>
  <p class="sub">O texto aprovado do livro. Clique num parágrafo para corrigir; cada correção fica no histórico e pode ser desfeita.</p>
  <div class="ferramentas">
    <input class="busca" type="search" bind:value={q} placeholder="Buscar neste livro" aria-label="Buscar neste livro" />
    {#if buscando}<span class="rotulo">{mostradas.length} {mostradas.length === 1 ? 'trecho' : 'trechos'}</span>{/if}
    <button class="rotulo alterna" onclick={() => { modoLote = !modoLote; marcadas = []; aberto = null }} aria-pressed={modoLote}>{modoLote ? 'Cancelar a seleção' : 'Passar trechos pelos modelos'}</button>
    <button class="rotulo alterna" onclick={() => (verHistorico = !verHistorico)} aria-expanded={verHistorico}>{verHistorico ? 'Esconder' : 'Ver'} histórico ({historico.length})</button>
  </div>
</header>

{#if modoLote}
  <div class="lote">
    <span class="rotulo">Clique nos parágrafos para marcar · {marcadas.length} {marcadas.length === 1 ? 'marcado' : 'marcados'}</span>
    <select bind:value={tarefaLote} aria-label="O que os modelos fazem">{#each Object.entries(TAREFAS) as [k, v]}<option value={k}>{v}</option>{/each}</select>
    <Botao variante="cheio" disabled={ocupado || !marcadas.length} onclick={passa}>Passar pelos modelos</Botao>
  </div>
{/if}
{#if trabalho?.estado === 'rodando'}
  <div class="lote"><Progresso valor={trabalho.progresso || null} rotulo={`Os modelos estão trabalhando: ${trabalho.feito} de ${trabalho.total}`} />
    <Botao variante="texto" onclick={async () => { await api(`/api/lote/${trabalho.id}/parar`, 'POST'); trabalho = await api(`/api/lote/${trabalho.id}`) }}>Parar</Botao></div>
{:else if trabalho}
  <p class="rotulo lote">{trabalho.erro ? `Os modelos pararam: ${trabalho.erro}` : Object.keys(propostas).length ? `${Object.keys(propostas).length} ${Object.keys(propostas).length === 1 ? 'proposta espera' : 'propostas esperam'} o seu aceite, logo abaixo de cada parágrafo.` : 'Nenhuma proposta pendente.'}</p>
{/if}
{#if verHistorico}
  <ol class="historico">
    {#each historico as h}<li><span class="rotulo">{h.data} · {h.hash}</span> {h.msg}</li>{:else}<li class="rotulo">Sem alterações registradas.</li>{/each}
  </ol>
{/if}
{#if erro}<p class="estado" role="alert"><Chip estado="erro">{erro}</Chip></p>{/if}

{#if linhas === null}
  <Progresso rotulo="Abrindo o livro" />
{:else if !linhas.length}
  <p class="estado leitura">Este livro ainda não tem texto aprovado. Aceite blocos na <a href="#revisao/{id}">revisão</a>.</p>
{:else}
  <article>
    {#each mostradas as l (l.i)}
      {#if aberto === l.i}
        <div class="edicao">
          <textarea class="leitura" bind:value={texto} rows={Math.max(3, Math.ceil(texto.length / 70))} spellcheck="false" aria-label="Texto do parágrafo"></textarea>
          <div class="botoes">
            <input bind:value={motivo} placeholder="motivo (opcional)" aria-label="Motivo da correção" />
            <Botao variante="cheio" disabled={ocupado} onclick={() => salva(l)}>Guardar</Botao>
            <Botao variante="texto" onclick={() => (aberto = null)}>Cancelar</Botao>
            <span class="rotulo">{l.pagina}</span>
          </div>
        </div>
      {:else if l.tipo === 'titulo'}
        <svelte:element this={'h' + (nivel(l.raw) + 2)} class="titulo n{nivel(l.raw)}" role="button" tabindex="0" onclick={() => abre(l)} onkeydown={(e) => e.key === 'Enter' && abre(l)}>{limpo(l.raw)}</svelte:element>
      {:else}
        <!-- svelte-ignore a11y_no_noninteractive_element_to_interactive_role -->
        <p class="leitura par" class:citacao={l.raw.startsWith('>')} role="button" tabindex="0" title={l.pagina} class:marcada={marcadas.includes(l.i)} aria-pressed={modoLote ? marcadas.includes(l.i) : undefined} onclick={() => (modoLote ? marca(l.i) : abre(l))} onkeydown={(e) => e.key === 'Enter' && (modoLote ? marca(l.i) : abre(l))}>{#if buscando}{#each partes(limpo(l.raw), q) as p}{#if p.m}<mark>{p.t}</mark>{:else}{p.t}{/if}{/each}{:else}{limpo(l.raw)}{/if}</p>
        {#if propostas[l.i]}{@const it = propostas[l.i]}{@const semMudanca = limpo(it.resultado) === limpo(it.raw)}
          <div class="proposta">
            <p class="rotulo">{semMudanca ? 'Os modelos não chegaram a uma correção' : 'Proposta dos modelos'}{it.estado === 'revisar' ? ' · pede atenção' : ''}</p>
            {#if !semMudanca}<p class="leitura">{limpo(it.resultado)}</p>{/if}
            {#each it.problemas as pr}<p class="rotulo">· {pr}</p>{/each}
            <div class="botoes">{#if !semMudanca}<Botao variante="cheio" disabled={ocupado} onclick={() => aceitaProposta(l, it)}>Aceitar</Botao>{/if}
              <Botao variante="texto" onclick={() => (fora = [...fora, l.i])}>Descartar</Botao></div>
          </div>
        {/if}
      {/if}
    {/each}
    {#if buscando && !mostradas.length}<p class="rotulo">Nada encontrado neste livro.</p>{/if}
  </article>
{/if}

<style>
  .alterna { all: unset; cursor: pointer; font-family: var(--mono); font-size: var(--t-rotulo); text-transform: uppercase; letter-spacing: 0.22em; color: var(--apagado); border-bottom: 1px solid var(--linha-forte); }
  .alterna:hover { color: var(--papel); border-color: var(--acento); } .alterna:focus-visible { outline: 1px solid var(--acento); outline-offset: 3px; }
  .historico { list-style: none; margin: 0; padding: var(--e4) 0; border-bottom: 1px solid var(--linha); display: grid; gap: var(--e2); max-height: 16rem; overflow: auto; color: var(--apagado); }
  .estado { padding: var(--e6) 0; }
  .ferramentas { display: flex; flex-wrap: wrap; gap: var(--e3) var(--e6); align-items: center; }
  .busca { flex: 0 1 22rem; }
  mark { background: color-mix(in srgb, var(--acento) 38%, transparent); color: inherit; border-radius: 2px; }
  article { padding: var(--e8) 0 var(--e24); max-width: 68ch; }
  .par { margin-bottom: 1em; white-space: pre-line; cursor: text; border-left: 1px solid transparent; padding-left: var(--e4); margin-left: calc(var(--e4) * -1); transition: border-color var(--rapido); }
  .par:hover, .par:focus-visible { border-left-color: var(--acento); outline: none; }
  .par.marcada { border-left-color: var(--acento); background: color-mix(in srgb, var(--acento) 10%, transparent); }
  .lote { display: flex; flex-wrap: wrap; gap: var(--e4); align-items: center; padding: var(--e4) 0; border-bottom: 1px solid var(--linha); }
  .proposta { display: grid; gap: var(--e2); margin: 0 0 var(--e6); padding-left: var(--e4); border-left: 1px solid var(--ok); }
  .citacao { color: var(--apagado); font-style: italic; padding-left: var(--e8); }
  .titulo { cursor: text; margin: 2em 0 0.8em; line-height: 1.1; }
  .titulo.n1 { font-size: var(--t-h2); } .titulo.n2 { font-size: var(--t-h3); } .titulo.n3 { font-size: 1.15rem; letter-spacing: 0.08em; }
  .titulo:focus-visible { outline: 1px solid var(--acento); outline-offset: 4px; }
  .edicao { display: grid; gap: var(--e3); margin: var(--e4) 0 var(--e6); }
  textarea { width: 100%; max-width: none; resize: vertical; background: transparent; border: 0; border-left: 1px solid var(--acento); padding: 0 0 0 var(--e4); }
  .botoes { display: flex; flex-wrap: wrap; gap: var(--e4); align-items: center; }
  .botoes input { flex: 1 1 12rem; }
</style>
