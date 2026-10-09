<script>
  import Abertura from './lib/Abertura.svelte'
  import Biblioteca from './telas/Biblioteca.svelte'
  import Livro from './telas/Livro.svelte'
  import Revisao from './telas/Revisao.svelte'
  import Modelos from './telas/Modelos.svelte'
  import Glossario from './telas/Glossario.svelte'
  import Leitura from './telas/Leitura.svelte'
  import Leitor from './telas/Leitor.svelte'
  import Config from './telas/Config.svelte'
  import TribunalDemo from './telas/TribunalDemo.svelte'
  import Fila from './telas/Fila.svelte'
  import { api } from './lib/api.js'
  import { le, grava, aplica } from './lib/aparencia.js'

  const rota = () => decodeURIComponent(location.hash.slice(1)) || 'biblioteca'     // 'biblioteca' | 'livro/<id>' | 'revisao/<id>' | 'config/<aba>'
  let caminho = $state(rota())
  let tela = $derived(caminho.split('/')[0])
  let param = $derived(caminho.split('/')[1] ?? '')
  let aparencia = $state(le())      // tema, cores, fontes, tamanho: escolha de quem usa (Configurações → Aparência)
  let abrindo = $state(le().abertura)
  let chave = $state(0)        // força a transição ao trocar de tela
  let rede = $state(null)      // o que está ligado em Configurações → Rede
  $effect(() => { api('/api/config').then((c) => (rede = c.rede)).catch(() => {}) })
  let ligadas = $derived(rede ? [['pesquisa', 'pesquisa'], ['edicoes', 'acervos'], ['modelo_fora', 'modelo de fora']].filter(([k]) => rede[k]).map(([, n]) => n) : [])

  const telas = [
    { id: 'biblioteca', nome: 'Biblioteca' },
    { id: 'modelos', nome: 'Modelos' },
    { id: 'config', nome: 'Configurações' },
  ]

  const ativa = (id) => tela === id || (id === 'biblioteca' && !telas.some((t) => t.id === tela))
  function ir(id) { if (id === caminho) return; const mesma = id.split('/')[0] === tela; caminho = id; if (!mesma) { chave++; scrollTo({ top: 0 }) } if (rota() !== id) location.hash = id }

  $effect(() => {
    const aoMudar = () => ir(rota())
    addEventListener('hashchange', aoMudar)
    return () => removeEventListener('hashchange', aoMudar)
  })

  $effect(() => { aplica(aparencia); grava(aparencia) })
</script>

