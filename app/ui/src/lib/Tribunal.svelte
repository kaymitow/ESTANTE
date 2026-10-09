<script>
  // O trabalho dos modelos como um tribunal: tradutor de um lado, auditor do outro, juiz no alto. Quem fala acende.
  // v = o que está acontecendo agora (papel, modelo, fonte, resultado, texto que sai, objeções); c = contadores do livro.
  import Cena from './Cena.svelte'
  import { pose, pilhas, falaDoAuditor, eventos } from './cena.js'
  import { le } from './aparencia.js'
  let { v, c = null, modelos = {}, fase = '', estado = 'rodando', tarefa = '' } = $props()
  const PAPEL = { atualizar_pt: 'Atualizador', limpar_ocr: 'Copista' }      // o "tradutor" tem outro nome quando a tarefa não é traduzir
  const modo = le().tribunal      // 'personagens' (a cena desenhada) ou 'quadros' (só as caixas)
  // o que mudou nos contadores desde a última consulta vira a folha que voa na cena
  let antes = null, ev = $state([])
  $effect(() => { const agora = c ? { ...c } : null, e = eventos(antes, agora); antes = agora; if (e.length) ev = e })
  let fala = $derived(v.papel === 'conferindo' ? falaDoAuditor(v.texto) : null)

  const limpo = (t) => (t ?? '').replace(/<\/?[aib]\d+>|<n\d+\/>/g, '').replace(/\s*<br>\s*/g, '\n')
  const VEZ = { propondo: 'tradutor', corrigindo: 'tradutor', conferindo: 'auditor', julgando: 'juiz', sentenciando: 'juiz' }
  const ATO = { propondo: 'Tradutor escrevendo', corrigindo: 'Tradutor corrigindo o que foi apontado', conferindo: 'Auditor conferindo a fidelidade',
                julgando: 'Juiz ouvindo as duas partes', sentenciando: 'Juiz escrevendo a sentença' }
  let vez = $derived(VEZ[v.papel] ?? 'tradutor')
  // cada linha do voto do juiz: "1: FONTE «…» | VERSÃO «…» | FIEL" ou "… | ERRO — motivo"
  let votos = $derived(v.papel === 'julgando' ? (v.texto ?? '').split('\n').map((l) => /\b(FIEL|ERRO)\b/.exec(l)?.[1]).filter(Boolean) : [])
  const curta = (o) => o.replace(/^“(.+?)”:.*$/s, '«$1»').slice(0, 140)
</script>

