<script>
  import { onMount } from 'svelte'
  import Chip from '../lib/Chip.svelte'
  import Botao from '../lib/Botao.svelte'
  import { api } from '../lib/api.js'
  import { semAcento } from '../lib/realce.js'

  let { rede = null } = $props()      // o que está ligado em Configurações → Rede

  let livros = $state(null)   // null = carregando
  let erro = $state('')
  let filtro = $state('')     // achar um livro da estante por título ou autor
  let visiveis = $derived((livros ?? []).filter((l) => !filtro.trim() || semAcento(l.titulo + ' ' + l.autor).includes(semAcento(filtro.trim()))))

  // acervos abertos: buscar um livro e baixá-lo para a pasta (só com a chave de rede ligada)
  let dlgAcervos = $state()
  let termo = $state('')
  let achados = $state(null)     // null = ainda não buscou
  let semResposta = $state([])
  let buscando = $state(false)
  let erroAcervo = $state('')
  let baixado = $state('')
  async function buscaAcervos(e) {
    e.preventDefault()
    if (termo.trim().length < 3) return
    buscando = true; erroAcervo = ''; baixado = ''
    try { const r = await api('/api/rede/acervos?q=' + encodeURIComponent(termo.trim())); achados = r.achados; semResposta = r.sem_resposta }
    catch (ex) { erroAcervo = ex.message } finally { buscando = false }
  }
  async function verArquivos(a) {
    a.carregando = true; erroAcervo = ''
    try { a.arquivos = await api('/api/rede/arquivos?id=' + encodeURIComponent(a.id)) } catch (ex) { erroAcervo = ex.message } finally { a.carregando = false }
  }
  async function baixa(a, arq) {
    arq.baixando = true; erroAcervo = ''; baixado = ''
    try { const r = await api('/api/rede/baixar', 'POST', { url: arq.url, titulo: a.titulo, autor: a.autor.split(',')[0] }); baixado = r.arquivo; soltos = await api('/api/soltos') }
    catch (ex) { erroAcervo = ex.message } finally { arq.baixando = false }
  }
  const tam = (kb) => (kb == null ? '' : kb > 1024 ? ` · ${(kb / 1024).toFixed(1)} MB` : ` · ${kb} KB`)

  // importar livro novo
  let dlg = $state()
  let novo = $state({ titulo: '', autor: '', idioma: 'en', tipo: 'traducao' })
  let arquivos = $state()
  let enviando = $state(false)
  let erroNovo = $state('')
  let soltos = $state([])       // arquivos largados em livros/, ainda não importados
  let solto = $state(null)      // o arquivo solto que está sendo importado

  let sugerido = $state(null)   // o que o app leu do arquivo: título, autor, idioma, ação recomendada
  // o servidor lê o arquivo (dados internos, amostra do texto, nome) e sugere; o usuário pode trocar tudo
  async function sugere(nome, corpo) {
    sugerido = null
    try {
      const r = await fetch('/api/palpite?' + new URLSearchParams({ arquivo: nome }), { method: 'POST', body: corpo })
      if (!r.ok) return
      const p = await r.json()
      sugerido = p
      novo = { titulo: p.titulo || novo.titulo, autor: p.autor || novo.autor, idioma: p.idioma || novo.idioma, tipo: p.tipo || novo.tipo }
    } catch { /* sem sugestão: o formulário continua manual */ }
  }
  function abreSolto(nome) {
    novo = { titulo: '', autor: '', idioma: 'en', tipo: 'traducao' }
    solto = nome; erroNovo = ''; dlg.showModal(); sugere(nome)
  }
  $effect(() => { const a = arquivos?.[0]; if (a && !solto) sugere(a.name, a) })
  async function importar(e) {
    e.preventDefault()
    const pdf = arquivos?.[0]
    if (!pdf && !solto) { erroNovo = 'Escolha o arquivo do livro.'; return }
    enviando = true; erroNovo = ''
    try {
      const q = new URLSearchParams({ ...novo, arquivo: solto ?? pdf.name })
      const r = solto ? await fetch('/api/importar-solto?' + q, { method: 'POST' }) : await fetch('/api/importar?' + q, { method: 'POST', body: pdf })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || r.statusText)
      dlg.close(); location.hash = 'livro/' + j.id
    } catch (ex) { erroNovo = ex.message } finally { enviando = false }
  }

  onMount(async () => {
    try {
      const r = await fetch('/api/livros')
      if (!r.ok) throw new Error(r.statusText)
      livros = await r.json()
      soltos = await fetch('/api/soltos').then((x) => (x.ok ? x.json() : []))
    } catch (e) {
      erro = 'Não foi possível falar com o servidor local.'
      livros = []
    }
  })