{#if abrindo}<Abertura aoTerminar={() => (abrindo = false)} />{/if}

<div class="casca">
  <nav aria-label="Principal">
    <a class="marca" href="#biblioteca" aria-label="Estante: ir para o acervo">
      <!-- a logo: três lombadas numa prateleira, nas cores do tema -->
      <svg class="lombadas" viewBox="0 0 32 32" aria-hidden="true"><rect class="l1" x="6" y="5" width="6" height="19" rx="1.4" /><rect class="l2" x="13" y="5" width="6" height="19" rx="1.4" /><rect class="l3" x="20" y="5" width="6" height="19" rx="1.4" /><path class="corte" d="M5 8.2h22M5 10h22M5 19.6h22M5 21.4h22" /><rect class="l1" x="3" y="25.4" width="26" height="1.5" rx=".75" /></svg>
      <span class="nome">Estante</span>
      <span class="rotulo lema">arquivo de leitura</span>
    </a>
    <ul>
      {#each telas as t, i}
        <li><button class:on={ativa(t.id)} onclick={() => ir(t.id)} aria-current={ativa(t.id) ? 'page' : undefined}>
          <span class="rotulo">{String(i + 1).padStart(2, '0')}</span>{t.nome}</button></li>
      {/each}
    </ul>
    <div class="rodape">
      {#if ligadas.length}<a class="rotulo rede" href="#config/rede">Rede ligada: {ligadas.join(', ')}</a>{:else}<span class="rotulo">Local · sem rede · sem censura</span>{/if}
    </div>
  </nav>

  {#key chave}
    <main class="tela">
      {#if tela === 'livro'}<Livro id={param} />{:else if tela === 'revisao'}<Revisao id={param} />{:else if tela === 'modelos'}<Modelos />{:else if tela === 'glossario'}<Glossario id={param} />{:else if tela === 'leitura'}<Leitura id={param} />{:else if tela === 'ler'}<Leitor id={param} />{:else if tela === 'fila'}<Fila />{:else if tela === 'tribunal-demo'}<TribunalDemo />{:else if tela === 'config'}<Config bind:aparencia aba={param} aoMudarRede={(r) => (rede = r)} />{:else}<Biblioteca {rede} />{/if}
    </main>
  {/key}
</div>

<style>
  .casca { display: grid; grid-template-columns: 17rem minmax(0, 1fr); min-height: 100vh; }
  nav { position: sticky; top: 0; height: 100vh; border-right: 1px solid var(--linha); padding: var(--e12) var(--e6) var(--e8); display: grid; grid-template-rows: auto 1fr auto; gap: var(--e12);
        background: linear-gradient(180deg, color-mix(in srgb, var(--superficie) 70%, transparent), transparent 55%); }
  /* a marca não muda com a fonte que o usuário escolhe; só a cor acompanha o tema */
  .marca { display: grid; gap: var(--e3); justify-items: start; text-decoration: none; color: var(--papel); padding-bottom: var(--e8); border-bottom: 1px solid var(--linha); }
  .marca .nome { font-family: var(--marca); text-transform: uppercase; letter-spacing: 0.26em; font-size: 1.75rem; line-height: 1; }
  .marca .lema { color: var(--apagado); }
  .lombadas { width: 2.5rem; height: 2.5rem; transition: transform var(--medio) var(--curva); }
  .lombadas .l1 { fill: var(--papel); } .lombadas .l2 { fill: var(--acento); } .lombadas .l3 { fill: var(--linha-forte); }
  .lombadas .corte { fill: none; stroke: var(--fundo); stroke-width: .7; }
  .marca:hover .lombadas { transform: translateY(-2px); } .marca:focus-visible { outline: 1px solid var(--acento); outline-offset: 6px; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--e2); align-content: start; }
  nav button { all: unset; cursor: pointer; display: flex; gap: var(--e4); align-items: baseline; width: 100%; padding: var(--e2) 0; color: var(--apagado); position: relative; font-size: 1.0625rem;
    transition: color var(--medio) var(--curva), transform var(--medio) var(--curva); box-sizing: border-box; }
  nav button::before { content: ''; position: absolute; left: calc(var(--e6) * -1); top: 50%; width: 0; height: 1px; background: var(--acento); transition: width var(--medio) var(--curva); }
  nav button:hover { color: var(--papel); transform: translateX(var(--e2)); }
  nav button.on { color: var(--papel); }
  nav button.on::before { width: var(--e4); }
  nav button:focus-visible { outline: 1px solid var(--acento); outline-offset: 3px; }
  .rodape { display: grid; gap: var(--e2); padding-top: var(--e4); border-top: 1px solid var(--linha); } .rodape .rede { color: var(--revisar); } .rodape a { text-decoration: none; } .rodape a:hover { color: var(--papel); }

  main { padding: var(--e12) clamp(var(--e6), 5vw, var(--e24)) var(--e24); min-width: 0; }
  .tela { animation: troca var(--medio) var(--curva) both; }
  @keyframes troca { from { opacity: 0; transform: translateY(12px); } }

  @media (max-width: 900px) {
    .casca { grid-template-columns: 1fr; }
    /* tela estreita: uma faixa só, a marca à esquerda e as telas à direita; fica presa no alto ao rolar */
    nav { position: sticky; top: 0; z-index: 5; height: auto; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--e2) var(--e6); border-right: 0; border-bottom: 1px solid var(--linha);
          padding: var(--e3) var(--e6); background: var(--fundo); }
    .marca { grid-auto-flow: column; align-items: center; gap: var(--e3); padding: 0; border: 0; } .marca .nome { font-size: 1.25rem; } .marca .lema { display: none; } .lombadas { width: 1.6rem; height: 1.6rem; }
    ul { display: flex; gap: var(--e6); flex-wrap: wrap; } nav button { font-size: 0.9375rem; width: auto; } .rodape { display: none; }
    nav button::before { display: none; }
  }
  @media (prefers-reduced-motion: reduce) { .tela { animation: none; } }
</style>
