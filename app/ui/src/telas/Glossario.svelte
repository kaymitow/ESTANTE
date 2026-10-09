<script>
  import Botao from '../lib/Botao.svelte'
  import Chip from '../lib/Chip.svelte'
  import Progresso from '../lib/Progresso.svelte'
  import { api } from '../lib/api.js'

  let { id } = $props()
  let linhas = $state(null)
  let erro = $state('')
  let aviso = $state('')
  let ocupado = $state(false)
  let sujo = $state(false)
  let apoio = $state(null)      // resultado da consulta de apoio (rede opcional)
  async function consulta(termo) {
    apoio = { termo, carregando: true }
    try { apoio = await api('/api/rede/consulta?termo=' + encodeURIComponent(termo)) } catch (e) { apoio = { termo, erro: e.message } }
  }

  $effect(() => { api(`/api/glossario/${id}`).then((l) => (linhas = l)).catch((e) => { erro = e.message; linhas = [] }) })
  // sugestões: nomes e termos que se repetem na fonte (achados sem modelo). O app não decide nada; você escolhe o que fixar
  const CHAVE = `estante.glossario.ignorados.${id}`
  let sugestoes = $state([])
  let ignorados = $state((() => { try { return JSON.parse(localStorage.getItem(CHAVE) ?? '[]') } catch { return [] } })())
  $effect(() => { api(`/api/glossario/${id}/sugestoes`).then((s) => (sugestoes = s)).catch(() => {}) })
  let propostas = $derived(sugestoes.filter((s) => !ignorados.includes(s.termo) && !(linhas ?? []).some((l) => l.fonte.trim().toLowerCase() === s.termo.toLowerCase())))
  const fixa = (termo, usar) => { linhas.push({ fonte: termo, usar, evitar: '', exceto: '', obs: '' }); sujo = true }
  const ignora = (termo) => { ignorados = [...ignorados, termo]; try { localStorage.setItem(CHAVE, JSON.stringify(ignorados)) } catch {} }
  const nova = () => { linhas.push({ fonte: '', usar: '', evitar: '', exceto: '', obs: '' }); sujo = true }
  const tira = (i) => { linhas.splice(i, 1); sujo = true }
  const COLS = ['fonte', 'usar', 'evitar', 'exceto', 'obs']
  function exporta() {
    const csv = COLS.join(';') + '\n' + linhas.map((l) => COLS.map((c) => (l[c] ?? '').replace(/[;\n]/g, ' ')).join(';')).join('\n') + '\n'
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); a.download = `glossario-${id}.csv`; a.click(); URL.revokeObjectURL(a.href)
  }
  // importar: termo novo entra; termo que você já decidiu de outro jeito fica como está (e é contado). Nada é guardado antes do seu "Guardar".
  async function importa(e) {
    const arq = e.currentTarget.files?.[0]; e.currentTarget.value = ''
    if (!arq) return
    const [cab, ...resto] = (await arq.text()).replace(/^﻿/, '').split(/\r?\n/).filter((l) => l.trim())
    const cols = cab.split(';').map((c) => c.trim())
    if (!cols.includes('fonte') || !cols.includes('usar')) { erro = 'Este arquivo não é um glossário do Estante (faltam as colunas "fonte" e "usar").'; return }
    let novos = 0, iguais = 0, conflitos = 0
    for (const l of resto.slice(0, 5000)) {
      const v = l.split(';'); const t = Object.fromEntries(COLS.map((c) => [c, (v[cols.indexOf(c)] ?? '').trim().slice(0, 300)]))
      const meu = linhas.find((x) => x.fonte.trim().toLowerCase() === t.fonte.toLowerCase())
      if (!t.fonte) continue
      if (!meu) { linhas.push(t); novos++ } else if (meu.usar.trim() === t.usar) iguais++; else conflitos++
    }
    sujo ||= novos > 0; erro = ''
    aviso = `${novos} termos novos, ${iguais} que você já tinha` + (conflitos ? `, ${conflitos} em conflito (ficou a sua decisão)` : '') + (novos ? '. Confira e clique em Guardar.' : '.')
  }
  async function salva() {
    ocupado = true; erro = ''; aviso = ''
    try { const r = await api(`/api/glossario/${id}`, 'PUT', { linhas }); aviso = `${r.termos} termos guardados`; sujo = false }
    catch (e) { erro = e.message } finally { ocupado = false }
  }
</script>

<header class="topo-tela">
  <a class="rotulo volta" href="#livro/{id}">← Livro</a>
  <h2>Glossário</h2>
  <p class="sub">Termos já decididos para este livro. Vão no pedido ao tradutor, e o app confere se cada um saiu como combinado.
    Em "usar", separe alternativas aceitas com | (a primeira é a preferida).</p>
</header>

