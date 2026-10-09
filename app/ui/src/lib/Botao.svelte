<script>
  // Botão de contorno (Santioni). variante: 'contorno' | 'cheio' | 'texto'
  let { variante = 'contorno', disabled = false, onclick, children } = $props()
</script>

<button class={variante} {disabled} {onclick}>
  <span>{@render children?.()}</span>
</button>

<style>
  button {
    position: relative; cursor: pointer; background: transparent; border: 1px solid var(--papel); border-radius: var(--raio);
    padding: var(--e3) var(--e6); font-family: var(--mono); font-size: var(--t-rotulo); text-transform: uppercase; letter-spacing: 0.22em;
    overflow: hidden; transition: color var(--medio) var(--curva), border-color var(--medio) var(--curva);
  }
  /* preenchimento que sobe ao passar o mouse */
  button::before {
    content: ''; position: absolute; inset: 0; background: var(--papel); transform: translateY(101%);
    transition: transform var(--medio) var(--curva);
  }
  span { position: relative; }
  button:hover:not(:disabled) { color: var(--fundo); }
  button:hover:not(:disabled)::before { transform: none; }
  button:active:not(:disabled) { transform: scale(0.985); }
  .cheio { background: var(--acento); border-color: var(--acento); color: var(--sobre-acento); }
  .cheio::before { background: var(--papel); }
  .texto { border-color: transparent; padding-inline: 0; color: var(--apagado); }
  .texto::before { display: none; }
  .texto:hover:not(:disabled) { color: var(--papel); }
  button:disabled { opacity: 0.35; cursor: not-allowed; }
</style>
