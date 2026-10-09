<script>
  // Demonstração do tribunal (#tribunal-demo): uma sequência gravada, com texto inventado, que passa por todas as poses e reações
  // sem usar nenhum modelo. Serve para conferir o desenho em cada tema e para mostrar o app.
  import Tribunal from '../lib/Tribunal.svelte'
  const FONTE = 'The lighthouse keeper counted the ships twice, and both times one was missing.'
  const PT = 'O faroleiro contou os navios duas vezes, e nas duas faltava um.'
  const q = (papel, texto, c, fase, mais = {}) => ({ v: { papel, texto, fonte: FONTE, modelo: 'modelo de demonstração', ...mais }, c, fase, estado: mais.estado ?? 'rodando' })
  const c0 = { propostos: 7, conferidos: 5, com_problema: 2, corrigidos: 1, reconferidos: 1, em_disputa: 1, causa_tradutor: 0, causa_auditor: 0, causa_usuario: 0 }
  const QUADROS = [
    q('propondo', '', c0, 'propor'),
    q('propondo', PT.slice(0, 30), c0, 'propor'),
    q('propondo', PT, { ...c0, propostos: 8 }, 'propor'),
    q('conferindo', '', { ...c0, propostos: 8 }, 'auditar'),
    q('conferindo', '{"problemas": [{"trecho": "duas vezes", "problema": "no original a contagem é dos navios, confira a ordem"}]}', { ...c0, propostos: 8, conferidos: 6, com_problema: 3 }, 'auditar', { resultado: PT }),
    q('conferindo', '{"problemas": []}', { ...c0, propostos: 8, conferidos: 7, com_problema: 3 }, 'auditar', { resultado: PT }),
    q('corrigindo', PT, { ...c0, propostos: 8, conferidos: 7, com_problema: 3, corrigidos: 2 }, 'revisar', { critica: '«duas vezes»: confira a ordem' }),
    q('conferindo', '{"problemas": [{"trecho": "faltava um", "problema": "o original diz que um navio estava ausente"}]}', { ...c0, propostos: 8, conferidos: 7, com_problema: 3, corrigidos: 2, reconferidos: 2, em_disputa: 2 }, 'reauditar', { resultado: PT }),
    q('julgando', '1: FONTE «one was missing» | VERSÃO «faltava um» | FIEL', { ...c0, propostos: 8, conferidos: 7, com_problema: 3, corrigidos: 2, reconferidos: 2, em_disputa: 2 }, 'julgar', { resultado: PT, objecoes: ['“faltava um”: o original diz que um navio estava ausente'] }),
    q('julgando', '1: FONTE «one was missing» | VERSÃO «faltava um» | FIEL', { ...c0, propostos: 8, conferidos: 7, com_problema: 3, corrigidos: 2, reconferidos: 2, em_disputa: 2, causa_tradutor: 1 }, 'julgar', { resultado: PT, objecoes: ['“faltava um”: o original diz que um navio estava ausente'] }),
    q('sentenciando', PT, { ...c0, propostos: 8, conferidos: 7, com_problema: 3, corrigidos: 2, reconferidos: 2, em_disputa: 2, causa_tradutor: 1, causa_auditor: 1 }, 'julgar', { resultado: PT }),
    q('', '', { ...c0, propostos: 8, conferidos: 7, com_problema: 3, corrigidos: 2, reconferidos: 2, em_disputa: 2, causa_tradutor: 1, causa_auditor: 1 }, 'julgar', { estado: 'pausado' }),
  ]
  let i = $state(0), anda = $state(true)
  $effect(() => { if (!anda) return; const t = setInterval(() => (i = (i + 1) % QUADROS.length), 2400); return () => clearInterval(t) })
  let a = $derived(QUADROS[i])
</script>

<h2>Tribunal · demonstração</h2>
<p class="rotulo">Quadro {i + 1} de {QUADROS.length} · texto inventado, nenhum modelo em uso ·
  <button class="elo" onclick={() => (anda = !anda)}>{anda ? 'parar' : 'andar'}</button> ·
  <button class="elo" onclick={() => { anda = false; i = (i + 1) % QUADROS.length }}>próximo</button></p>
<Tribunal v={a.v} c={a.c} modelos={{ tradutor: 'tradutor', auditor: 'auditor', juiz: 'juiz' }} fase={a.fase} estado={a.estado} tarefa="traduzir" />

<style>
  .elo { all: unset; cursor: pointer; text-decoration: underline; color: var(--papel); }
  p { margin-bottom: var(--e6); }
</style>
