<script>
  // valor de 0 a 1; sem valor = indeterminado (linha que percorre)
  let { valor = null, rotulo = '' } = $props()
</script>

<div class="p" role="progressbar" aria-valuenow={valor === null ? undefined : Math.round(valor * 100)} aria-valuemin="0" aria-valuemax="100" aria-label={rotulo}>
  <div class="trilho"><div class="barra" class:ind={valor === null} style:transform={valor === null ? null : `scaleX(${valor})`}></div></div>
  {#if rotulo}<div class="rotulo linha"><span>{rotulo}</span>{#if valor !== null}<span>{Math.round(valor * 100)}%</span>{/if}</div>{/if}
</div>

<style>
  .trilho { height: 1px; background: var(--linha-forte); position: relative; overflow: hidden; }
  .barra { position: absolute; inset: -1px 0; height: 3px; background: var(--acento); transform-origin: left; transition: transform var(--lento) var(--curva); }
  .ind { width: 30%; animation: corre 1.6s var(--curva) infinite; }
  @keyframes corre { from { transform: translateX(-100%); } to { transform: translateX(340%); } }
  .linha { display: flex; justify-content: space-between; margin-top: var(--e2); }
  @media (prefers-reduced-motion: reduce) { .ind { animation: none; width: 100%; opacity: 0.4; } }
</style>
