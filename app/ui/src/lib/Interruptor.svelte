<script>
  // Chave de ligar e desligar.
  let { ligado = false, rotulo = '', onclick, disabled = false } = $props()
</script>

<button class="interruptor" class:on={ligado} role="switch" aria-checked={!!ligado} aria-label={rotulo} {disabled} {onclick}><i></i><span class="rotulo">{ligado ? 'Ligado' : 'Desligado'}</span></button>

<style>
  .interruptor { all: unset; cursor: pointer; display: inline-flex; align-items: center; gap: var(--e3); position: relative; }
  .interruptor::before { content: ''; box-sizing: border-box; width: 2.75rem; height: 1.4rem; border: 1px solid var(--linha-forte); border-radius: 1rem; transition: border-color var(--medio) var(--curva), background var(--medio) var(--curva); }
  i { position: absolute; left: 4px; top: 50%; width: calc(1.4rem - 8px); height: calc(1.4rem - 8px); border-radius: 50%; background: var(--apagado); transform: translateY(-50%);
      transition: transform var(--medio) var(--curva), background var(--medio) var(--curva); }
  .on::before { border-color: var(--acento); background: color-mix(in srgb, var(--acento) 18%, transparent); }
  .on i { transform: translate(1.35rem, -50%); background: var(--acento); }
  .on .rotulo { color: var(--papel); }
  .rotulo { min-width: 5.5rem; }
  .interruptor:focus-visible { outline: 1px solid var(--acento); outline-offset: 4px; }
  .interruptor:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