{#if linhas === null}
  <Progresso rotulo="Abrindo" />
{:else}
  <div class="tabela" role="table" aria-label="Glossário">
    <div class="linha cab" role="row"><span class="rotulo">Na fonte</span><span class="rotulo">Usar</span><span class="rotulo">Evitar</span><span class="rotulo">Observação</span><span></span></div>
    {#each linhas as l, i}
      <div class="linha" role="row">
        <input bind:value={l.fonte} oninput={() => (sujo = true)} aria-label="Termo na fonte" placeholder="free will" />
        <input bind:value={l.usar} oninput={() => (sujo = true)} aria-label="Usar" placeholder="livre-arbítrio" />
        <input bind:value={l.evitar} oninput={() => (sujo = true)} aria-label="Evitar" />
        <input bind:value={l.obs} oninput={() => (sujo = true)} aria-label="Observação" />
        <span class="acoes"><button class="tira" title="Consultar dicionário e enciclopédia (usa a internet, se ligada em Configurações)" onclick={() => consulta(l.fonte)} disabled={!l.fonte.trim()} aria-label="Consultar o termo">?</button><button class="tira" onclick={() => tira(i)} aria-label="Remover termo">×</button></span>
      </div>
    {:else}
      <p class="rotulo vazio">Nenhum termo ainda.</p>
    {/each}
  </div>
  {#if apoio}
    <aside class="apoio" aria-live="polite">
      <div class="rotulo">Consulta de apoio · {apoio.termo}</div>
      {#if apoio.carregando}<Progresso rotulo="Consultando" />
      {:else if apoio.erro}<Chip estado="revisar">{apoio.erro}</Chip>
      {:else}
        {#each apoio.definicoes as d}<p>{d}</p>{/each}
        {#if apoio.resumo}<p class="resumo">{apoio.resumo}</p>{/if}
        {#if !apoio.definicoes.length && !apoio.resumo}<p class="rotulo">Nada encontrado.</p>{/if}
        <span class="rotulo">{apoio.fontes.filter(Boolean).join(' · ')}</span>
      {/if}
    </aside>
  {/if}
  <div class="botoes">
    <Botao onclick={nova}>Novo termo</Botao>
    <Botao variante="texto" disabled={!linhas?.length} onclick={exporta}>Exportar (.csv)</Botao>
    <label class="elo">Importar de um arquivo<input type="file" accept=".csv,text/csv" onchange={importa} hidden /></label>
    <Botao variante="cheio" disabled={ocupado || !sujo} onclick={salva}>{ocupado ? 'Guardando…' : 'Guardar'}</Botao>
    {#if aviso}<Chip estado="ok">{aviso}</Chip>{/if}
    {#if erro}<Chip estado="erro">{erro}</Chip>{/if}
    {#if sujo}<span class="rotulo">Há mudanças não guardadas</span>{/if}
  </div>
  {#if propostas.length}
    <details class="sugestoes" open={!linhas.length}>
      <summary class="rotulo">Sugestões · {propostas.length} nomes e termos que se repetem na fonte</summary>
      <p class="o">Achados pelas maiúsculas e pela repetição, sem modelo. Nome próprio costuma ficar igual; termo do autor merece uma tradução fixa.
        Nada entra no glossário sem você: "manter" e "traduzir" só põem a linha na tabela, e ela vale depois de Guardar.</p>
      <ul>
        {#each propostas as s (s.termo)}
          <li>
            <span class="termo">{s.termo}</span><span class="rotulo">{s.vezes} vezes</span>
            <span class="exemplo">…{s.exemplo}…</span>
            <span class="escolhas"><button class="elo" onclick={() => fixa(s.termo, s.termo)}>Manter igual</button><button class="elo" onclick={() => fixa(s.termo, '')}>Traduzir</button><button class="elo apagado" onclick={() => ignora(s.termo)}>Ignorar</button></span>
          </li>
        {/each}
      </ul>
    </details>
  {/if}
{/if}

<style>
  .tabela { padding: var(--e6) 0; display: grid; gap: var(--e2); }
  .linha { display: grid; grid-template-columns: 1.1fr 1.3fr 1.3fr 1.3fr 3.5rem; gap: var(--e2); align-items: center; }
  .acoes { display: flex; } .tira:disabled { opacity: 0.3; cursor: default; }
  .apoio { border-left: 2px solid var(--linha-forte); padding: var(--e3) var(--e4); margin-bottom: var(--e6); display: grid; gap: var(--e2); color: var(--apagado); max-width: 72ch; }
  .apoio .resumo { font-family: var(--leitura); }
  .cab { padding-bottom: var(--e2); border-bottom: 1px solid var(--linha); }
  .linha input { width: 100%; }
  .tira { all: unset; cursor: pointer; text-align: center; color: var(--apagado); font-size: 1.2rem; line-height: 1; padding: var(--e1); }
  .tira:hover { color: var(--acento); } .tira:focus-visible { outline: 1px solid var(--acento); }
  .vazio { padding: var(--e6) 0; }
  .botoes { display: flex; flex-wrap: wrap; gap: var(--e4) var(--e6); align-items: center; }
  .sugestoes { margin-top: var(--e8); padding-top: var(--e4); border-top: 1px solid var(--linha); }
  .sugestoes summary { cursor: pointer; } .sugestoes summary:hover { color: var(--papel); }
  .sugestoes .o { color: var(--apagado); max-width: 72ch; padding: var(--e3) 0; }
  .sugestoes ul { list-style: none; margin: 0; padding: 0; }
  .sugestoes li { display: grid; grid-template-columns: minmax(8rem, 14rem) 5rem minmax(0, 1fr) auto; gap: var(--e2) var(--e4); align-items: baseline; padding: var(--e2) 0; border-top: 1px solid var(--linha); }
  .termo { font-family: var(--leitura); overflow-wrap: anywhere; } .exemplo { color: var(--apagado); font-size: 0.875rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .escolhas { display: flex; gap: var(--e4); } .escolhas .elo { background: none; border-width: 0 0 1px; cursor: pointer; } .escolhas .apagado { color: var(--apagado); border-color: var(--linha-forte); }
  @media (max-width: 900px) { .sugestoes li { grid-template-columns: 1fr auto; } .exemplo { grid-column: 1 / -1; white-space: normal; } }
  @media (max-width: 900px) { .linha { grid-template-columns: 1fr 1fr 3.5rem; } .linha input:nth-of-type(3), .linha input:nth-of-type(4), .cab span:nth-child(3), .cab span:nth-child(4) { display: none; } }
</style>
