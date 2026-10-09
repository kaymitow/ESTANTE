<script>
  // Gera os arquivos do livro (PDF, EPUB…) a partir do texto aprovado e lista o que já foi gerado.
  import Botao from './Botao.svelte'
  import Chip from './Chip.svelte'
  import Progresso from './Progresso.svelte'
  import { api } from './api.js'

  let { id } = $props()
  let arquivos = $state([])
  let rodando = $state('')       // ação em andamento
  let log = $state([])
  let erro = $state('')
  let resultado = $state(null)   // 'ok' | 'falhou'

  const ACOES = [['pdf', 'PDF'], ['epub', 'EPUB'], ['docx', 'Word'], ['odt', 'ODT'], ['html', 'HTML'], ['fb2', 'FB2'], ['bilingue', 'Bilíngue (EPUB, HTML, Word)'], ['verificar', 'Conferir PDF e EPUB']]
  const lista = async () => { try { arquivos = await api(`/api/livro/${id}/saida`) } catch { arquivos = [] } }
  $effect(() => { lista() })

  async function faz(acao) {
    rodando = acao; log = []; erro = ''; resultado = null
    try {
      const { id: jid } = await api('/api/tarefa', 'POST', { livro: id, acao })
      for (;;) {
        await new Promise((r) => setTimeout(r, 800))
        const e = await api(`/api/tarefa/${jid}?desde=${log.length}`)
        log = [...log, ...e.log]
        if (!e.rodando) { resultado = e.codigo === 0 ? 'ok' : 'falhou'; break }
      }
    } catch (e) { erro = e.message } finally { rodando = ''; lista() }
  }
  const quando = (t) => new Date(t * 1000).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  // prova de fidelidade: gera saida/prova.json e prova.html (aparecem na lista abaixo)
  let prova = $state(null), provando = $state(false)
  async function gerarProva() {
    provando = true; erro = ''
    try { prova = (await api(`/api/livro/${id}/prova`)).totais; lista() }
    catch (e) { erro = e.message } finally { provando = false }
  }
</script>

<div class="acoes">
  {#each ACOES as [acao, nome]}
    <Botao disabled={!!rodando} onclick={() => faz(acao)}>{rodando === acao ? 'Gerando…' : nome}</Botao>
  {/each}
  <Botao disabled={provando} onclick={gerarProva}>{provando ? 'Provando…' : 'Prova de fidelidade'}</Botao>
</div>
{#if prova}
  <p class="rotulo">{prova.aceitos} aceitos de {prova.blocos_rascunho} blocos · {prova.sem_registro} sem registro · {prova.fecha ? 'os totais fecham' : 'os totais NÃO fecham: veja a prova'}</p>
{/if}
{#if rodando}<div class="barra"><Progresso rotulo={log.at(-1)?.slice(0, 90) || 'trabalhando'} /></div>{/if}
{#if erro}<Chip estado="erro">{erro}</Chip>{/if}
{#if resultado === 'falhou'}<Chip estado="erro">Não deu certo. Veja o registro abaixo.</Chip>{/if}
{#if resultado === 'ok'}<Chip estado="ok">Pronto</Chip>{/if}
{#if log.length && (resultado === 'falhou' || log.some((l) => /parágrafos|EPUBCheck|OK|sem:/.test(l)))}
  <pre class="log">{log.filter((l) => !/MiKTeX updates/.test(l)).slice(-14).join('\n')}</pre>
{/if}

{#if arquivos.length}
  <ul class="arquivos">
    {#each arquivos as a}
      <li><a href="/api/livro/{id}/saida/{encodeURIComponent(a.arquivo)}" target="_blank" rel="noopener">{a.arquivo}</a>
        <span class="rotulo">{a.kb > 1024 ? (a.kb / 1024).toFixed(1) + ' MB' : a.kb + ' KB'} · {quando(a.quando)}</span></li>
    {/each}
  </ul>
{:else}
  <p class="rotulo">Nenhum arquivo gerado ainda.</p>
{/if}

<style>
  .acoes { display: flex; flex-wrap: wrap; gap: var(--e3); }
  .barra { max-width: 34rem; }
  .log { margin: 0; padding: var(--e3) var(--e4); background: var(--superficie); border-left: 2px solid var(--linha-forte); font-family: var(--mono); font-size: 0.75rem; color: var(--apagado); white-space: pre-wrap; overflow-wrap: anywhere; max-height: 16rem; overflow: auto; }
  .arquivos { list-style: none; margin: 0; padding: 0; }
  .arquivos li { display: flex; flex-wrap: wrap; gap: var(--e2) var(--e6); justify-content: space-between; align-items: baseline; padding: var(--e3) 0; border-top: 1px solid var(--linha); }
  .arquivos a { font-family: var(--mono); font-size: 0.875rem; text-decoration: none; overflow-wrap: anywhere; }
  .arquivos a:hover { color: var(--acento); }
</style>
