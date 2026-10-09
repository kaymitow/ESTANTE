<script>
  // Uma opção explicada: o que é, o que muda com ela ligada ou desligada e, se usa a internet, o que sai do computador.
  let { nome, oque = '', ligado = '', desligado = '', sai = '', children } = $props()
</script>

<div class="opcao">
  <div class="cab">
    <span class="nome">{nome}</span>
    <div class="controle">{@render children?.()}</div>
  </div>
  {#if oque}<p class="oque">{oque}</p>{/if}
  {#if ligado || desligado || sai}
    <dl>
      {#if ligado}<div><dt class="rotulo">Ligado</dt><dd>{ligado}</dd></div>{/if}
      {#if desligado}<div><dt class="rotulo">Desligado</dt><dd>{desligado}</dd></div>{/if}
      {#if sai}<div class="sai"><dt class="rotulo">Sai do computador</dt><dd>{sai}</dd></div>{/if}
    </dl>
  {/if}
</div>

<style>
  .opcao { display: grid; gap: var(--e3); padding: var(--e6); border: 1px solid var(--linha); border-radius: var(--raio); background: color-mix(in srgb, var(--superficie) 55%, transparent);
           transition: border-color var(--medio) var(--curva); min-width: 0; container-type: inline-size; }
  .opcao:hover { border-color: var(--linha-forte); }
  .cab { display: flex; flex-wrap: wrap; gap: var(--e3) var(--e6); align-items: center; justify-content: space-between; }
  .nome { font-family: var(--display); text-transform: var(--caixa-titulos); font-size: 1.15rem; letter-spacing: 0.04em; line-height: 1.15; }
  .controle { display: flex; flex-wrap: wrap; gap: var(--e3); align-items: center; }
  .oque { color: var(--papel); max-width: 70ch; }
  dl { margin: 0; display: grid; gap: var(--e2); }
  dl > div { display: grid; grid-template-columns: 11.5rem minmax(0, 1fr); gap: var(--e3); align-items: baseline; }
  dd { margin: 0; color: var(--apagado); max-width: 62ch; }
  .sai dt { color: var(--revisar); }
  @container (max-width: 34rem) { dl > div { grid-template-columns: 1fr; gap: 0; } }
</style>
