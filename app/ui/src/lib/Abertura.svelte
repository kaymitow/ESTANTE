<script>
  // Abertura de ~1,6 s: logotipo espaçado que se revela e uma cortina que sobe. Clique ou tecla pula.
  import { onMount } from 'svelte'
  let { aoTerminar } = $props()
  let saindo = $state(false)
  const letras = 'ESTANTE'.split('')

  function fim() {
    if (saindo) return
    saindo = true
    setTimeout(aoTerminar, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 700)
  }
  onMount(() => {
    const t = setTimeout(fim, 1600)
    const tecla = () => fim()
    addEventListener('keydown', tecla)
    return () => { clearTimeout(t); removeEventListener('keydown', tecla) }
  })
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div class="abertura" class:saindo onclick={fim}>
  <div class="marca" aria-label="Estante">
    {#each letras as l, i}<span style:animation-delay="{120 + i * 70}ms">{l}</span>{/each}
  </div>
  <div class="rotulo sub">arquivo de leitura · local e privado</div>
  <div class="rotulo pular">clique para entrar</div>
</div>

<style>
  .abertura { position: fixed; inset: 0; z-index: 100; background: var(--fundo); display: grid; place-content: center; justify-items: center; gap: var(--e6);
    transition: transform var(--lento) var(--curva); cursor: pointer; }
  .saindo { transform: translateY(-100%); }
  .marca { font-family: var(--marca); font-size: clamp(2.5rem, 9vw, 7rem); letter-spacing: 0.32em; padding-left: 0.32em; display: flex; overflow: hidden; }
  .marca span { display: inline-block; transform: translateY(110%); animation: sobe var(--lento) var(--curva) forwards; }
  @keyframes sobe { to { transform: none; } }
  .sub { opacity: 0; animation: aparece var(--lento) var(--curva) 700ms forwards; }
  .pular { position: absolute; bottom: var(--e8); left: 50%; transform: translateX(-50%); opacity: 0; animation: aparece var(--lento) 1000ms forwards; }
  @keyframes aparece { to { opacity: 1; } }
  @media (prefers-reduced-motion: reduce) { .marca span { transform: none; animation: none; } .sub, .pular { opacity: 1; animation: none; } }
</style>
