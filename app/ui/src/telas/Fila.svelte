<script>
  // Modo lote: a fila de livros. Um por vez, na ordem; erro num livro não trava os outros; nada é aceito sozinho.
  // Em cima, a fila e os horários; embaixo, o que pode entrar nela: livros da estante ainda não processados e arquivos novos.
  import Botao from '../lib/Botao.svelte'
  import Chip from '../lib/Chip.svelte'
  import { api } from '../lib/api.js'
  let fila = $state(null), livros = $state([]), erro = $state('')
  let comecar = $state(''), parar = $state('')
  const carrega = async () => { try { [fila, livros] = await Promise.all([api('/api/fila'), api('/api/livros')]); erro = '' } catch (e) { erro = e.message } }
  $effect(() => { carrega(); const t = setInterval(carrega, 4000); return () => clearInterval(t) })
  const faz = async (u, m = 'POST', c) => { try { fila = await api(u, m, c); erro = '' } catch (e) { erro = e.message } }

  const nome = (id) => livros.find((l) => l.id === id)?.titulo ?? id
  const ESTADO = { 'na fila': ['neutro', 'Na fila'], rodando: ['revisar', 'Rodando'], pronto: ['ok', 'Pronto'], parou: ['erro', 'Parou'], esperando: ['revisar', 'Esperando você'] }
  const ETAPA = { diagnostico: 'diagnóstico', inventario: 'inventário', extracao: 'lendo o arquivo', estrutura: 'estrutura', transformacao: 'modelos trabalhando', rascunho: 'montando o rascunho' }
  const tempo = (s) => (s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min` : s >= 60 ? `${Math.round(s / 60)} min` : `${Math.round(s)} s`)
  const hora = (t) => new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(new Date(t * 1000))
  let naFila = $derived(new Set((fila?.itens ?? []).filter((i) => i.estado !== 'pronto').map((i) => i.livro)))
  let esperam = $derived((fila?.itens ?? []).filter((i) => i.estado === 'na fila').length)
  // livros da estante que ainda não passaram pelos modelos
  let candidatos = $derived(livros.filter((l) => l.novo && !naFila.has(l.id)))
  let marcados = $state([])

  // importar vários arquivos de uma vez: o app dá um palpite para cada um e você confere antes
  let linhas = $state([]), importando = $state(false)
  const TIPOS = [['traducao', 'Traduzir'], ['atualizacao', 'Atualizar português antigo'], ['nativo', 'Só extrair']]
  // só arquivos de livro: vale para arquivos soltos e para uma pasta inteira (subpastas incluídas)
  const LIVRO = /\.(pdf|epub|mobi|azw|azw3|docx|odt|rtf|fb2|html|htm|txt)$/i
  async function escolhe(e) {
    const arqs = [...e.currentTarget.files].filter((a) => LIVRO.test(a.name)); e.currentTarget.value = ''
    for (const arq of arqs) {
      const l = { arq, nome: arq.name, titulo: '', autor: '', idioma: 'en', tipo: 'traducao', rapido: false, aviso: '', marcado: true, vendo: true }
      linhas = [...linhas, l]
      const k = linhas.length - 1
      try {
        const r = await fetch('/api/palpite?' + new URLSearchParams({ arquivo: arq.name }), { method: 'POST', body: arq })
        const p = await r.json()
        if (!r.ok) throw new Error(p.detail || 'não foi possível ler')
        const aviso = !p.leu_texto ? 'não deu para ler o texto (scan?): confira o idioma' : p.outro_idioma ? `idioma que o app ainda não traduz (${p.outro_idioma}): só extrai` : !p.autor ? 'sem autor: preencha' : ''
        linhas[k] = { ...linhas[k], titulo: p.titulo || '', autor: p.autor || '', idioma: p.idioma || 'en', tipo: p.tipo || 'traducao', aviso, marcado: !!(p.titulo && p.autor), vendo: false }
      } catch (ex) { linhas[k] = { ...linhas[k], aviso: ex.message, marcado: false, vendo: false } }
    }
  }
  async function importa() {
    importando = true
    const novos = [], configs = {}
    for (const [k, l] of linhas.entries()) {
      if (!l.marcado || l.feito) continue
      try {
        const r = await fetch('/api/importar?' + new URLSearchParams({ titulo: l.titulo, autor: l.autor, idioma: l.idioma, tipo: l.tipo, arquivo: l.nome }), { method: 'POST', body: l.arq })
        const j = await r.json()
        if (!r.ok) throw new Error(j.detail || 'não importou')
        novos.push(j.id); linhas[k] = { ...l, feito: true, aviso: '' }
        if (l.rapido && l.tipo === 'traducao') configs[j.id] = { tarefa: 'traduzir', rapido: true }
      } catch (ex) { linhas[k] = { ...l, aviso: ex.message, marcado: false } }
    }
    if (novos.length) await faz('/api/fila', 'POST', { livros: novos, configs })
    linhas = linhas.filter((l) => !l.feito); importando = false; await carrega()
  }
</script>

<header class="topo-tela">
  <a class="rotulo volta" href="#biblioteca">← Biblioteca</a>
  <h2>Fila de livros</h2>
  <p class="o">Processa um livro depois do outro, sem você por perto: de noite, por exemplo. Um por vez, na ordem. Se um livro der erro, a fila segue para o próximo. Nada é aceito sozinho: de manhã cada livro espera a sua revisão.</p>
</header>

{#if erro}<Chip estado="erro">{erro}</Chip>{/if}
{#if fila}
  <section class="bloco">
    <div class="comando">
      {#if fila.ligada}
        <Chip estado="revisar">{fila.inicio_em && fila.inicio_em * 1000 > Date.now() ? `Começa às ${hora(fila.inicio_em)}` : 'Fila ligada'}{fila.fim_em ? ` · para às ${hora(fila.fim_em)}` : ''}</Chip>
        <Botao onclick={() => faz('/api/fila/desligar')}>Parar depois deste livro</Botao>
      {:else}
        <label><span class="rotulo">Começar às (vazio = agora)</span><input type="time" bind:value={comecar} /></label>
        <label><span class="rotulo">Parar às (vazio = até acabar)</span><input type="time" bind:value={parar} /></label>
        <Botao variante="cheio" disabled={!fila.itens.some((i) => ['na fila', 'parou', 'esperando'].includes(i.estado))} onclick={() => faz('/api/fila/ligar', 'POST', { comecar: comecar || null, parar: parar || null })}>{comecar ? 'Agendar a fila' : 'Começar a fila'}</Botao>
      {/if}
      {#if fila.itens.some((i) => i.estado === 'pronto')}<button class="elo" onclick={() => faz('/api/fila/limpar')}>Tirar os prontos</button>{/if}
    </div>
    {#if fila.aviso}<p class="o" aria-live="polite">{fila.aviso}</p>{/if}
    {#if fila.outro_rodando?.length}<p class="o">Há um livro sendo processado fora da fila ({fila.outro_rodando.map(nome).join(', ')}). A fila espera ele terminar.</p>{/if}

    {#if fila.itens.length}
      <ol class="fila">
        {#each fila.itens as i, k (i.livro)}
          <li>
            <span class="rotulo n">{String(k + 1).padStart(2, '0')}</span>
            <div class="quem"><a class="t" href="#livro/{i.livro}">{nome(i.livro)}</a>
              {#if i.estado === 'rodando'}<span class="rotulo">{ETAPA[i.etapa] ?? i.etapa ?? ''}{i.progresso ? ` · ${Math.round(100 * i.progresso)}%` : ''}{i.segundos ? ` · ${tempo(i.segundos)} de trabalho` : ''}</span>
              {:else if i.estado === 'pronto' && i.rascunho}<span class="rotulo">{i.rascunho.total} blocos · {i.rascunho.revisar} pedem atenção · {i.rascunho.juiz} do juiz{i.segundos ? ` · ${tempo(i.segundos)}` : ''}</span>
              {:else if i.estado === 'na fila'}<span class="rotulo">{i.config?.rapido ? 'Rascunho rápido · ' : ''}{i.estimativa ? `cerca de ${tempo(i.estimativa)} (estimativa)` : 'sem estimativa: falta um livro rodado neste modo para medir o ritmo'}</span>
              {:else if i.motivo}<span class="motivo">{i.motivo}</span>{/if}</div>
            <Chip estado={ESTADO[i.estado]?.[0]}>{ESTADO[i.estado]?.[1] ?? i.estado}</Chip>
            <span class="acoes">
              {#if i.estado === 'na fila'}
                <button class="seta" onclick={() => faz(`/api/fila/${i.livro}/mover?para=-1`)} aria-label="Subir {nome(i.livro)}">↑</button>
                <button class="seta" onclick={() => faz(`/api/fila/${i.livro}/mover?para=1`)} aria-label="Descer {nome(i.livro)}">↓</button>
              {/if}
              {#if i.estado === 'pronto'}<a class="elo" href="#revisao/{i.livro}">Revisar →</a>
              {:else if i.estado === 'esperando' || i.estado === 'rodando'}<a class="elo" href="#livro/{i.livro}">Ver →</a>{/if}
              {#if i.estado !== 'rodando'}<button class="seta" onclick={() => faz(`/api/fila/${i.livro}`, 'DELETE')} aria-label="Tirar {nome(i.livro)} da fila">✕</button>{/if}
            </span>
          </li>
        {/each}
      </ol>
      {#if !fila.ligada && fila.itens.some((i) => ['parou', 'esperando'].includes(i.estado))}<p class="rotulo">Ao começar de novo, os livros que pararam ou esperavam voltam para a fila.</p>{/if}
    {:else}
      <p class="vazio">A fila está vazia. Ponha nela os livros da estante que ainda não foram processados, ou importe vários arquivos de uma vez, aqui embaixo.</p>
    {/if}
  </section>

  {#if candidatos.length}
    <section class="bloco">
      <h3>Da estante</h3>
      <p class="o">Livros importados que ainda não passaram pelos modelos. Cada um é processado com o que já está escolhido na tela dele.</p>
      <ul class="marcar">{#each candidatos as l (l.id)}<li><label><input type="checkbox" bind:group={marcados} value={l.id} /> <span class="t">{l.titulo}</span> <span class="rotulo">{l.autor}</span></label></li>{/each}</ul>
      <Botao disabled={!marcados.length} onclick={async () => { await faz('/api/fila', 'POST', { livros: marcados }); marcados = [] }}>Pôr {marcados.length || ''} na fila</Botao>
    </section>
  {/if}

  <section class="bloco">
    <h3>Importar vários</h3>
    <p class="o">Escolha os arquivos; o app lê cada um e dá um palpite de título, autor, idioma e do que fazer. Você confere, e os marcados são importados e entram na fila.</p>
    <div class="escolhas">
      <label class="botao-arq"><span>Escolher arquivos</span><input type="file" multiple accept=".pdf,.epub,.mobi,.azw,.azw3,.docx,.odt,.rtf,.fb2,.html,.htm,.txt" onchange={escolhe} /></label>
      <label class="botao-arq"><span>Escolher uma pasta inteira</span><input type="file" webkitdirectory onchange={escolhe} /></label>
    </div>
    {#if linhas.length}
      <div class="tabela" role="table" aria-label="Arquivos a importar">
        {#each linhas as l, k}
          <div class="linha" role="row" class:fora={!l.marcado}>
            <input type="checkbox" bind:checked={linhas[k].marcado} disabled={l.vendo} aria-label="Importar {l.nome}" />
            <span class="arq">{l.nome}{#if l.vendo}<span class="rotulo"> · lendo…</span>{/if}</span>
            <label><span class="rotulo">Título</span><input bind:value={linhas[k].titulo} autocomplete="off" /></label>
            <label><span class="rotulo">Autor</span><input bind:value={linhas[k].autor} autocomplete="off" /></label>
            <label><span class="rotulo">Idioma</span><select bind:value={linhas[k].idioma}><option value="en">Inglês</option><option value="de">Alemão</option><option value="pt">Português</option></select></label>
            <label><span class="rotulo">O que fazer</span><select bind:value={linhas[k].tipo}>{#each TIPOS as [v, n]}<option value={v}>{n}</option>{/each}</select></label>
            <label class="rapido-linha"><input type="checkbox" bind:checked={linhas[k].rapido} disabled={l.tipo !== 'traducao'} /> <span class="rotulo">Rascunho rápido</span></label>
            {#if l.aviso}<span class="motivo">{l.aviso}</span>{/if}
          </div>
        {/each}
      </div>
      <Botao variante="cheio" disabled={importando || !linhas.some((l) => l.marcado && l.titulo.trim() && l.autor.trim())} onclick={importa}>{importando ? 'Importando…' : `Importar ${linhas.filter((l) => l.marcado).length} e pôr na fila`}</Botao>
    {/if}
  </section>
{:else if !erro}
  <div class="esqueleto" aria-label="Carregando a fila"><span></span><span></span><span></span></div>
{/if}

<style>
  .volta { text-decoration: none; } .volta:hover { color: var(--papel); }
  .o { color: var(--apagado); max-width: 62ch; margin: 0; }
  .bloco { display: grid; gap: var(--e4); padding: var(--e8) 0; border-bottom: 1px solid var(--linha); justify-items: start; }
  .comando { display: flex; flex-wrap: wrap; gap: var(--e4) var(--e6); align-items: center; }
  .comando label, .linha label { display: grid; gap: var(--e1); }
  .fila { list-style: none; margin: 0; padding: 0; width: 100%; }
  .fila li { display: grid; grid-template-columns: 2rem minmax(0, 1fr) auto auto; gap: var(--e4); align-items: baseline; padding: var(--e4) 0; border-top: 1px solid var(--linha); }
  .n { color: var(--apagado); }
  .quem { display: grid; gap: var(--e1); min-width: 0; }
  .t { font-family: var(--display); text-transform: var(--caixa-titulos); font-size: 1.05rem; line-height: 1.15; text-decoration: none; overflow-wrap: anywhere; } a.t:hover { color: var(--acento); }
  .motivo { color: var(--revisar); font-size: 0.875rem; overflow-wrap: anywhere; }
  .acoes { display: flex; gap: var(--e3); align-items: baseline; justify-content: end; min-width: 6rem; }
  .seta { all: unset; cursor: pointer; padding: 0 var(--e2); color: var(--apagado); font-family: var(--mono); transition: color var(--rapido) var(--curva); }
  .seta:hover { color: var(--papel); } .seta:active { transform: scale(0.9); } .seta:focus-visible { outline: 1px solid var(--acento); outline-offset: 2px; }
  .vazio { color: var(--apagado); max-width: 62ch; }
  .marcar { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--e2); }
  .marcar label { display: flex; gap: var(--e3); align-items: baseline; cursor: pointer; }
  .tabela { display: grid; gap: 0; width: 100%; }
  .linha { display: grid; grid-template-columns: auto minmax(8rem, 1.2fr) minmax(0, 1.5fr) minmax(0, 1.2fr) auto auto auto; gap: var(--e3); align-items: end; padding: var(--e3) 0; border-top: 1px solid var(--linha); }
  .linha .rapido-linha { display: flex; gap: var(--e2); align-items: center; padding-bottom: var(--e2); } .linha .rapido-linha input:disabled { opacity: 0.4; }
  .escolhas { display: flex; flex-wrap: wrap; gap: var(--e3); }
  .botao-arq { position: relative; display: inline-flex; border: 1px solid var(--linha); border-radius: var(--raio); padding: var(--e2) var(--e4); cursor: pointer; font-family: var(--mono); font-size: var(--t-rotulo); text-transform: uppercase; letter-spacing: 0.12em; color: var(--apagado); }
  .botao-arq:hover, .botao-arq:focus-within { color: var(--papel); border-color: var(--acento); }
  .botao-arq input { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; }
  .linha input:not([type]) { width: 100%; }
  .linha.fora { opacity: 0.6; }
  .arq { font-family: var(--mono); font-size: 0.8125rem; overflow-wrap: anywhere; align-self: center; }
  .linha .motivo { grid-column: 2 / -1; }
  .esqueleto { display: grid; gap: var(--e3); padding: var(--e8) 0; max-width: 40rem; } .esqueleto span { height: 0.7rem; background: var(--linha); border-radius: var(--raio); } .esqueleto span:last-child { width: 60%; }
  @media (max-width: 900px) { .fila li { grid-template-columns: 2rem minmax(0, 1fr); } .fila li > :global(.chip), .acoes { grid-column: 2; justify-content: start; } .linha { grid-template-columns: auto 1fr; } .linha label, .linha .motivo { grid-column: 2; } }
</style>