<div class="tribunal" data-vez={vez} data-modo={modo}>
  <div class="ato rotulo" aria-live="polite"><span class="pulso" aria-hidden="true"></span>{ATO[v.papel] ?? v.papel}</div>
  {#if modo === 'personagens'}<div class="palco"><Cena {ev} p={pose(v, fase, estado)} pl={pilhas(c ?? {}, !!modelos.juiz || fase === 'julgar')}
    nomes={{ tradutor: modelos.tradutor, auditor: modelos.auditor, juiz: fase === 'julgar' ? (v.modelo ?? modelos.juiz) : '', papelTradutor: PAPEL[tarefa] }} /></div>{/if}

  <div class="lugar juiz" class:fala={vez === 'juiz'}>
    <div class="quem">
      <svg class="icone" class:bate={v.papel === 'julgando'} viewBox="0 0 32 32" aria-hidden="true"><path d="M6 27h14M13 27v-3M18.5 4.5l7 7M15 8l7 7M16.7 6.3l-7.4 7.4 5 5 7.4-7.4M11.8 16.2 4 24" /></svg>
      <div class="placa"><div class="nome">Juiz</div><div class="rotulo">{vez === 'juiz' ? v.modelo : (modelos.juiz ?? 'entra só nas disputas')}</div></div>
      {#if c && (c.causa_tradutor || c.causa_auditor || c.causa_usuario)}
        <div class="placar rotulo"><span>{c.causa_tradutor} do tradutor</span><span>{c.causa_auditor} do auditor</span><span class:alerta={c.causa_usuario}>{c.causa_usuario} para você</span></div>
      {/if}
    </div>
    {#if v.papel === 'julgando'}
      <div class="balao">
        {#if v.objecoes?.length}
          <ol class="itens">{#each v.objecoes as o, i}<li class:fiel={votos[i] === 'FIEL'} class:erro={votos[i] === 'ERRO'}>
            <span class="trecho">{curta(limpo(o))}</span>
            <span class="voto rotulo">{votos[i] === 'FIEL' ? 'não procede' : votos[i] === 'ERRO' ? 'procede' : i === votos.length ? 'julgando…' : ''}</span></li>{/each}</ol>
        {:else}<p class="leitura">{v.texto}<span class="cursor" aria-hidden="true"></span></p>{/if}
      </div>
    {:else if v.papel === 'sentenciando'}
      <div class="balao"><div class="rotulo">Sentença · versão corrigida</div><p class="leitura">{limpo(v.texto)}<span class="cursor" aria-hidden="true"></span></p></div>
    {/if}
  </div>

  <div class="fonte"><div class="rotulo">Em pauta · o texto do autor</div><p class="leitura">{limpo(v.fonte)}</p></div>

  <div class="partes">
    <div class="lugar tradutor" class:fala={vez === 'tradutor'}>
      <div class="quem">
        <svg class="icone" viewBox="0 0 32 32" aria-hidden="true"><path d="M5 27l2-7L21 6l5 5-14 14-7 2zM18 9l5 5M7 20l5 5" /></svg>
        <div class="placa"><div class="nome">{PAPEL[tarefa] ?? 'Tradutor'}</div><div class="rotulo">{vez === 'tradutor' ? v.modelo : (modelos.tradutor ?? '')}</div></div>
      </div>
      {#if vez === 'tradutor'}
        <div class="balao"><p class="leitura">{limpo(v.texto)}<span class="cursor" aria-hidden="true"></span></p></div>
      {:else if v.resultado}
        <div class="balao quieto"><div class="rotulo">Versão em disputa</div><p class="leitura">{limpo(v.resultado)}</p></div>
      {/if}
    </div>

    <div class="lugar auditor" class:fala={vez === 'auditor'}>
      <div class="quem">
        <svg class="icone" viewBox="0 0 32 32" aria-hidden="true"><circle cx="14" cy="14" r="8" /><path d="M20 20l7 7M10.5 14l2.5 2.5 4.5-5" /></svg>
        <div class="placa"><div class="nome">Auditor</div><div class="rotulo">{vez === 'auditor' ? v.modelo : (modelos.auditor ?? '')}</div></div>
      </div>
      {#if vez === 'auditor'}
        <div class="balao">
          {#if Array.isArray(fala)}<ol class="itens pares">{#each fala as f}<li><span class="trecho">«{f.trecho}»</span><span class="problema">{f.problema}</span></li>{/each}</ol>
          {:else}<p class="parecer">{fala === 'fiel' ? 'Fiel: nada a apontar.' : 'Lendo e comparando com o original'}<span class="cursor" aria-hidden="true"></span></p>{/if}
        </div>
      {:else if v.papel === 'corrigindo' && v.critica}
        <div class="balao quieto"><div class="rotulo">Apontou</div><p class="parecer">{limpo(v.critica).slice(0, 600)}</p></div>
      {:else if vez === 'juiz' && v.objecoes?.length}
        <div class="balao quieto"><div class="rotulo">{v.objecoes.length} {v.objecoes.length === 1 ? 'objeção' : 'objeções'} em julgamento</div></div>
      {/if}
    </div>
  </div>
</div>

<style>
  .tribunal { display: grid; gap: var(--e6); }
  .ato { display: flex; align-items: center; gap: var(--e3); color: var(--papel); }
  .pulso { width: 8px; height: 8px; border-radius: 50%; background: var(--acento); animation: pulsa 1.4s ease-in-out infinite; box-shadow: 0 0 0 4px color-mix(in srgb, var(--acento) 25%, transparent); }
  .partes { display: grid; grid-template-columns: 1fr 1fr; gap: var(--e6); align-items: start; }
  .lugar { display: grid; gap: var(--e3); padding: var(--e4); border: 1px solid var(--linha); border-radius: var(--raio); min-width: 0; opacity: 0.55;
           transition: opacity var(--medio, 300ms), border-color var(--medio, 300ms), box-shadow var(--medio, 300ms); }
  .lugar.fala { opacity: 1; border-color: var(--acento); box-shadow: 0 0 0 1px var(--acento), 0 0 2.5rem -0.75rem color-mix(in srgb, var(--acento) 60%, transparent); }
  .juiz { justify-self: center; width: min(100%, 44rem); }
  .quem { display: flex; align-items: center; gap: var(--e3); flex-wrap: wrap; }
  .nome { font-family: var(--display, inherit); font-size: 1.125rem; letter-spacing: 0.06em; text-transform: var(--caixa-titulos); color: var(--papel); }
  .icone { width: 2rem; height: 2rem; flex: none; fill: none; stroke: var(--apagado); stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; transition: stroke var(--medio, 300ms); }
  .fala .icone { stroke: var(--acento); }
  .icone.bate { transform-origin: 30% 80%; animation: martelo 1.6s ease-in-out infinite; }
  .placar { margin-left: auto; display: flex; gap: var(--e4); flex-wrap: wrap; }
  .alerta { color: var(--revisar); }
  .balao .leitura, .balao .parecer { max-height: 15rem; overflow-y: auto; }
  .balao { display: grid; gap: var(--e2); padding: var(--e3) var(--e4); background: var(--superficie); border-radius: var(--raio); position: relative; min-width: 0; }
  .balao::before { content: ''; position: absolute; top: -6px; left: 1.4rem; width: 12px; height: 12px; background: var(--superficie); transform: rotate(45deg); }
  .balao.quieto { background: transparent; border: 1px dashed var(--linha); } .balao.quieto::before { display: none; }
  .leitura { max-height: 14rem; overflow-y: auto; white-space: pre-wrap; margin: 0; }
  .fonte { display: grid; gap: var(--e2); justify-self: center; width: min(100%, 44rem); text-align: left; }
  .fonte .leitura { color: var(--apagado); max-height: 9rem; }
  .parecer { font-family: var(--mono); font-size: 0.8125rem; color: var(--apagado); white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; max-height: 14rem; overflow-y: auto; }
  .itens { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--e2); }
  .itens li { display: flex; gap: var(--e3); justify-content: space-between; align-items: baseline; padding-left: var(--e3); border-left: 2px solid var(--linha-forte); }
  .itens .trecho { font-family: var(--mono); font-size: 0.8125rem; color: var(--apagado); overflow-wrap: anywhere; min-width: 0; }
  .itens .voto { flex: none; color: var(--papel); }
  /* parecer do auditor: trecho em cima, problema embaixo, em texto corrido; a caixa tem altura máxima e rola por dentro */
  .pares { max-height: 15rem; overflow-y: auto; }
  .pares li { display: grid; gap: 2px; justify-content: stretch; }
  .pares .problema { font-size: 0.875rem; color: var(--papel); overflow-wrap: anywhere; }
  .itens li.fiel { border-color: var(--ok); } .itens li.fiel .voto { color: var(--ok); }
  .itens li.erro { border-color: var(--revisar); } .itens li.erro .voto { color: var(--revisar); }
  .itens li.fiel, .itens li.erro { animation: carimbo 320ms var(--curva, ease-out) both; }
  .cursor { display: inline-block; width: 0.5em; height: 1em; margin-left: 2px; background: var(--acento); vertical-align: text-bottom; animation: pisca 1s steps(2) infinite; }
  @keyframes pisca { 50% { opacity: 0; } }
  @keyframes pulsa { 50% { opacity: 0.35; } }
  @keyframes martelo { 0%, 60%, 100% { transform: rotate(0); } 75% { transform: rotate(-22deg); } 85% { transform: rotate(6deg); } }
  @keyframes carimbo { from { transform: scale(1.04); opacity: 0.4; } to { transform: none; opacity: 1; } }
  @media (max-width: 900px) { .partes { grid-template-columns: 1fr; } }
  @media (prefers-reduced-motion: reduce) { .cursor, .pulso, .icone.bate, .itens li { animation: none; } .lugar { transition: none; } }
  .palco { padding: var(--e4) 0; }
  @container (max-width: 560px) { .palco { display: none; } }
  @media (max-width: 560px) { .palco { display: none; } }
  /* com a cena, as placas e os ícones das caixas saem: quem é quem já está desenhado. Em tela estreita a cena some e as caixas voltam inteiras */
  @media (min-width: 561px) {
    [data-modo='personagens'] .icone, [data-modo='personagens'] .placa { display: none; }
    [data-modo='personagens'] .quem:not(:has(.placar)) { display: none; }
    [data-modo='personagens'] .lugar, [data-modo='personagens'] .lugar.fala { border: 0; padding: 0; opacity: 1; box-shadow: none; }
    [data-modo='personagens'] .placar { margin: 0 auto; }
  }
</style>
