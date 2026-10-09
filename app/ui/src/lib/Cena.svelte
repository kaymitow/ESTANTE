<script>
  // A cena do tribunal: tradutor, auditor e juiz desenhados em traço de gravura, com as pilhas de folhas. Só desenho: quem decide
  // a pose e os números é lib/cena.js, a partir dos dados do processamento. As figuras são decoração (aria-hidden); o texto real
  // dos modelos continua nos balões do Tribunal. Cores só pelos tokens do tema; movimento só com transform e opacity.
  import { untrack } from 'svelte'
  let { p, pl, nomes = {}, ev = [] } = $props()      // p = pose(); pl = pilhas(); nomes = { tradutor, auditor, juiz } (modelos); ev = eventos() da última consulta
  // a folha que voa: sai da mesa de quem terminou e pousa na pilha de destino. Uma por vez, no máximo a cada 450 ms; com as animações
  // desligadas não voa nada (os números das pilhas já dizem tudo)
  const DE = { tradutor: [149, 190], auditor: [497, 190], juiz: [325, 160] }
  const PARA = { conferir: [584, 186], corrigir: [104, 186], disputa: [272, 156], aprovados: [135, 288], juiz: [325, 288], voce: [515, 288] }
  const MARCA = { aprovado: 'ok', 'causa-tradutor': 'ok', objecao: 'risco', disputa: 'risco', 'causa-auditor': 'risco', 'causa-usuario': 'duvida' }
  const quieto = () => document.documentElement.dataset.movimento === 'nao' || matchMedia('(prefers-reduced-motion: reduce)').matches
  let voos = $state([]), toque = $state(false), ultimo = 0, seq = 0
  $effect(() => {
    const novos = ev
    if (!novos.length || quieto() || performance.now() - ultimo < 450) return
    ultimo = performance.now()
    untrack(() => { voos = [...voos, ...novos.map((e) => ({ ...e, k: ++seq }))]; if (novos[0].de === 'juiz') { toque = true; setTimeout(() => (toque = false), 700) } })
  })
  function voa(el, e) {
    const [x0, y0] = DE[e.de], [x1, y1] = PARA[e.para], a = `translate(${x0}px, ${y0}px)`, b = `translate(${x1}px, ${y1}px)`
    el.animate([{ transform: a, opacity: 0 }, { transform: a, opacity: 1, offset: 0.12 }, { transform: b, opacity: 1, offset: 0.88 }, { transform: b, opacity: 0 }],
               { duration: 900, easing: 'ease-in-out' }).onfinish = () => (voos = voos.filter((v) => v.k !== e.k))
  }
  const folhas = (n) => Array.from({ length: Math.min(5, Math.max(0, n)) }, (_, k) => k)
  const BANDEJAS = [['aprovados', 'aprovados pelos modelos', 150], ['juiz', 'do juiz, a conferir', 340], ['voce', 'para você', 530]]
</script>

