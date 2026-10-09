<script>
  // Livro ao vivo: o original de um lado, a tradução enchendo do outro, página a página. Mostra o andamento dos modelos, não o texto
  // aprovado: a tinta só fica firme na Revisão, com o aceite. O fluxo anda por fases (traduz tudo, depois confere tudo, depois corrige
  // e julga), então o livro é percorrido mais de uma vez: primeiro o texto aparece, depois chegam as marcas na margem.
  import { api } from './api.js'
  let { id, v = null } = $props()      // v = o que o modelo está escrevendo agora (st.ao_vivo), ou null se nada está rodando
  let pg = $state(0), d = $state(null), seguir = $state(true), erro = $state('')
  let rodando = $derived(!!v)      // só o liga/desliga: v muda a cada consulta e não pode reiniciar o relógio abaixo
  const ESCREVE = ['propondo', 'corrigindo', 'sentenciando']
  const MARCA = { conferido: ['✓', 'Conferido pelo auditor, sem ressalva'], objecao: ['!', 'O auditor apontou'], disputa: ['§', 'Em disputa: vai ao juiz'],
                  juiz: ['J', 'Corrigido pelo juiz: você confere na Revisão'], voce: ['?', 'Fica para você decidir na Revisão'] }
  const limpo = (t) => (t ?? '').replace(/<\/?[aib]\d+>|<n\d+\/>/g, '').replace(/\s*<br>\s*/g, '\n').replace(/^#+\s*/, '')

  // O texto que sai do modelo chega a cada 700 ms; qual bloco está em pauta, só a cada consulta desta tela. Para os dois andarem juntos:
  // quando o modelo muda de parágrafo a tela consulta na hora, e o texto ao vivo só aparece no bloco quando a consulta é do mesmo parágrafo.
  let fonteAgora = $derived(v?.fonte ?? null), fonteDaConsulta = $state(null)
  let emDia = $derived(fonteDaConsulta === fonteAgora)
  $effect(() => { if (fonteAgora !== null) carrega() })
  async function carrega() {
    try {
      const pedida = v?.fonte ?? null
      const r = await api(`/api/livro/${id}/vivo/${pg}`)
      fonteDaConsulta = pedida
      // seguindo o trabalho: quando o bloco em pauta muda de página, o livro vira sozinho
      if (seguir && v && r.agora && r.agora.pagina !== r.pagina) { pg = r.agora.pagina; return }
      d = r; pg = r.pagina; erro = ''
    } catch (e) { erro = e.message }
  }
  $effect(() => { pg; carrega(); if (!rodando) return; const t = setInterval(carrega, 2000); return () => clearInterval(t) })
  // seguindo o trabalho, o parágrafo que está sendo escrito fica à vista (a janela acompanha; a caixa não tem rolagem própria)
  function avista(el) { const r = el.getBoundingClientRect(); if (seguir && (r.bottom > innerHeight || r.top < 0)) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }
  const mostra = (el, ativo) => { const u = (a) => a && avista(el); u(ativo); return { update: u } }
  const vai = (n) => { if (n != null) { seguir = false; pg = n } }
  function tecla(e) { if (e.key === 'ArrowLeft') vai(d?.anterior); else if (e.key === 'ArrowRight') vai(d?.proxima) }
</script>

{#if erro}<p class="rotulo">{erro}</p>
{:else if d}
  <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
  <section class="vivo" aria-label="Livro ao vivo: original e tradução, página a página" tabindex="0" onkeydown={tecla}>
    {#snippet trad(b, ativo)}
      {@const texto = ativo && ESCREVE.includes(v.papel) && v.texto ? v.texto : b.texto}
      <div class="bloco" data-marca={b.marca} class:agora={ativo} use:mostra={ativo && texto}>
        {#if texto}<p class="leitura" class:titulo={b.titulo}>{limpo(texto)}{#if ativo && ESCREVE.includes(v.papel)}<span class="cursor" aria-hidden="true"></span>{/if}{#if b.continua}<span class="rotulo"> · segue na próxima página</span>{/if}</p>
        {:else}<div class="esqueleto" aria-label="Ainda não traduzido"><span></span><span></span><span></span></div>{/if}
        {#if MARCA[b.marca]}<span class="marca" title={[MARCA[b.marca][1], ...b.objecoes].join('\n· ')} aria-label={MARCA[b.marca][1]}>{MARCA[b.marca][0]}</span>{/if}
        {#if b.objecoes.length && b.marca !== 'juiz'}<p class="apontou">{b.objecoes[0]}{b.objecoes.length > 1 ? ` (+${b.objecoes.length - 1})` : ''}</p>{/if}
      </div>
    {/snippet}
    {#if d.imagem}
      <div class="aberto">
        <div class="folha original">
          <div class="rotulo cab">Original · página {d.pagina}</div>
          <img src="/api/livro/{id}/pagina/{d.pagina}" alt="Página {d.pagina} do original" />
        </div>
        <div class="lombada" aria-hidden="true"></div>
        {#key d.pagina}
          <div class="folha traducao">
            <div class="rotulo cab">Tradução · {v ? 'em andamento' : 'como os modelos deixaram'}</div>
            {#each d.blocos as b (b.id)}{@render trad(b, !!v && emDia && d.agora?.id === b.id)}{/each}
            {#if !d.processado}<p class="rotulo">Este livro ainda não passou pelos modelos.</p>{/if}
          </div>
        {/key}
      </div>
    {:else}
      <!-- sem imagem de página: cada parágrafo do original fica na mesma linha da sua tradução, e os dois andam juntos -->
      {#key d.pagina}
        <div class="aberto pares">
          <div class="par"><div class="rotulo cab">Original</div><div class="rotulo cab">Tradução · {v ? 'em andamento' : 'como os modelos deixaram'}</div></div>
          {#each d.blocos as b (b.id)}
            {@const ativo = !!v && emDia && d.agora?.id === b.id}
            <div class="par"><p class="leitura de" class:titulo={b.titulo} class:agora={ativo}>{limpo(b.fonte).replace(/\*/g, '')}</p>{@render trad(b, ativo)}</div>
          {/each}
          {#if !d.processado}<p class="rotulo">Este livro ainda não passou pelos modelos.</p>{/if}
        </div>
      {/key}
    {/if}
    <div class="pe rotulo">
      <button onclick={() => vai(d.anterior)} disabled={d.anterior == null} aria-label="Página anterior">◄</button>
      <span>{d.n} de {d.total}</span>
      <button onclick={() => vai(d.proxima)} disabled={d.proxima == null} aria-label="Próxima página">►</button>
      {#if v}<label class="segue"><input type="checkbox" bind:checked={seguir} onchange={() => seguir && (pg = 0)} /> seguir o trabalho</label>{/if}
      {#if !d.imagem}<span class="legenda">A imagem da página só existe para livro em PDF. Neste formato o original aparece como texto, repartido em páginas pelo app.</span>{/if}
      <span class="legenda">Tinta clara: proposta dos modelos · ✓ conferido · ! apontado · J do juiz · ? para você · nada entra no livro sem o seu aceite</span>
    </div>
  </section>
{/if}

<style>
  .vivo { display: grid; gap: var(--e4); outline: none; } .vivo:focus-visible .aberto { border-color: var(--acento); }
  .aberto { display: grid; grid-template-columns: minmax(0, 1fr) 1px minmax(0, 1fr); border: 1px solid var(--linha); background: var(--superficie); perspective: 1800px; min-height: 28rem; }
  .lombada { background: var(--linha-forte); box-shadow: 0 0 2.5rem 0.6rem color-mix(in srgb, var(--fundo) 85%, transparent); }
  .folha { position: relative; padding: var(--e6) var(--e8); display: grid; gap: var(--e4); align-content: start; min-width: 0; }      /* sem altura máxima: a página inteira cabe na caixa, sem barra de rolagem */
  .cab { color: var(--apagado); }
  /* livro sem imagem de página: linhas de dois, original e tradução na mesma altura; o fio do meio é a lombada */
  .pares { display: block; padding: var(--e6) 0; animation: surge 320ms var(--curva) both; }
  .par { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .par > * { padding: var(--e2) var(--e8); min-width: 0; } .par > :first-child { border-right: 1px solid var(--linha-forte); }
  .par .de { color: var(--apagado); border-left: 2px solid transparent; } .par .de.agora { border-left-color: var(--acento); }
  .par .bloco { margin-left: 0; padding-left: var(--e8); padding-right: calc(var(--e8) + var(--e6)); } .par .bloco .marca { right: var(--e6); top: 0.6em; }
  .pares > .rotulo { padding: var(--e4) var(--e8); }
  @keyframes surge { from { opacity: 0; transform: translateY(6px); } }
  .original img { width: 100%; border: 1px solid var(--linha); background: #fff; }
  .original .leitura { color: var(--apagado); }
  .leitura { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; max-width: none; }
  .titulo { font-family: var(--display); text-transform: var(--caixa-titulos); font-size: 1.25rem; line-height: 1.15; }
  /* a folha da tradução vira sobre a lombada quando a página muda */
  .traducao { transform-origin: left center; animation: vira 520ms var(--curva) both; backface-visibility: hidden; }
  @keyframes vira { from { transform: rotateY(-78deg); opacity: 0.2; } }
  .bloco { position: relative; padding-right: var(--e8); display: grid; gap: var(--e1); border-left: 2px solid transparent; padding-left: var(--e3); margin-left: calc(var(--e3) * -1 - 2px); }
  /* proposta ainda não conferida: tinta clara. Conferida ou julgada: tinta cheia (mas só o aceite a põe no livro) */
  .bloco[data-marca='proposto'] .leitura, .bloco[data-marca='objecao'] .leitura, .bloco[data-marca='disputa'] .leitura { color: var(--apagado); }
  .bloco.agora, .original .agora { border-left: 2px solid var(--acento); } .original .agora { padding-left: var(--e3); margin-left: calc(var(--e3) * -1 - 2px); }
  .marca { position: absolute; right: 0; top: 0.2em; width: 1.4rem; height: 1.4rem; display: grid; place-items: center; font-family: var(--mono); font-size: 0.75rem; border: 1px solid currentColor; border-radius: 50%; color: var(--ok); cursor: help; }
  [data-marca='objecao'] .marca, [data-marca='voce'] .marca, [data-marca='disputa'] .marca { color: var(--revisar); } [data-marca='juiz'] .marca { color: var(--acento); }
  .apontou { margin: 0; font-size: 0.8125rem; color: var(--revisar); overflow-wrap: anywhere; max-width: none; }
  .esqueleto { display: grid; gap: 0.55rem; padding: 0.35rem 0; } .esqueleto span { height: 0.6rem; background: var(--linha); border-radius: var(--raio); } .esqueleto span:last-child { width: 62%; }
  .cursor { display: inline-block; width: 0.5em; height: 1em; margin-left: 2px; background: var(--acento); vertical-align: text-bottom; animation: pisca 1s steps(2) infinite; }
  @keyframes pisca { 50% { opacity: 0; } }
  .pe { display: flex; flex-wrap: wrap; gap: var(--e3) var(--e6); align-items: center; }
  .pe button { all: unset; cursor: pointer; padding: var(--e1) var(--e3); border: 1px solid var(--linha-forte); border-radius: var(--raio); color: var(--papel); transition: border-color var(--rapido) var(--curva); }
  .pe button:hover:not(:disabled) { border-color: var(--papel); } .pe button:active:not(:disabled) { transform: scale(0.96); } .pe button:disabled { opacity: 0.35; cursor: default; }
  .pe button:focus-visible { outline: 1px solid var(--acento); outline-offset: 3px; }
  .segue { display: flex; gap: var(--e2); align-items: center; cursor: pointer; color: var(--papel); }
  .legenda { flex-basis: 100%; text-transform: none; letter-spacing: 0.02em; }
  @media (max-width: 700px) { .aberto { grid-template-columns: 1fr; } .lombada, .original { display: none; } .par { grid-template-columns: 1fr; } .par > :first-child { border-right: 0; font-size: 0.9em; padding-bottom: 0; } }
  @media (prefers-reduced-motion: reduce) { .traducao, .cursor, .pares { animation: none; } }
</style>
