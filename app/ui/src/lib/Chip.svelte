<script>
  // Estado pequeno: 'neutro' | 'ok' | 'revisar' | 'erro'
  let { estado = 'neutro', children } = $props()
</script>

<span class="chip {estado}"><i></i>{@render children?.()}</span>

<style>
  .chip { display: inline-flex; align-items: center; gap: var(--e2); font-family: var(--mono); font-size: var(--t-rotulo); text-transform: uppercase; letter-spacing: 0.18em; color: var(--apagado); }
  .chip { align-items: flex-start; }      /* texto em duas linhas: a bolinha fica na primeira */
  i { flex: none; width: 6px; height: 6px; margin-top: 0.42em; border-radius: 50%; background: var(--linha-forte); }
  .ok { color: var(--ok); } .ok i { background: var(--ok); }
  .revisar { color: var(--revisar); } .revisar i { background: var(--revisar); }
  .erro { color: var(--acento); } .erro i { background: var(--acento); }
</style>