<!-- sem juiz, o topo da sala (onde ele sobe) fica de fora: a cena não deixa um vazio em cima -->
<svg class="cena" viewBox={p.juiz === 'ausente' ? '0 44 680 286' : '0 0 680 330'} aria-hidden="true" data-tradutor={p.tradutor} data-auditor={p.auditor} data-juiz={p.juiz}>
  <g class="traco">
    <!-- juiz: sobe por trás da bancada quando há disputa -->
    <g class="juiz">
      <g transform="translate(340,62)">
        <path d="M-36 52L-29 14Q-25 2-10 0H10Q25 2 29 14L36 52" />
        <path class="fino" d="M-24 22L-27 46M-17 16L-19 46M17 16L19 46M24 22L27 46" />
        <path class="cheio" d="M-5 1V14H-1V1ZM1 1V14H5V1Z" />
        <circle cx="-15" cy="-25" r="5" /><circle cx="-18" cy="-15" r="5" /><circle cx="-15" cy="-5" r="5" />
        <circle cx="15" cy="-25" r="5" /><circle cx="18" cy="-15" r="5" /><circle cx="15" cy="-5" r="5" />
        <path d="M-15 -28Q0 -44 15 -28" /><circle cy="-18" r="13" />
        <g class="olhos cheio"><circle cx="-5" cy="-18" r="1.4" /><circle cx="5" cy="-18" r="1.4" /></g>
        <path class="fino" d="M-8 -24L-3 -23M8 -24L3 -23M-3 -10H3" />
      </g>
      <path class="vazio" d="M369 78Q382 90 380 106" />
      <g transform="translate(380,106)"><g class="martelo" class:toque><path d="M0 0L16 -20" /><rect class="destaque" x="5" y="-25" width="22" height="10" rx="2" transform="rotate(39 16 -20)" /></g></g>
    </g>
    <rect x="252" y="112" width="176" height="74" /><rect class="fino" x="264" y="124" width="152" height="50" /><rect x="396" y="106" width="22" height="6" />
    <!-- pilha "em disputa", na bancada -->
    {#each folhas(pl.disputa) as k}<rect class="fino" x={272} y={164 - k * 3} width="34" height="5" />{/each}

    <!-- tradutor -->
    <path class="vazio mao-t" d="M128 172Q160 176 160 194" />
    <g transform="translate(128,150)" class="corpo-t"><g class="respira">
      <path d="M-26 54L-22 12Q-20 2-8 0H8Q20 2 22 12L26 54" /><circle cy="-18" r="13" />
      <path class="vazio" d="M-13 -21Q-9 -31 1 -30Q10 -30 13 -21" />
      <g class="olhos cheio olhos-t"><circle cx="-4" cy="-16" r="1.4" /><circle cx="6" cy="-16" r="1.4" /></g>
      <path class="fino" d="M-1 -9H4" />
    </g></g>
    <!-- auditor -->
    <path class="vazio mao-a" d="M552 172Q526 176 524 192" />
    <g transform="translate(552,150)" class="corpo-a"><g class="respira depois">
      <path d="M-26 54L-22 12Q-20 2-8 0H8Q20 2 22 12L26 54" /><circle cy="-18" r="13" />
      <path class="vazio" d="M-12 -24Q-13 -30 -8 -30M12 -24Q13 -30 8 -30" />
      <g class="olhos cheio olhos-a"><circle cx="-5.5" cy="-18" r="1.4" /><circle cx="5.5" cy="-18" r="1.4" /></g>
      <g class="vazio fino"><circle cx="-5.5" cy="-18" r="4.6" /><circle cx="5.5" cy="-18" r="4.6" /><path d="M-.9 -18H.9" /></g>
      <path class="vazio fino" d="M-5 -9Q0 -6 5 -9" />
    </g></g>
    <!-- mesas, com o livro-fonte, a folha de cada um e as pilhas -->
    <rect x="56" y="202" width="144" height="40" /><rect x="480" y="202" width="144" height="40" />
    <path class="livro" d="M64 202V190Q74 185 82 190Q90 185 100 190V202ZM82 190V202" />
    <path d="M138 202L144 192H190L184 202Z" /><path class="tinta fino" d="M150 197H178" />
    <path d="M486 202L492 192H538L532 202Z" />
    {#each folhas(pl.corrigir) as k}<rect class="fino" x={104} y={196 - k * 3} width="30" height="5" />{/each}
    {#each folhas(pl.conferir) as k}<rect class="fino" x={584} y={196 - k * 3} width="30" height="5" />{/each}
    <g class="mao-t"><path d="M160 194L172 172" /><path class="destaque" d="M172 172Q182 164 180 154Q170 158 168 170Z" /></g>
    <g class="mao-a"><path d="M524 192L516 188" /><circle class="vazio" cx="508" cy="184" r="8" /></g>
    <path class="lapis" d="M576 200L586 176" />
    <!-- balcão e bandejas -->
    <path d="M24 262H656" />
    {#each BANDEJAS as [id, , x]}
      <path d="M{x - 46} 300H{x + 46}L{x + 40} 312H{x - 40}Z" />
      {#each folhas(pl[id]) as k}<rect class="fino" x={x - 30} y={294 - k * 3} width="60" height="5" />{/each}
    {/each}
    <!-- bilhete no meio da sala quando o trabalho para -->
    {#if p.ato === 'pausado' || p.ato === 'erro'}<rect class="fino" x="304" y="204" width="72" height="22" rx="1" />{/if}
    {#each voos as e (e.k)}
      <g class="voo" use:voa={e}><rect x="0" y="0" width="30" height="9" />
        {#if MARCA[e.tipo] === 'ok'}<path class="m-ok" d="M20 4.5l2.5 2.5l4.5-5" />{:else if MARCA[e.tipo] === 'risco'}<path class="m-risco" d="M5 3h9M5 6h14" />{:else if MARCA[e.tipo] === 'duvida'}<circle class="m-duvida" cx="24" cy="4.5" r="2.2" />{/if}</g>
    {/each}
  </g>
  <g class="letras">
    <text x="340" y="153">Juiz{nomes.juiz ? ' · ' + nomes.juiz : ''}</text>
    <text x="128" y="227">{nomes.papelTradutor ?? 'Tradutor'}</text><text class="menor" x="128" y="238">{nomes.tradutor ?? ''}</text>
    <text x="552" y="227">Auditor</text><text class="menor" x="552" y="238">{nomes.auditor ?? ''}</text>
    {#if pl.corrigir}<text class="num" x="80" y="179">{pl.corrigir}</text>{/if}
    {#if pl.conferir}<text class="num" x="604" y="174">{pl.conferir}</text>{/if}
    {#if pl.disputa}<text class="num" x="289" y="150">{pl.disputa}</text>{/if}
    {#if p.ato === 'pausado' || p.ato === 'erro'}<text x="340" y="218">{p.ato === 'erro' ? 'parou' : 'em pausa'}</text>{/if}
    {#each BANDEJAS as [id, rotulo, x]}<text class="num" x={x} y="286">{pl[id]}</text><text class="menor" x={x} y="326">{rotulo}</text>{/each}
  </g>
</svg>

<style>
  .cena { width: 100%; max-width: 52rem; height: auto; display: block; margin: 0 auto; }
  .traco { fill: var(--fundo); stroke: var(--papel); stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
  .fino { stroke-width: 0.9; } .vazio { fill: none; } .cheio { fill: var(--papel); stroke: none; }
  .destaque { fill: var(--acento); stroke: var(--acento); } .lapis { stroke: var(--acento); stroke-width: 2.4; }
  .letras text { font-family: var(--mono); font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase; fill: var(--apagado); text-anchor: middle; }
  .letras .menor { font-size: 8.5px; letter-spacing: 0.04em; text-transform: none; } .letras .num { font-size: 12px; fill: var(--papel); }

  /* o juiz só aparece quando há disputa */
  .juiz { transition: transform 600ms var(--curva, ease), opacity 400ms; }
  [data-juiz='ausente'] .juiz { transform: translateY(60px); opacity: 0; }
  /* poses: cada uma é um gesto pequeno, ligado ao que o modelo está fazendo */
  .olhos { transform-box: fill-box; transform-origin: center; animation: pisca 6s infinite; } .olhos-a { animation-delay: -2.3s; }
  .martelo { transform-box: fill-box; transform-origin: 0% 100%; }
  [data-juiz='julga'] .martelo { animation: bate 2.6s ease-in-out infinite; }
  .martelo.toque { animation: toque 700ms ease-in-out !important; }
  .voo { opacity: 0; } .voo .m-ok { fill: none; stroke: var(--ok); } .voo .m-risco { stroke: var(--acento); stroke-width: 1.1; } .voo .m-duvida { fill: var(--revisar); stroke: none; }
  /* vida em repouso: respirar, um pouco fora de sincronia */
  .respira { animation: respira 4s ease-in-out infinite; } .respira.depois { animation-delay: -1.7s; }
  [data-tradutor='escreve'] .mao-t, [data-tradutor='reescreve'] .mao-t { animation: escreve 1.3s ease-in-out infinite; }
  [data-tradutor='escreve'] .tinta, [data-tradutor='reescreve'] .tinta { stroke-dasharray: 28; animation: tinta 1.3s linear infinite; }
  [data-tradutor='folheia'] .livro { animation: folheia 1.8s ease-in-out infinite; transform-box: fill-box; transform-origin: 50% 100%; }
  /* espera longa: a cada 45 s, o tradutor acena com a mão um instante (só o último 3% do ciclo se mexe) */
  [data-tradutor='espera'] .mao-t { transform: translate(4px, -10px); animation: acena 45s ease-in-out infinite; }
  [data-tradutor='olha-auditor'] .olhos-t { transform: translateX(3px); animation: none; } [data-tradutor='olha-juiz'] .olhos-t { transform: translate(2px, -2px); animation: none; }
  [data-auditor='lupa'] .mao-a { animation: lupa 3s ease-in-out infinite; }
  [data-auditor='limpa-lupa'] .mao-a { animation: limpa 1.2s ease-in-out infinite; }
  [data-auditor='olha-juiz'] .olhos-a { transform: translate(-2px, -2px); animation: none; }
  .mao-t, .mao-a, .olhos-t, .olhos-a { transition: transform 300ms var(--curva, ease); }
  @keyframes pisca { 0%, 93%, 100% { transform: scaleY(1); } 96% { transform: scaleY(0.1); } }
  @keyframes respira { 50% { transform: translateY(-0.7px); } }
  @keyframes toque { 0%, 100% { transform: rotate(0); } 35% { transform: rotate(-14deg); } 60% { transform: rotate(48deg); } }
  @keyframes bate { 0%, 58%, 100% { transform: rotate(0); } 70% { transform: rotate(-14deg); } 80% { transform: rotate(50deg); } 87% { transform: rotate(42deg); } }
  @keyframes escreve { 0%, 100% { transform: translate(0, 0); } 30% { transform: translate(5px, -1px); } 60% { transform: translate(10px, 0); } 80% { transform: translate(4px, 1px); } }
  @keyframes tinta { from { stroke-dashoffset: 28; } to { stroke-dashoffset: 0; } }
  @keyframes folheia { 0%, 100% { transform: scaleX(1); } 50% { transform: scaleX(0.92); } }
  @keyframes lupa { 0%, 100% { transform: translate(0, 0); } 50% { transform: translate(-16px, 0); } }
  @keyframes limpa { 0%, 100% { transform: rotate(0); } 50% { transform: rotate(-8deg); } }
  @keyframes acena { 0%, 93%, 100% { transform: translate(4px, -10px); } 96% { transform: translate(10px, -17px) rotate(-10deg); } }
  /* animações desligadas: poses paradas, que ainda mostram quem trabalha */
  :global([data-movimento='nao']) .cena *, .cena:global(.parada) * { animation: none !important; transition: none !important; }
  @media (prefers-reduced-motion: reduce) { .cena * { animation: none !important; transition: none !important; } }
</style>
