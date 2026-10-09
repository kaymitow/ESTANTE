<script>
  import Chip from '../lib/Chip.svelte'
  import Botao from '../lib/Botao.svelte'
  import Progresso from '../lib/Progresso.svelte'
  import { api } from '../lib/api.js'

  let d = $state(null)          // resposta de /api/catalogo; null = carregando
  let erro = $state('')
  let papeis = $state({})
  let outro = $state('')
  let proprio = $state({ nome: '', caminho: '' })
  let ocupado = $state(false)
  let todos = $state(false)     // mostrar também os modelos que não cabem na placa ou não foram medidos

  // os três que trabalham numa tradução ficam à vista; os de scan e português antigo, recolhidos
  const PAPEIS = [
    { id: 'tradutor', nome: 'Tradutor', o: 'Escreve a tradução de cada bloco.' },
    { id: 'auditor', nome: 'Auditor', o: 'Confere a tradução contra o original e aponta o que não bate.' },
    { id: 'juiz', nome: 'Juiz', o: 'Decide as disputas entre os dois. Só entra nos blocos em disputa.' },
    { id: 'geral', nome: 'Português antigo', o: 'Atualiza a grafia de textos antigos e limpa a leitura de scan.', extra: true },
    { id: 'leitor', nome: 'Leitor de páginas', o: 'Lê a imagem da página escaneada.', extra: true },
    { id: 'votante', nome: 'Votante do juiz', o: 'Vota nas disputas no lugar do juiz, que fica só com a correção. Em "automático" o próprio juiz vota.', extra: true },
    { id: 'leitor2', nome: 'Segundo leitor', o: 'Lê a mesma página sem ver a primeira leitura, para conferir.', extra: true },
  ]
  const FAZ = { tradutor: 'traduz', auditor: 'audita', juiz: 'julga', geral: 'português antigo', leitor: 'lê páginas', leitor2: 'confere páginas', votante: 'vota nas disputas' }

  async function carrega(primeira = false) {
    try { d = await api('/api/catalogo'); if (primeira) papeis = { ...d.papeis }; if (primeira || !erro) erro = d.erro }
    catch (e) { erro = 'Não foi possível falar com o servidor local.'; d = d ?? { catalogo: [], instalados: [], em_uso: {}, baixando: {} } }
  }
  async function faz(f) { ocupado = true; erro = ''; try { await f(); await carrega() } catch (e) { erro = e.message } finally { ocupado = false } }

  const baixa = (nome) => faz(() => api('/api/modelos/baixar', 'POST', { nome }))
  const remove = (nome) => { if (confirm(`Apagar ${nome} do computador?`)) faz(() => api('/api/modelos/remover', 'POST', { nome })) }
  const escolhe = (id, valor) => { papeis[id] = valor || undefined; faz(() => api('/api/modelos/papeis', 'PUT', { papeis })) }      // vale na hora, sem botão de guardar
  let aviso = $state('')        // o que o teste de um modelo recém-registrado mostrou
  const traz = () => faz(async () => { aviso = ''; aviso = (await api('/api/modelos/proprio', 'POST', proprio)).aviso ?? ''; proprio = { nome: '', caminho: '' } })

  let ativos = $derived(d ? Object.entries(d.baixando).filter(([, b]) => !['pronto', 'erro'].includes(b.estado)) : [])
  $effect(() => {
    carrega(true)
    const t = setInterval(() => { if (ativos.length && !document.hidden) carrega() }, 1500)
    return () => clearInterval(t)
  })
  const gb = (b) => (b / 1e9).toFixed(1)
  // Cada caixa mostra primeiro os modelos medidos naquele papel (na ordem do catálogo: o primeiro é o recomendado), depois os outros instalados.
  // Modelo feito para uma coisa só (o tradutor dedicado, o leitor de páginas) não aparece nos papéis que ele não faz.
  const SO_UM = ['tradutor', 'leitor2', 'votante']
  const curto = (nome) => nome?.replace(/^hf\.co\/[^/]+\//, '')
  function opcoes(id) {
    const tem = new Set(d.instalados.map((m) => m.nome))
    const testados = d.catalogo.filter((c) => tem.has(c.nome) && c.papeis.includes(id) && c.medido)
    const dedicado = (c) => c.papeis.length === 1 && SO_UM.includes(c.papeis[0])
    const outros = d.instalados.filter((m) => !testados.some((c) => c.nome === m.nome) && !d.catalogo.some((c) => c.nome === m.nome && dedicado(c) && !c.papeis.includes(id))
      && !(id.startsWith('leitor') && d.catalogo.some((c) => c.nome === m.nome && !c.papeis.some((x) => x.startsWith('leitor')))))
    return { testados, outros }
  }
  const nota = (id) => d.catalogo.find((c) => c.nome === (papeis[id] || d.em_uso[id]))?.nota ?? (papeis[id] && papeis[id] !== 'fora' ? 'Ainda não medido neste papel.' : '')
  let ehArquivo = $derived(/\.gguf$/i.test(outro.trim()) || /^[a-z]:[\\/]|^[\\/~]/i.test(outro.trim()))
  function preenche() {      // "C:\modelos\Meu Modelo.Q4_K_M.gguf" -> "meu-modelo-q4-k-m"
    proprio.caminho = outro.trim()
    if (ehArquivo) proprio.nome = outro.trim().split(/[\\/]/).pop().replace(/\.gguf$/i, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  }
  const usos = (nome) => PAPEIS.filter((p) => (papeis[p.id] || d.em_uso[p.id]) === nome).map((p) => p.nome)
  // catálogo + o que está instalado e não está nele (modelos que o usuário trouxe)
  let lista = $derived(d ? [...d.catalogo, ...d.instalados.filter((m) => !d.catalogo.some((c) => c.nome === m.nome)).map((m) => ({ ...m, instalado: true, seu: true, papeis: [] }))] : [])
  let visiveis = $derived(lista.filter((m) => todos || m.instalado || (m.cabe !== false && m.medido) || d.baixando[m.nome]))
</script>

<header class="topo-tela">
  <div class="rotulo">Modelos · rodam no seu computador{d?.placa ? ` · ${d.placa.nome} · ${d.placa.gb} GB` : ''}</div>
  <h2>Modelos de IA</h2>
  <p class="sub">Você escolhe quem faz cada trabalho e quais modelos ficam no computador. Nada é baixado sem o seu clique.</p>
</header>

{#if d === null}
  <Progresso rotulo="Abrindo" />
{:else}
  {#if erro}<p class="erro" role="alert"><Chip estado="erro">{erro}</Chip></p>{/if}

  <section>
    <div class="titulo-secao"><h3>Quem faz o quê</h3><p class="o">Em "automático" o app usa o melhor entre os instalados. Auditor e juiz funcionam melhor quando são modelos diferentes do tradutor.</p></div>
    {#snippet papel(p, i)}
      <label class="papel">
        <span class="num rotulo">{String(i + 1).padStart(2, '0')}</span>
        <span class="pn">{p.nome}</span>
        <span class="o">{p.o}</span>
        <select aria-label="Modelo para {p.nome}" value={papeis[p.id] ?? ''} disabled={ocupado} onchange={(e) => escolhe(p.id, e.currentTarget.value)}>
          <option value="">Automático · {curto(d.em_uso[p.id]) ?? '—'}</option>
          {#if opcoes(p.id).testados.length}<optgroup label="Testados para este papel">
            {#each opcoes(p.id).testados as m, k}<option value={m.nome}>{curto(m.nome)}{k === 0 ? ' · recomendado' : ''}</option>{/each}</optgroup>{/if}
          {#if opcoes(p.id).outros.length}<optgroup label="Outros instalados · não medidos neste papel">
            {#each opcoes(p.id).outros as m}<option value={m.nome}>{curto(m.nome)}</option>{/each}</optgroup>{/if}
          {#if d.fora && !p.id.startsWith('leitor')}<optgroup label="Pela internet"><option value="fora">modelo de fora · {d.fora}</option></optgroup>{/if}
        </select>
        {#if nota(p.id)}<span class="nota-papel">{nota(p.id)}</span>{/if}
      </label>
    {/snippet}
    <div class="papeis">{#each PAPEIS.filter((p) => !p.extra) as p, i}{@render papel(p, i)}{/each}</div>
    <details>
      <summary class="rotulo">Livros escaneados e português antigo</summary>
      <div class="papeis recuo">{#each PAPEIS.filter((p) => p.extra) as p, i}{@render papel(p, i + 3)}{/each}</div>
    </details>
  </section>

  {#snippet linha(m)}
    {@const b = d.baixando[m.nome]}
    {@const u = m.instalado ? usos(m.nome) : []}
    <li>
      <div class="quem"><span class="nome">{curto(m.nome)}</span><span class="rotulo">{m.gb} GB{m.licenca ? ` · ${m.licenca}` : ''}</span></div>
      <div class="oque">
        {#if m.papeis?.length}<span class="rotulo">{m.papeis.map((p) => FAZ[p]).join(' · ')}</span>{/if}
        <p class="o">{m.nota ?? (m.seu ? 'Modelo que você trouxe. Ainda não medido aqui.' : '')}</p>
      </div>
      <div class="estado">
        {#if u.length}<Chip estado="ok">Em uso · {u.join(', ')}</Chip>{:else if m.instalado}<Chip>Sem papel</Chip>
        {:else if m.cabe === true}<Chip estado="ok">Cabe na placa</Chip>{:else if m.cabe === false}<Chip estado="revisar">Maior que a placa</Chip>{/if}
        {#if m.medido === false}<Chip>Não medido aqui</Chip>{/if}
        {#if b?.estado === 'erro'}<Chip estado="erro">{b.erro}</Chip>{/if}
      </div>
      <div class="acao">
        {#if b && !['pronto', 'erro'].includes(b.estado)}<Progresso valor={b.total ? b.feito / b.total : null} rotulo={b.total ? `${gb(b.feito)} de ${gb(b.total)} GB` : b.estado} />
        {:else if m.instalado}<Botao variante="texto" disabled={ocupado} onclick={() => remove(m.nome)}>Apagar</Botao>
        {:else}<Botao disabled={ocupado} onclick={() => baixa(m.nome)}>Baixar</Botao>{/if}
      </div>
    </li>
  {/snippet}

  <section>
    <div class="titulo-secao"><h3>No computador</h3><p class="o">Os modelos instalados e o que cada um está fazendo.</p></div>
    <ul class="linhas">{#each lista.filter((m) => m.instalado) as m (m.nome)}{@render linha(m)}{:else}<li class="rotulo">Nenhum modelo instalado.</li>{/each}</ul>
  </section>

  <section>
    <div class="titulo-secao"><h3>Para baixar</h3>
      <p class="o">{todos ? 'Todo o catálogo.' : 'Os recomendados para a sua placa.'}
        <button class="alterna rotulo" onclick={() => (todos = !todos)}>{todos ? 'Só os recomendados' : 'Mostrar todos'}</button></p></div>
    <ul class="linhas">{#each visiveis.filter((m) => !m.instalado) as m (m.nome)}{@render linha(m)}{:else}<li class="rotulo">Tudo o que o app recomenda para esta placa já está instalado.</li>{/each}</ul>
    <form class="trazer" onsubmit={(e) => { e.preventDefault(); if (ehArquivo) traz() }}>
      <label><span class="rotulo">Trazer um modelo que você já tem</span>
        <input bind:value={outro} oninput={preenche} placeholder="arquivo do seu computador (C:\modelos\meu-modelo.gguf)" /></label>
      {#if ehArquivo}
        <label><span class="rotulo">Nome para ele no app · preenchido pelo arquivo, troque se quiser</span><input bind:value={proprio.nome} /></label>
        <span class="o">O arquivo fica onde está; o app só registra o caminho, faz uma pergunta de teste (pode levar um minuto) e ele aparece em "No computador".</span>
      {/if}
      <div><Botao disabled={ocupado || !ehArquivo || !proprio.nome.trim()}>{ocupado ? 'Registrando…' : 'Registrar o arquivo'}</Botao></div>
      {#if aviso}<Chip estado="revisar">{aviso}</Chip>{/if}
    </form>
  </section>


{/if}

<style>
  .erro { padding-top: var(--e4); }
  section { padding: var(--e8) 0; border-bottom: 1px solid var(--linha); display: grid; gap: var(--e6); }
  .titulo-secao { display: grid; gap: var(--e2); }
  .o { color: var(--apagado); max-width: 70ch; }
  .papeis { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr)); gap: var(--e4); }
  .papeis.recuo { padding-top: var(--e4); }
  .papel { display: grid; gap: var(--e2); align-content: start; padding: var(--e6); border: 1px solid var(--linha); border-radius: var(--raio); background: color-mix(in srgb, var(--superficie) 55%, transparent);
           transition: border-color var(--medio) var(--curva); min-width: 0; }
  .papel:hover, .papel:focus-within { border-color: var(--acento); }
  .pn { font-family: var(--display); text-transform: var(--caixa-titulos); font-size: 1.35rem; line-height: 1.1; }
  .papel .o { font-size: 0.875rem; min-height: 2.6em; }
  select, input { width: 100%; }
  .nota-papel { font-size: 0.8125rem; color: var(--apagado); line-height: 1.45; }
  label { display: grid; gap: var(--e2); }
  summary { cursor: pointer; } summary:hover { color: var(--papel); }
  .alterna { all: unset; cursor: pointer; margin-left: var(--e3); border-bottom: 1px solid var(--linha-forte); font-family: var(--mono); font-size: var(--t-rotulo); text-transform: uppercase; letter-spacing: 0.22em; color: var(--apagado); }
  .alterna:hover { color: var(--papel); border-color: var(--acento); } .alterna:focus-visible { outline: 1px solid var(--acento); outline-offset: 3px; }

  .linhas { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--linha); }
  .linhas li { display: grid; grid-template-columns: minmax(11rem, 1.1fr) minmax(0, 2.4fr) minmax(9rem, 1fr) auto; gap: var(--e3) var(--e6); align-items: start;
               padding: var(--e4) 0; border-bottom: 1px solid var(--linha); }
  .quem { display: grid; gap: var(--e1, 4px); min-width: 0; }
  .nome { font-family: var(--mono); font-size: 0.9375rem; overflow-wrap: anywhere; }
  .oque { display: grid; gap: var(--e1, 4px); min-width: 0; } .oque p { margin: 0; font-size: 0.875rem; }
  .estado { display: flex; flex-wrap: wrap; gap: var(--e2); }
  .acao { justify-self: end; min-width: 6rem; text-align: right; }
  .trazer { display: grid; gap: var(--e3); padding-top: var(--e4); max-width: 56rem; }
  @media (max-width: 820px) { .linhas li { grid-template-columns: 1fr; } .acao { justify-self: start; text-align: left; } }
</style>