</script>

<header class="topo">
  <div class="rotulo">Biblioteca · {livros ? String(livros.length).padStart(2, '0') : '—'} {livros?.length === 1 ? 'obra' : 'obras'}</div>
  <h1><span>Seu</span><span class="recuo">acervo</span></h1>
  <div class="acoes">
    <Botao variante="cheio" onclick={() => { solto = null; sugerido = null; dlg.showModal() }}>Novo livro</Botao>
    <Botao onclick={() => dlgAcervos.showModal()}>Buscar em acervos abertos</Botao>
    <Botao onclick={() => (location.hash = 'fila')}>Fila de livros</Botao>
    {#if (livros?.length ?? 0) > 1}<input class="filtro" type="search" bind:value={filtro} placeholder="Achar na estante: título ou autor" aria-label="Achar um livro da estante" />{/if}
  </div>
</header>

<dialog bind:this={dlgAcervos} class="largo" aria-labelledby="t-acervos">
  <div class="rotulo">Acervos abertos · Internet Archive e Project Gutenberg</div>
  <h3 id="t-acervos">Buscar um livro</h3>
  {#if !rede?.edicoes}
    <p class="leitura">Esta busca usa a internet e vem desligada. Ligada, sai do seu computador só o que você digitar aqui e o pedido do arquivo que escolher.</p>
    <div class="botoes"><Botao variante="texto" onclick={() => dlgAcervos.close()}>Fechar</Botao><a class="elo" href="#config/rede" onclick={() => dlgAcervos.close()}>Ligar em Configurações → Rede →</a></div>
  {:else}
    <form class="linha-busca" onsubmit={buscaAcervos}>
      <input type="search" bind:value={termo} placeholder="título ou autor" aria-label="Título ou autor" />
      <Botao variante="cheio" disabled={buscando || termo.trim().length < 3}>{buscando ? 'Buscando…' : 'Buscar'}</Botao>
    </form>
    <p class="rotulo">Só livros com arquivo aberto (EPUB ou PDF). O arquivo vai para a sua pasta de livros e aparece para importar.</p>
    {#if erroAcervo}<Chip estado="erro">{erroAcervo}</Chip>{/if}
    {#if baixado}<Chip estado="ok">Baixado: {baixado} · já está na lista para importar</Chip>{/if}
    {#if achados}
      <ul class="achados">
        {#each achados as a}
          <li>
            <div class="info"><a class="at" href={a.link} target="_blank" rel="noreferrer">{a.titulo}</a>
              <span class="rotulo">{[a.autor, a.ano, a.idioma, a.acervo].filter(Boolean).join(' · ')}</span></div>
            <div class="arqs">
              {#if a.arquivos === null}<Botao variante="texto" disabled={a.carregando} onclick={() => verArquivos(a)}>{a.carregando ? 'Vendo…' : 'Ver arquivos'}</Botao>
              {:else}{#each a.arquivos as arq}<Botao disabled={arq.baixando} onclick={() => baixa(a, arq)}>{arq.baixando ? 'Baixando…' : `Baixar ${arq.formato}${tam(arq.kb)}`}</Botao>{:else}<span class="rotulo">sem arquivo aberto</span>{/each}{/if}
            </div>
          </li>
        {:else}<li class="rotulo">Nada encontrado com arquivo aberto.</li>{/each}
      </ul>
      {#if semResposta.length}<p class="rotulo">Sem resposta agora: {semResposta.join(', ')}</p>{/if}
    {/if}
    <div class="botoes"><Botao variante="texto" onclick={() => dlgAcervos.close()}>Fechar</Botao></div>
  {/if}
</dialog>

<dialog bind:this={dlg} aria-labelledby="t-novo">
  <form onsubmit={importar}>
    <div class="rotulo">Importar · fica só neste computador</div>
    <h3 id="t-novo">Novo livro</h3>
    {#if solto}
      <p class="rotulo">Arquivo · {solto}</p>
    {:else}
      <label><span class="rotulo">Arquivo · PDF, EPUB, MOBI, AZW3, DOCX, ODT, RTF, FB2, HTML, TXT</span><input type="file" accept=".pdf,.epub,.mobi,.azw,.azw3,.docx,.odt,.rtf,.fb2,.html,.htm,.txt,.md" bind:files={arquivos} required /></label>
    {/if}
    {#if sugerido}<p class="rotulo">Preenchido pelo app a partir do arquivo{sugerido.outro_idioma ? ` · o texto parece estar em outro idioma (${sugerido.outro_idioma}), que o app ainda não traduz: dá para extrair e converter` : sugerido.leu_texto ? '' : ' (não deu para ler o texto: confira o idioma)'} · confira e troque o que quiser</p>{/if}
    <label><span class="rotulo">Título</span><input bind:value={novo.titulo} required /></label>
    <label><span class="rotulo">Autor</span><input bind:value={novo.autor} required /></label>
    <div class="dupla">
      <label><span class="rotulo">Idioma da fonte{sugerido?.idioma ? ' · detectado' : ''}</span>
        <select bind:value={novo.idioma}><option value="en">Inglês</option><option value="de">Alemão</option><option value="pt">Português</option></select></label>
      <label><span class="rotulo">O que fazer</span>
        <select bind:value={novo.tipo}><option value="traducao">Traduzir para PT-BR{sugerido?.tipo === 'traducao' ? ' · recomendado' : ''}</option><option value="atualizacao">Atualizar português antigo{sugerido?.tipo === 'atualizacao' ? ' · recomendado' : ''}</option><option value="nativo">Só extrair o texto{sugerido?.tipo === 'nativo' ? ' · recomendado' : ''}</option></select></label>
    </div>
    {#if erroNovo}<Chip estado="erro">{erroNovo}</Chip>{/if}
    <div class="botoes"><Botao variante="texto" onclick={(e) => { e.preventDefault(); dlg.close() }}>Cancelar</Botao><Botao variante="cheio" disabled={enviando}>{enviando ? 'Importando…' : 'Importar'}</Botao></div>
  </form>
</dialog>

{#if soltos.length}
  <details class="soltos" open={!!baixado}>
    <summary class="rotulo">{soltos.length} {soltos.length === 1 ? 'arquivo' : 'arquivos'} na pasta, ainda não {soltos.length === 1 ? 'importado' : 'importados'}</summary>
    <ul>{#each soltos as s}<li><span class="nome">{s.arquivo}</span><span class="rotulo">{s.kb > 1024 ? (s.kb / 1024).toFixed(1) + ' MB' : s.kb + ' KB'}</span>
      <Botao variante="texto" onclick={() => abreSolto(s.arquivo)}>Importar →</Botao></li>{/each}</ul>
  </details>
{/if}

{#if livros === null}
  <ul class="estante" aria-busy="true">{#each [0, 1, 2] as _}<li class="esqueleto"></li>{/each}</ul>
{:else if erro}
  <div class="vazio"><Chip estado="erro">{erro}</Chip><p class="rotulo">Abra o aplicativo de novo pelo atalho.</p></div>
{:else if livros.length === 0}
  <div class="vazio"><p class="leitura">Nenhum livro ainda.</p><p class="rotulo">Comece importando um PDF.</p><Botao variante="cheio" onclick={() => dlg.showModal()}>Novo livro</Botao></div>
{:else}
  <ul class="estante">
    {#each visiveis as l, i (l.id)}
      {@const r = l.rascunho}
      <li style:animation-delay="{i * 70}ms">
        <a class="livro" href="#livro/{l.id}">
          <span class="capa" class:sem={!l.capa}>
            {#if l.capa}<img src="/api/livro/{l.id}/capa" alt="" loading="lazy" />
            {:else}<span class="lombada" aria-hidden="true"></span><span class="t">{l.titulo}</span><span class="a">{l.autor}</span>{/if}
            {#if l.processando}<span class="selo agora">Processando</span>
            {:else if l.pausado}<span class="selo">Pausado</span>
            {:else if r && r.aceitos < r.total}<span class="selo revisar">{r.total - r.aceitos} para revisar</span>{/if}
          </span>
          <!-- a barra ocupa o lugar mesmo sem rascunho, para os títulos ficarem todos na mesma linha -->
          <span class="barra" style:visibility={r ? null : 'hidden'} title={r ? `${r.aceitos} de ${r.total} blocos aceitos` : null}><span style:width="{r ? Math.round(100 * r.aceitos / Math.max(1, r.total)) : 0}%"></span></span>
          <span class="titulo">{l.titulo}</span>
          <span class="autor">{l.autor}</span>
          <span class="rotulo meta">{l.paragrafos} {l.paragrafos === 1 ? 'bloco' : 'blocos'} no livro{l.pdf ? ' · PDF' : ''}{l.epub ? ' · EPUB' : ''}</span>
        </a>
      </li>
    {/each}
  </ul>
{/if}

<style>
  .topo { padding-bottom: var(--e12); border-bottom: 1px solid var(--linha); margin-bottom: var(--e2); }
  h1 { margin-top: var(--e6); display: grid; }
  h1 span { display: block; animation: entra var(--lento) var(--curva) both; }
  h1 .recuo { padding-left: 14%; font-style: italic; animation-delay: 90ms; }
  @keyframes entra { from { opacity: 0; transform: translateY(0.35em); } }

  .acoes { margin-top: var(--e8); display: flex; flex-wrap: wrap; gap: var(--e3) var(--e4); align-items: center; }
  .filtro { flex: 1 1 14rem; max-width: 24rem; width: auto; }
  dialog.largo { width: min(46rem, calc(100vw - 2rem)); max-height: calc(100vh - 2rem); }
  dialog.largo[open] { display: grid; gap: var(--e4); align-content: start; }
  .linha-busca { display: flex; gap: var(--e3); } .linha-busca input { flex: 1; }
  .achados { list-style: none; margin: 0; padding: 0; max-height: 46vh; overflow: auto; }
  .achados li { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--e3) var(--e6); align-items: center; padding: var(--e3) 0; border-top: 1px solid var(--linha); border-bottom: 0; animation: none; }
  .achados .info { display: grid; gap: var(--e1); min-width: 0; } .at { text-decoration: none; overflow-wrap: anywhere; } .at:hover { color: var(--acento); }
  .arqs { display: flex; flex-wrap: wrap; gap: var(--e2); justify-content: flex-end; }
  @media (max-width: 640px) { .achados li { grid-template-columns: 1fr; } .arqs { justify-content: flex-start; } }
  /* recolhido: quem pôs o arquivo na pasta sabe que ele está lá; abre sozinho só depois de um download pelos acervos */
  .soltos { padding: var(--e3) 0; border-bottom: 1px solid var(--linha); animation: none; }
  .soltos summary { cursor: pointer; } .soltos summary:hover { color: var(--papel); }
  .soltos[open] ul { padding-top: var(--e3); }
  .soltos ul { list-style: none; margin: 0; padding: 0; }
  .soltos li { display: flex; flex-wrap: wrap; gap: var(--e2) var(--e6); align-items: baseline; justify-content: space-between; padding: var(--e2) 0; border: 0; animation: none; }
  .soltos .nome { font-family: var(--mono); font-size: 0.875rem; overflow-wrap: anywhere; flex: 1 1 16rem; }
  dialog { background: var(--superficie); color: var(--papel); border: 1px solid var(--linha-forte); border-radius: var(--raio); padding: var(--e8); width: min(34rem, calc(100vw - 2rem)); }
  dialog::backdrop { background: rgb(0 0 0 / 0.7); backdrop-filter: blur(3px); }
  dialog[open] { animation: entra var(--medio) var(--curva) both; }
  form { display: grid; gap: var(--e4); }
  form h3 { margin-bottom: var(--e2); }
  label { display: grid; gap: var(--e2); }
  .dupla { display: grid; grid-template-columns: 1fr 1fr; gap: var(--e4); align-items: end; }
  input, select { font: inherit; color: var(--papel); background: var(--fundo); border: 1px solid var(--linha-forte); border-radius: var(--raio); padding: var(--e2) var(--e3); min-width: 0; width: 100%; }
  input:focus-visible, select:focus-visible { outline: none; border-color: var(--acento); }
  .botoes { display: flex; justify-content: flex-end; gap: var(--e6); margin-top: var(--e4); }

  /* estante de capas, como numa biblioteca de leitor: a capa é o livro; quem não tem capa ganha uma tipográfica */
  .estante { list-style: none; margin: 0; padding: var(--e8) 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr)); gap: var(--e12) var(--e8); }
  .estante li { border: 0; animation: entra var(--lento) var(--curva) both; }
  .livro { display: grid; gap: var(--e2); text-decoration: none; align-content: start; }
  .capa { position: relative; display: block; aspect-ratio: 2 / 3; overflow: hidden; background: var(--superficie); border: 1px solid var(--linha); margin-bottom: var(--e2);
          box-shadow: 0 1.4rem 2.6rem -1.4rem rgb(0 0 0 / 0.9); transition: transform var(--medio) var(--curva), box-shadow var(--medio) var(--curva), border-color var(--medio) var(--curva); }
  .capa img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .livro:hover .capa, .livro:focus-visible .capa { transform: translateY(-0.4rem); border-color: var(--acento); box-shadow: 0 2.2rem 3rem -1.4rem rgb(0 0 0 / 0.95), 0 0 0 1px var(--acento); }
  .capa.sem { display: grid; align-content: space-between; padding: var(--e6) var(--e4) var(--e4) var(--e6);
              background: linear-gradient(160deg, color-mix(in srgb, var(--acento) 16%, var(--superficie)), var(--fundo) 70%); }
  .capa.sem .lombada { position: absolute; left: 0; top: 0; bottom: 0; width: 0.5rem; background: var(--acento); opacity: 0.75; }
  .capa.sem .t { font-family: var(--display); text-transform: var(--caixa-titulos); font-size: 1.15rem; line-height: 1.05; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 6; line-clamp: 6; -webkit-box-orient: vertical; overflow: hidden; }
  .capa.sem .a { font-family: var(--leitura); font-style: italic; color: var(--apagado); font-size: 0.9rem; }
  .selo { position: absolute; left: 0; bottom: var(--e3); padding: var(--e1) var(--e3); background: var(--fundo); border: 1px solid var(--linha-forte); border-left: 0;
          font-family: var(--mono); font-size: 0.6875rem; text-transform: uppercase; letter-spacing: 0.14em; color: var(--papel); }
  .selo.revisar, .selo.agora { color: var(--revisar); border-color: var(--revisar); }
  .barra { display: block; height: 2px; background: var(--linha); } .barra span { display: block; height: 100%; background: var(--ok); }
  .titulo { font-family: var(--display); font-size: 1.05rem; text-transform: var(--caixa-titulos); line-height: 1.15; overflow-wrap: anywhere; }
  .autor { font-family: var(--leitura); font-style: italic; color: var(--apagado); font-size: 0.95rem; }
  .meta { margin-top: var(--e1); }

  .esqueleto { aspect-ratio: 2 / 3; background: linear-gradient(90deg, transparent, var(--superficie), transparent); background-size: 200% 100%; animation: brilho 1.4s linear infinite; }
  @keyframes brilho { to { background-position: -200% 0; } }
  .vazio { display: grid; gap: var(--e4); justify-items: start; padding: var(--e16) 0; }

  @media (max-width: 520px) { .estante { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--e8) var(--e4); } }
  @media (prefers-reduced-motion: reduce) { .capa { transition: none; } .livro:hover .capa { transform: none; } }
</style>
