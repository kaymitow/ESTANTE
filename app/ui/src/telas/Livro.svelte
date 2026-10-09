<script>
  import Chip from '../lib/Chip.svelte'
  import Tribunal from '../lib/Tribunal.svelte'
  import LivroVivo from '../lib/LivroVivo.svelte'
  import Botao from '../lib/Botao.svelte'
  import Progresso from '../lib/Progresso.svelte'
  import Gerar from '../lib/Gerar.svelte'
  import { api } from '../lib/api.js'

  let { id } = $props()
  let st = $state(null)        // estado do pipeline; null = carregando
  let info = $state(null)      // título e autor
  let erro = $state('')
  let ocupado = $state(false)
  let tarefa = $state('')
  let rapido = $state(false)      // rascunho rápido: motor clássico, sem IA grande
  let de = $state(''), ate = $state('')

  const ETAPAS = [
    { id: 'diagnostico', nome: 'Diagnóstico', o: 'Conta as páginas e descobre se o PDF tem texto ou é imagem.' },
    { id: 'inventario', nome: 'Inventário', o: 'Tabela de páginas do arquivo.' },
    { id: 'extracao', nome: 'Extração', o: 'Lê o texto. Em scan, dois modelos leem cada página sem ver a leitura um do outro.' },
    { id: 'estrutura', nome: 'Estrutura', o: 'Tira cabeçalhos e numeração, une parágrafos entre páginas, marca títulos.' },
    { id: 'transformacao', nome: 'Transformação', o: 'Um modelo propõe, outro audita a fidelidade, o primeiro corrige.' },
    { id: 'rascunho', nome: 'Rascunho', o: 'Junta tudo por bloco, com o que os modelos aprovaram e o que ficou em dúvida.' },
  ]
  const TAREFAS = { traduzir: 'Traduzir do inglês', traduzir_de: 'Traduzir do alemão', atualizar_pt: 'Atualizar português antigo', limpar_ocr: 'Só limpar a leitura', nenhuma: 'Só extrair o texto' }

  async function pega(u, opts) {
    const r = await fetch(u, opts)
    const j = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(j.detail || r.statusText)
    return j
  }
  async function carrega() {
    try { st = await pega(`/api/pipeline/${id}`); if (!tarefa) tarefa = st.config?.tarefa || 'nenhuma'; erro = '' }
    catch (e) { erro = e.message; st = st ?? {} }
  }
  async function manda(acao, mais = {}) {
    ocupado = true
    try {
      const corpo = acao === 'iniciar' ? { tarefa, paginas: de && ate ? [+de, +ate] : null, rapido: rapido && tarefa === 'traduzir' ? true : null, ...mais } : {}
      st = await pega(`/api/pipeline/${id}/${acao}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) })
      erro = ''
    } catch (e) { erro = e.message } finally { ocupado = false }
  }

  $effect(() => {
    carrega()
    pega('/api/livros').then((l) => (info = l.find((x) => x.id === id) ?? null)).catch(() => {})
    pega(`/api/livro/${id}/estilo`).then((e) => (estilo = e)).catch(() => {})
    pega('/api/config').then((c) => (rede = c.rede)).catch(() => {})
    const t = setInterval(() => { if (st?.estado === 'rodando' && !document.hidden) carrega() }, 700)
    return () => clearInterval(t)
  })

  const situacao = (e) => st.feitas?.includes(e) ? 'feita' : st.etapa === e ? (st.estado === 'erro' ? 'erro' : st.estado === 'pausado' ? 'pausada' : 'agora') : 'espera'
  let comecou = $derived(!!st?.feitas?.length || st?.estado === 'rodando')
  let r = $derived(st?.rascunho)
  const PASSOS = [...ETAPAS, { id: 'revisao', nome: 'Pontos para olhar', o: 'Opcional. O livro já sai do rascunho inteiro. Aqui ficam os trechos que o app não tem certeza, para você conferir se quiser.' }]
  const sit = (e) => (e === 'revisao' ? (r ? 'opcional' : 'espera') : situacao(e))
  let foco = $state(null)      // passo que o usuário clicou para ler; sem clique, mostra o que está acontecendo
  // partes para uma IA grande: o app só copia ou salva o texto; quem envia para a IA é a pessoa, por conta própria
  let msgPartes = $state('')
  async function copiarPartes() {
    try {
      const { texto, n } = await api(`/api/livro/${id}/partes`)
      try { await navigator.clipboard.writeText(texto); msgPartes = `${n} trecho(s) copiados. Cole numa IA grande.` }
      catch { msgPartes = 'Não deu para copiar daqui: use Salvar arquivo.' }
    } catch (e) { msgPartes = e.message }
  }
  async function salvarPartes() {
    try { const r = await api(`/api/livro/${id}/partes/salvar`, 'POST'); msgPartes = `Salvo em saida/${r.arquivo} (${r.n} trecho(s)).` }
    catch (e) { msgPartes = e.message }
  }
  let visto = $derived(foco ?? (st?.estado === 'concluido' || r ? 'revisao' : st?.etapa ?? PASSOS.find((e) => !st?.feitas?.includes(e.id))?.id ?? 'diagnostico'))
  let dlgApagar = $state()
  async function apaga() {
    ocupado = true
    try { const x = await fetch(`/api/livro/${id}`, { method: 'DELETE' }); const j = await x.json(); if (!x.ok) throw new Error(j.detail || x.statusText); location.hash = 'biblioteca' }
    catch (e) { erro = e.message; dlgApagar.close() } finally { ocupado = false }
  }
  let estilo = $state(null)
  let rede = $state(null)
  // comparar com outra cópia do mesmo livro: só mostra as diferenças, nunca escreve no texto
  let copias = $state([])
  let comparando = $state(false)
  let erroCopia = $state('')
  $effect(() => { pega(`/api/copias/${id}`).then((c) => (copias = c)).catch(() => {}) })
  async function compara(e) {
    const arq = e.currentTarget.files?.[0]
    if (!arq) return
    comparando = true; erroCopia = ''
    try {
      const x = await fetch(`/api/copias/${id}?arquivo=${encodeURIComponent(arq.name)}`, { method: 'POST', body: arq })
      const j = await x.json(); if (!x.ok) throw new Error(j.detail || x.statusText)
      copias = [j, ...copias.filter((c) => c.arquivo !== j.arquivo)]
    } catch (ex) { erroCopia = ex.message } finally { comparando = false; e.currentTarget.value = '' }
  }
  // capa e fontes do livro gerado, trocadas aqui mesmo
  let erroEstilo = $state('')
  let vezCapa = $state(0)
  async function pedeEstilo(url, opcoes) {
    erroEstilo = ''
    try { const x = await fetch(url, opcoes); const j = await x.json(); if (!x.ok) throw new Error(j.detail || x.statusText); estilo = j; vezCapa++ }
    catch (ex) { erroEstilo = ex.message }
  }
  function mandaEstilo(tipo, e, alvo = '') {
    const arq = e.currentTarget.files?.[0]; e.currentTarget.value = ''
    if (arq) pedeEstilo(`/api/livro/${id}/estilo/${tipo}` + (tipo === 'fonte' ? `?alvo=${alvo}&arquivo=${encodeURIComponent(arq.name)}` : ''), { method: 'POST', body: arq })
  }
  const tiraEstilo = (alvo) => pedeEstilo(`/api/livro/${id}/estilo/${alvo}`, { method: 'DELETE' })
  let edicoes = $state(null)      // null = não buscou; {achados, sem_resposta} | {erro}
  async function buscaEdicoes() {
    edicoes = { carregando: true }
    // a busca usa o título com que o livro foi importado: com o título em português os acervos não achariam nada
    try { edicoes = await pega(`/api/rede/edicoes?titulo=${encodeURIComponent(info.titulo_original ?? info.titulo)}&autor=${encodeURIComponent(info.autor)}`) } catch (e) { edicoes = { erro: e.message } }
  }
  // baixa uma das edições achadas e compara com a fonte (o arquivo fica em fonte/outras-copias; nada é escrito no texto)
  async function comparaEdicao(e) {
    e.comparando = true; e.erro = ''
    try {
      let url = e.link + '.epub3.images'                        // Project Gutenberg
      if (e.acervo === 'Internet Archive') {
        const arqs = await pega('/api/rede/arquivos?id=' + encodeURIComponent(e.link.split('/').pop()))
        const a = arqs.find((x) => x.formato === 'EPUB') ?? arqs[0]
        if (!a) throw new Error('esta edição não tem arquivo aberto (EPUB ou PDF com texto)')
        url = a.url
      }
      const j = await pega(`/api/copias/${id}/baixar`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, nome: [e.titulo, e.ano].filter(Boolean).join(' ').slice(0, 80) }) })
      copias = [j, ...copias.filter((c) => c.arquivo !== j.arquivo)]; e.comparada = true
    } catch (ex) { e.erro = ex.message } finally { e.comparando = false }
  }
  // título em português: o tradutor sugere, você decide; o original fica guardado
  let dlgTitulo = $state()
  let tituloNovo = $state('')
  let sugerindo = $state(false)
  let erroTitulo = $state('')
  async function abreTitulo() {
    tituloNovo = info.titulo_original ? info.titulo : ''; erroTitulo = ''; dlgTitulo.showModal()
    if (tituloNovo) return
    sugerindo = true
    try { const s = await pega(`/api/livro/${id}/titulo`); if (!tituloNovo.trim()) tituloNovo = s.sugestao } catch (e) { erroTitulo = e.message } finally { sugerindo = false }
  }
  async function gravaTitulo(valor) {
    try {
      const r = await pega(`/api/livro/${id}/titulo`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ titulo: valor }) })
      info = { ...info, titulo: r.titulo, titulo_original: r.titulo_original }; dlgTitulo.close()
    } catch (e) { erroTitulo = e.message }
  }
  let v = $derived(st?.estado === 'rodando' ? st.ao_vivo : null)
  // como acompanhar o trabalho: a cena do tribunal ou o livro aberto (original e tradução, página a página). A escolha fica neste navegador
  let modoVivo = $state(location.hash.endsWith('/aberto') ? 'livro' : (() => { try { return localStorage.getItem('estante.vivo') } catch { return null } })() ?? 'tribunal')
  const escolheVivo = (m) => { modoVivo = m; try { localStorage.setItem('estante.vivo', m) } catch { /* sem armazenamento: vale só agora */ } }
  let folhear = $state(location.hash.endsWith('/aberto'))      // #livro/<id>/aberto já chega com o livro aberto
  let c = $derived(st?.fila?.conta)
  // as marcas que protegem links e notas (<a1>…</a1>, <n2/>) não interessam a quem acompanha: some com elas na tela
  const limpo = (t) => (t ?? '').replace(/<\/?a\d+>|<n\d+\/>/g, '').replace(/\s*<br>\s*/g, '\n')
  const PAPEL = { propondo: 'escrevendo', corrigindo: 'corrigindo', conferindo: 'conferindo a fidelidade', lendo: 'lendo a página' }
  const tempo = (s) => s >= 3600 ? `${Math.floor(s / 3600)} h ${String(Math.round((s % 3600) / 60)).padStart(2, '0')} min` : s >= 60 ? `${Math.round(s / 60)} min` : `${Math.round(s)} s`
  // estimativa do que falta na transformação, pelo ritmo até aqui
  let falta = $derived(st?.fila && st.fila.progresso > 0.03 && st.fila.progresso < 1 ? st.fila.segundos * (1 - st.fila.progresso) / st.fila.progresso : null)
</script>

<header class="topo" class:com-capa={estilo?.capa} style:--capa={estilo?.capa ? `url(/api/livro/${id}/capa)` : null}>
  <a class="rotulo volta" href="#biblioteca">← Biblioteca</a>
  {#if estilo?.capa}<img class="capa" src="/api/livro/{id}/capa" alt="Capa de {info?.titulo ?? id}" />{/if}
  <div class="ident">
    <h2>{info?.titulo ?? id}</h2>
    <p class="autor">{info?.autor ?? ''}</p>
    {#if info && st?.config?.tarefa?.startsWith('traduzir')}
      <p class="rotulo">{#if info.titulo_original}Original · {info.titulo_original} · {/if}<button class="elo liso" onclick={abreTitulo}>{info.titulo_original ? 'Trocar o título' : 'Dar um título em português'}</button></p>
    {/if}
    {#if r}
      <dl class="numeros">
        <div><dd>{r.total}</dd><dt class="rotulo">blocos</dt></div>
        <div class:bom={r.aceitos > 0}><dd>{r.aceitos}</dd><dt class="rotulo">no livro</dt></div>
        <div class:alerta={r.revisar}><dd>{r.revisar}</dd><dt class="rotulo">pedem atenção</dt></div>
        {#if r.juiz}<div class="alerta"><dd>{r.juiz}</dd><dt class="rotulo">do juiz, a conferir</dt></div>{/if}
      </dl>
    {:else if info?.paragrafos}<dl class="numeros"><div><dd>{info.paragrafos}</dd><dt class="rotulo">blocos no livro</dt></div></dl>{/if}
  </div>
</header>

<dialog bind:this={dlgTitulo} aria-labelledby="t-titulo">
  <div class="rotulo">Título do livro gerado</div>
  <h3 id="t-titulo">Título em português</h3>
  <p class="o">Aparece na folha de rosto, no cabeçalho das páginas e na estante. O título original ({info?.titulo_original ?? info?.titulo}) fica guardado e continua valendo para procurar outras edições.</p>
  <label><span class="rotulo">{sugerindo ? 'O tradutor está sugerindo · você pode escrever sem esperar' : 'Título'}</span>
    <input class="largo" bind:value={tituloNovo} aria-label="Título em português" /></label>
  {#if erroTitulo}<Chip estado="erro">{erroTitulo}</Chip>{/if}
  <div class="botoes">
    {#if info?.titulo_original}<Botao variante="texto" onclick={() => gravaTitulo(info.titulo_original)}>Voltar ao original</Botao>{/if}
    <Botao variante="texto" onclick={() => dlgTitulo.close()}>Cancelar</Botao>
    <Botao variante="cheio" disabled={!tituloNovo.trim()} onclick={() => gravaTitulo(tituloNovo)}>Usar este título</Botao>
  </div>
</dialog>

<dialog bind:this={dlgApagar} aria-labelledby="t-apagar">
  <div class="rotulo">Tirar da estante</div>
  <h3 id="t-apagar">Apagar {info?.titulo ?? id}?</h3>
  <p class="o">O livro sai da estante com tudo: arquivo de origem, traduções e revisão. A pasta não é destruída: vai para <code>livros/.lixeira</code>, de onde dá para trazer de volta à mão.</p>
  <div class="botoes"><Botao variante="texto" onclick={() => dlgApagar.close()}>Cancelar</Botao><Botao variante="cheio" disabled={ocupado} onclick={apaga}>Apagar o livro</Botao></div>
</dialog>

{#if st === null}
  <Progresso rotulo="Abrindo" />
{:else if st.impedimento}
  <section class="aviso">
    <Chip estado="ok">Texto aprovado · {info?.paragrafos ?? '—'} blocos</Chip>
    <p class="leitura">Este livro foi preparado antes do processamento automático. O texto aprovado dele não é tocado pelo processamento.</p>
  </section>
{:else}
  <section class="painel">
    <div class="estado">
      {#if st.estado === 'rodando'}<Chip estado="revisar">Processando</Chip>
      {:else if st.estado === 'pausado'}<Chip>Pausado</Chip>
      {:else if st.estado === 'erro'}<Chip estado="erro">Parou com erro</Chip>
      {:else if st.estado === 'concluido'}<Chip estado="ok">Pronto para revisar</Chip>
      {:else}<Chip>Importado · ainda não processado</Chip>{/if}
      {#if st.mensagem}<p class="msg" aria-live="polite">{st.mensagem}</p>{/if}
      {#if st.aviso}<p class="msg">{st.aviso}</p>{/if}
      {#if erro}<Chip estado="erro">{erro}</Chip>{/if}
    </div>

    {#if !comecou}
      <div class="config">
        <label><span class="rotulo">O que fazer com o texto</span>
          <select bind:value={tarefa}>{#each Object.entries(TAREFAS) as [k, v]}<option value={k}>{v}</option>{/each}</select></label>
        <label><span class="rotulo">Só um trecho (opcional)</span>
          <span class="faixa"><input type="number" min="1" placeholder="da página" aria-label="Da página" bind:value={de} /><input type="number" min="1" placeholder="até" aria-label="Até a página" bind:value={ate} /></span></label>
        {#if tarefa === 'traduzir'}
          <label class="rapido"><input type="checkbox" bind:checked={rapido} /> <span>Rascunho rápido, sem IA grande
            <span class="rotulo">minutos em vez de horas, no processador. A tradução é mais fraca (erra expressões e perde o itálico) e não passa por auditor nem juiz: serve para ler logo ou para computador sem placa.</span></span></label>
        {/if}
      </div>
    {/if}

    <div class="botoes">
      {#if st.estado === 'rodando'}<Botao disabled={ocupado} onclick={() => manda('pausar')}>Pausar</Botao>
      {:else if st.pergunta === 'camada' && st.estado === 'pausado'}
        <Botao variante="cheio" disabled={ocupado} onclick={() => manda('iniciar', { ler_por_imagem: true })}>Reler pelas imagens</Botao>
        <Botao disabled={ocupado} onclick={() => manda('iniciar', { ler_por_imagem: false })}>Usar o texto do arquivo</Botao>
      {:else if st.estado !== 'concluido'}<Botao variante="cheio" disabled={ocupado} onclick={() => manda('iniciar')}>{comecou ? 'Continuar' : 'Processar o livro'}</Botao>{/if}
      {#if r}<a class="abrir" href="#revisao/{id}">Abrir a revisão →</a>{/if}
    </div>
    {#if !comecou}<p class="rotulo nota">O livro inteiro é processado sozinho. Nada vira texto aprovado sem o seu aceite.</p>{/if}
  </section>

  {#if v}
    <section class="vivo" aria-label="Acontecendo agora">
      <div class="vivo-cab">
        <span class="pulso" aria-hidden="true"></span>
        <span class="rotulo claro">{v.papel === 'lendo' ? `${v.modelo} · lendo a página` : 'Sessão em andamento'}</span>
        {#if c}
          <span class="rotulo">{c.propostos}/{st.fila.total} escritos</span>
          <span class="rotulo">{c.conferidos} conferidos</span>
          <span class="rotulo" class:alerta={c.com_problema}>{c.com_problema} com ressalva</span>
          {#if c.causa_tradutor + c.causa_auditor + c.causa_usuario}<span class="rotulo">{c.causa_tradutor + c.causa_auditor + c.causa_usuario} julgados</span>{/if}
        {/if}
        {#if st.fila?.segundos}<span class="rotulo">{tempo(st.fila.segundos)} de trabalho{falta ? ` · faltam cerca de ${tempo(falta)}` : ''}</span>{/if}
      </div>
      {#if v.papel === 'lendo'}
        <div class="vivo-lados">
          <div>
            <div class="rotulo">{v.papel === 'lendo' ? `Página ${v.pagina}` : 'Fonte'}</div>
            {#if v.papel === 'lendo'}<img src="/api/livro/{id}/pagina/{v.pagina}" alt="Página {v.pagina} sendo lida" />
            {:else}<p class="leitura fonte">{limpo(v.fonte)}</p>{/if}
          </div>
          <div>
            <div class="rotulo">{v.papel === 'conferindo' ? 'Tradução em conferência' : 'Saindo agora'}</div>
            {#if v.papel === 'conferindo'}
              <p class="leitura">{limpo(v.resultado)}</p>
              <p class="parecer"><span class="rotulo">Auditor</span> {v.texto}<span class="cursor" aria-hidden="true"></span></p>
            {:else}
              <p class="leitura">{limpo(v.texto)}<span class="cursor" aria-hidden="true"></span></p>
            {/if}
          </div>
        </div>
      {:else}
        <div class="segmento modo-vivo" role="group" aria-label="Como acompanhar o trabalho">{#each [['tribunal', 'Tribunal'], ['livro', 'Livro']] as [m, n]}<button class:on={modoVivo === m} aria-pressed={modoVivo === m} onclick={() => escolheVivo(m)}>{n}</button>{/each}</div>
        {#if modoVivo === 'livro'}<LivroVivo {id} {v} />{:else}
        <Tribunal {v} {c} modelos={{ tradutor: st.fila?.a, auditor: st.fila?.b }} fase={st.fila?.fase} estado={st.estado} tarefa={st.fila?.tarefa} />{/if}
      {/if}
    </section>
  {/if}

  <ol class="passos">
    {#each PASSOS as e, i}
      {@const s = sit(e.id)}
      <li class={s} class:sel={visto === e.id}>
        <button onclick={() => (foco = e.id)} aria-pressed={visto === e.id}>
          <span class="rotulo">{String(i + 1).padStart(2, '0')}</span>
          <span class="pn">{e.nome}</span>
          <span class="rotulo sit">{{ feita: 'Feita', agora: 'Agora', opcional: 'Opcional', pausada: 'Pausada', erro: 'Erro', espera: '—' }[s]}</span>
        </button>
      </li>
    {/each}
  </ol>
  {#each PASSOS.filter((e) => e.id === visto) as e}
    <div class="passo-detalhe">
      <p class="o">{e.o}</p>
      {#if e.id === 'revisao' && r}<p class="o">{r.revisar} pedem atenção · {r.juiz} corrigidos pelo juiz · {r.total - r.revisar - r.juiz} aprovados pelos modelos. Nada disso é obrigatório: o livro já pode ser gerado.</p>
        {#if r.revisar + r.juiz > 0}
          <div class="atalhos">
            <button class="elo" onclick={copiarPartes}>Copiar os trechos para uma IA grande</button>
            <button class="elo" onclick={salvarPartes}>Salvar os trechos em arquivo</button>
            <a class="elo" href="#revisao/{id}">Ver os pontos →</a>
          </div>
          {#if msgPartes}<p class="rotulo" aria-live="polite">{msgPartes}</p>{/if}
        {/if}
      {:else if sit(e.id) === 'agora'}<div class="barra"><Progresso valor={st.progresso || null} rotulo={st.mensagem || 'trabalhando'} /></div>
      {:else if sit(e.id) === 'erro'}<p class="msg erro">{st.mensagem}</p>{/if}
    </div>
  {/each}
{/if}

{#if st !== null}
  <section class="bloco">
    <h3>O livro</h3>
    <div class="atalhos">
      <a class="elo" href="#ler/{id}">Ler →</a>
      <a class="elo" href="#leitura/{id}">Corrigir o texto →</a>
      <a class="elo" href="#glossario/{id}">Glossário →</a>
      {#if r}<a class="elo" href="#revisao/{id}">Revisão →</a>{/if}
      {#if st.feitas?.includes('estrutura') && !v}<button class="elo" aria-expanded={folhear} onclick={() => (folhear = !folhear)}>{folhear ? 'Fechar o livro aberto' : 'Original e tradução lado a lado'}</button>{/if}
    </div>
    {#if folhear && !v}<LivroVivo {id} />{/if}
  </section>
  {#if info?.paragrafos}
    <section class="bloco">
      <h3>Gerar o livro</h3>
      <p class="o">Sai do texto aprovado, com a capa e as fontes do original quando o livro as tem.</p>
      <Gerar {id} />
    </section>
  {/if}
  {#if st.feitas?.includes('estrutura')}
    <section class="bloco">
      <h3>Comparar com outra cópia</h3>
      <p class="o">Tem outra edição ou outro arquivo deste mesmo livro, no idioma original? O app compara com a fonte, bloco a bloco, e mostra cortes, acréscimos e palavras trocadas.
        A outra cópia nunca escreve no texto: é só para você ver.</p>
      <label class="escolhe"><input type="file" accept=".epub,.pdf,.txt,.md,.html,.htm" onchange={compara} disabled={comparando} /><span class="rotulo">{comparando ? 'Comparando…' : 'EPUB, PDF com texto, TXT ou HTML'}</span></label>
      {#if erroCopia}<Chip estado="erro">{erroCopia}</Chip>{/if}
      {#each copias as c}
        <details class="copia">
          <summary><span class="cn">{c.arquivo}</span>
            <span class="rotulo">{c.data} · {c.resumo.iguais} iguais · <b class:alerta={c.resumo.diferentes}>{c.resumo.diferentes} diferentes</b> · <b class:alerta={c.resumo.ausentes}>{c.resumo.ausentes} só na nossa</b> · <b class:alerta={c.resumo.so_na_copia}>{c.resumo.so_na_copia} só na outra</b>{c.resumo.nao_comparados ? ` · ${c.resumo.nao_comparados} curtos sem comparar` : ''}</span></summary>
          {#if c.so_na_copia.length}
            <details><summary class="rotulo">{c.so_na_copia.length} só na outra cópia (pode ser corte na nossa fonte)</summary>
            <ul>{#each c.so_na_copia as x}<li><span class="rotulo">{x.palavras} palavras, depois de {x.depois_de ?? 'o começo'}</span><p class="o">{x.trecho}…</p></li>{/each}</ul></details>
          {/if}
          {#if c.ausentes.length}
            <details><summary class="rotulo">{c.ausentes.length} só na nossa fonte (a outra cópia não tem)</summary>
            <ul>{#each c.ausentes as x}<li><span class="rotulo">{x.id}</span><p class="o">{x.trecho}</p></li>{/each}</ul></details>
          {/if}
          {#if c.diferencas.length}
            <details open><summary class="rotulo">{c.diferencas.length} com palavras diferentes · riscado: a sua fonte · em verde: a outra cópia</summary>
            <ul>{#each c.diferencas as d}<li><span class="rotulo">{d.id}{d.total > d.mudancas.length ? ` · ${d.total} mudanças` : ''}</span>
              {#each d.mudancas as m}<p class="muda"><span class="o">…{m.antes}</span> <del>{m.nosso || '∅'}</del> <ins>{m.outra || '∅'}</ins></p>{/each}</li>{/each}</ul></details>
          {/if}
          {#if !c.diferencas.length && !c.ausentes.length && !c.so_na_copia.length}<p class="o">As duas cópias dizem o mesmo, palavra por palavra.</p>{/if}
        </details>
      {/each}
    </section>
  {/if}
  {#if rede?.edicoes && info}
    <section class="bloco">
      <h3>Outras edições</h3>
      <p class="o">Procura este título e autor em acervos públicos, para você comparar com a sua cópia. Saem do computador só o título e o autor.
        "Baixar e comparar" traz o arquivo aberto da edição e mostra as diferenças; vale para edições no mesmo idioma da sua fonte.</p>
      <div><Botao disabled={edicoes?.carregando} onclick={buscaEdicoes}>{edicoes?.carregando ? 'Procurando…' : 'Procurar'}</Botao></div>
      {#if edicoes?.erro}<Chip estado="erro">{edicoes.erro}</Chip>{/if}
      {#if edicoes?.achados}
        {#if edicoes.sem_resposta.length}<span class="rotulo">Sem resposta de: {edicoes.sem_resposta.join(', ')}</span>{/if}
        <ul class="edicoes">
          {#each edicoes.achados as e}
            <li><a href={e.link} target="_blank" rel="noopener noreferrer">{e.titulo}</a>
              <span class="rotulo">{[e.autor, e.ano, e.idioma, e.acervo].filter(Boolean).join(' · ')}</span>
              {#if st.feitas?.includes('estrutura') && e.acervo !== 'Open Library'}
                <span class="troca">{#if e.comparada}<span class="rotulo">Comparada · veja acima, em "Comparar com outra cópia"</span>
                  {:else}<button class="elo" disabled={e.comparando} onclick={() => comparaEdicao(e)}>{e.comparando ? 'Baixando e comparando…' : 'Baixar e comparar'}</button>{/if}
                  {#if e.erro}<span class="rotulo alerta">{e.erro}</span>{/if}</span>
              {/if}</li>
          {:else}<li class="rotulo">Nada encontrado.</li>{/each}
        </ul>
      {/if}
    </section>
  {/if}
  <section class="bloco">
    <h3>Aparência do livro gerado</h3>
    <p class="o">A capa e as fontes do PDF e do EPUB que você gera. Vêm do arquivo de origem quando ele as traz; aqui você troca por arquivos seus ou volta ao padrão do app. Não muda o texto.</p>
    {#if erroEstilo}<Chip estado="erro">{erroEstilo}</Chip>{/if}
    <div class="aparencia">
      {#if estilo?.capa}{#key vezCapa}<img src="/api/livro/{id}/capa?v={vezCapa}" alt="Capa em uso" />{/key}{:else}<div class="sem-capa rotulo">sem capa</div>{/if}
      <dl>
        <div><dt class="rotulo">Capa</dt><dd>{estilo?.capa ? (estilo.capa.startsWith('capa-escolhida') ? 'Escolhida por você' : 'A do arquivo de origem') : 'Nenhuma: o livro sai sem capa'}
          <span class="troca"><label class="elo">Trocar<input type="file" accept="image/jpeg,image/png" onchange={(e) => mandaEstilo('capa', e)} hidden /></label>
            {#if estilo?.capa}<button class="elo" onclick={() => tiraEstilo('capa')}>Tirar</button>{/if}</span></dd></div>
        {#each [['titulos', 'Títulos', 'Padrão do app'], ['texto', 'Texto', 'Padrão do app: Pagella no PDF; no EPUB, a fonte do leitor']] as [alvo, nome, padrao]}
          <div><dt class="rotulo">{nome}</dt><dd>{estilo?.[alvo]?.familia ?? (alvo === 'texto' && estilo?.texto_tex ? `${estilo.texto_tex.familia} · equivalente livre de ${estilo.fonte_original}` : padrao)}
            <span class="troca"><label class="elo">Usar uma fonte sua<input type="file" accept=".ttf,.otf" onchange={(e) => mandaEstilo('fonte', e, alvo)} hidden /></label>
              {#if estilo?.[alvo]}<button class="elo" onclick={() => tiraEstilo(alvo)}>Padrão do app</button>
              {:else if alvo === 'texto' && estilo?.texto_tex}<button class="elo" onclick={() => tiraEstilo('texto_tex')}>Padrão do app</button>{/if}</span></dd></div>
        {/each}
        <div><dt class="rotulo">Página do PDF</dt><dd>{estilo?.pagina ? `${estilo.pagina[0]} × ${estilo.pagina[1]} pol · a do original` : 'Padrão do app: 6 × 9 pol'}
          {#if estilo?.pagina}<span class="troca"><button class="elo" onclick={() => tiraEstilo('pagina')}>Padrão do app</button></span>{/if}</dd></div>
        {#if estilo?.origem}<div><dt class="rotulo">Origem</dt><dd class="o">Colhido de {estilo.origem}. Os arquivos ficam na pasta <code>estilo/</code> do livro.</dd></div>{/if}
      </dl>
    </div>
  </section>
{/if}

{#if st !== null && st.estado !== 'rodando'}
  <div class="zona"><button class="apagar" onclick={() => dlgApagar.showModal()}><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></svg>Apagar este livro</button><span class="rotulo">Vai para a lixeira da pasta de livros; dá para recuperar.</span></div>
{/if}

<style>
  .topo { padding-bottom: var(--e8); border-bottom: 1px solid var(--linha); display: grid; gap: var(--e3); }
  .volta { text-decoration: none; justify-self: start; transition: color var(--rapido); } .volta:hover { color: var(--papel); }
  h2 { animation: entra var(--lento) var(--curva) both; }
  .topo { position: relative; isolation: isolate; }
  .topo.com-capa { grid-template-columns: auto minmax(0, 1fr); column-gap: var(--e8); align-items: end; }
  /* a capa, desfocada, colore o fundo do cabeçalho */
  .topo.com-capa::before { content: ''; position: absolute; inset: calc(var(--e12) * -1) 0 0; /* só para cima: para os lados estouraria a página */ z-index: -1; background: var(--capa) center / cover; filter: blur(60px) saturate(1.3); opacity: 0.28;
                           mask-image: linear-gradient(#000 40%, transparent); -webkit-mask-image: linear-gradient(#000 40%, transparent); pointer-events: none; }
  .numeros { display: flex; flex-wrap: wrap; gap: var(--e3) var(--e8); margin: var(--e3) 0 0; }
  .numeros > div { display: grid; gap: 2px; } .numeros dd { margin: 0; font-family: var(--display); font-size: 1.9rem; line-height: 1; }
  .numeros .bom dd { color: var(--ok); } .numeros .alerta dd { color: var(--revisar); }
  dialog { background: var(--superficie); color: var(--papel); border: 1px solid var(--linha-forte); border-radius: var(--raio); padding: var(--e8); width: min(32rem, calc(100vw - 2rem)); }
  dialog[open] { display: grid; gap: var(--e4); } dialog::backdrop { background: rgb(0 0 0 / 0.7); backdrop-filter: blur(3px); }
  dialog .botoes { justify-content: flex-end; }
  dialog input.largo { width: 100%; }
  .liso { background: none; border-width: 0 0 1px; cursor: pointer; }
  .passos { list-style: none; margin: 0; padding: var(--e6) 0 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr)); gap: var(--e3) var(--e2); }
  .passos li { display: block; padding: 0; border: 0; animation: none; }
  .passos button { all: unset; cursor: pointer; box-sizing: border-box; width: 100%; display: grid; gap: var(--e1); padding: var(--e3) var(--e2) var(--e3) 0; border-top: 2px solid var(--linha-forte); transition: border-color var(--medio) var(--curva), color var(--medio) var(--curva); }
  .passos .pn { font-family: var(--display); text-transform: var(--caixa-titulos); font-size: 0.875rem; line-height: 1.15; }
  .passos .feita button { border-color: var(--ok); } .passos .agora button, .passos .erro button { border-color: var(--acento); } .passos .pausada button { border-color: var(--revisar); }
  .passos .espera { opacity: 0.5; } .passos .sel button { background: linear-gradient(color-mix(in srgb, var(--papel) 7%, transparent), transparent); }
  .passos button:hover .pn { color: var(--acento); } .passos button:focus-visible { outline: 1px solid var(--acento); outline-offset: 2px; }
  .passo-detalhe { display: grid; gap: var(--e3); padding: var(--e4) 0 var(--e8); border-bottom: 1px solid var(--linha); min-height: 4.5rem; }
  .apagar { all: unset; cursor: pointer; display: inline-flex; align-items: center; gap: var(--e2); padding: var(--e2) var(--e4); border: 1px solid var(--erro, var(--acento)); border-radius: var(--raio); color: var(--erro, var(--acento));
            font-family: var(--mono); font-size: var(--t-rotulo); text-transform: uppercase; letter-spacing: 0.18em; transition: background var(--rapido), color var(--rapido); }
  .apagar:hover { background: var(--erro, var(--acento)); color: var(--fundo); } .apagar:focus-visible { outline: 1px solid var(--papel); outline-offset: 3px; }
  .rapido { display: flex; gap: var(--e3); align-items: flex-start; grid-column: 1 / -1; } .rapido .rotulo { display: block; margin-top: 4px; text-transform: none; letter-spacing: 0; }
  .zona { display: flex; flex-wrap: wrap; gap: var(--e3) var(--e6); align-items: center; padding: var(--e8) 0; }

  .topo .volta { grid-column: 1 / -1; }
  .topo .capa { width: clamp(5.5rem, 12vw, 9rem); border: 1px solid var(--linha); box-shadow: 0 1.2rem 2.5rem -1rem rgb(0 0 0 / 0.8); animation: entra var(--lento) var(--curva) both; }
  .ident { display: grid; gap: var(--e3); min-width: 0; }
  .autor { font-family: var(--leitura); font-style: italic; color: var(--apagado); font-size: 1.1rem; }
  @keyframes entra { from { opacity: 0; transform: translateY(0.35em); } }

  .aviso { display: grid; gap: var(--e4); justify-items: start; padding: var(--e12) 0; }

  .painel { display: grid; gap: var(--e6); padding: var(--e8) 0; border-bottom: 1px solid var(--linha); }
  .estado { display: flex; flex-wrap: wrap; gap: var(--e3) var(--e6); align-items: baseline; }
  .msg { color: var(--apagado); } .msg.erro { color: var(--acento); margin-top: var(--e2); }
  .config { display: flex; flex-wrap: wrap; gap: var(--e6); }
  label { display: grid; gap: var(--e2); }
  .faixa { display: flex; gap: var(--e2); }
  input, select { font: inherit; color: var(--papel); background: var(--fundo); border: 1px solid var(--linha-forte); border-radius: var(--raio); padding: var(--e2) var(--e3); }
  input { width: 8rem; } .escolhe input { width: 26rem; max-width: 100%; border: 0; padding: 0; }
  input:focus-visible, select:focus-visible { outline: none; border-color: var(--acento); }
  .botoes { display: flex; flex-wrap: wrap; gap: var(--e6); align-items: center; }
  .abrir { font-family: var(--mono); font-size: var(--t-rotulo); text-transform: uppercase; letter-spacing: 0.22em; text-decoration: none; color: var(--papel); border-bottom: 1px solid var(--acento); padding-bottom: 2px; }
  .abrir:hover { color: var(--acento); }
  .nota { max-width: 60ch; }

  .vivo { padding: var(--e6) 0 var(--e8); border-bottom: 1px solid var(--linha); display: grid; gap: var(--e6); }
  .vivo-cab { display: flex; flex-wrap: wrap; gap: var(--e3) var(--e6); align-items: center; }
  .claro { color: var(--papel); } .alerta { color: var(--revisar); }
  .pulso { width: 8px; height: 8px; border-radius: 50%; background: var(--acento); animation: pulsa 1.4s ease-in-out infinite; box-shadow: 0 0 0 4px color-mix(in srgb, var(--acento) 25%, transparent); }
  .vivo-lados { display: grid; grid-template-columns: 1fr 1fr; gap: var(--e8); align-items: start; }
  .vivo-lados > div { display: grid; gap: var(--e3); min-width: 0; }
  .vivo-lados .leitura { max-height: 18rem; overflow-y: auto; white-space: pre-wrap; }
  .vivo-lados .fonte { color: var(--apagado); }
  .vivo-lados img { width: 100%; max-height: 24rem; object-fit: contain; object-position: left top; border: 1px solid var(--linha); background: #fff; }
  .parecer { font-family: var(--mono); font-size: 0.8125rem; color: var(--apagado); border-left: 2px solid var(--linha-forte); padding-left: var(--e3); white-space: pre-wrap; overflow-wrap: anywhere; }
  .cursor { display: inline-block; width: 0.5em; height: 1em; margin-left: 2px; background: var(--acento); vertical-align: text-bottom; animation: pisca 1s steps(2) infinite; }
  @keyframes pisca { 50% { opacity: 0; } }
  @media (max-width: 900px) { .vivo-lados { grid-template-columns: 1fr; } }
  @media (prefers-reduced-motion: reduce) { .cursor, .pulso { animation: none; } }

  .bloco { padding: var(--e8) 0; border-bottom: 1px solid var(--linha); display: grid; gap: var(--e4); }
  .atalhos { display: flex; flex-wrap: wrap; gap: var(--e4) var(--e8); }
  .aparencia { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: var(--e8); align-items: start; }
  .aparencia img { width: 10rem; border: 1px solid var(--linha); box-shadow: 0 1.2rem 2.5rem -1rem rgb(0 0 0 / 0.8); }
  .aparencia dl { margin: 0; display: grid; max-width: 44rem; }
  .aparencia dl > div { display: grid; grid-template-columns: 7rem minmax(0, 1fr); gap: var(--e4); align-items: baseline; padding: var(--e3) 0; border-bottom: 1px solid var(--linha); }
  .aparencia dl > div:first-child { padding-top: 0; }
  .aparencia dd { margin: 0; } .aparencia dd.o { color: var(--apagado); }
  @media (max-width: 640px) { .aparencia { grid-template-columns: 1fr; } .aparencia dl > div { grid-template-columns: 1fr; gap: var(--e1); } }
  code { font-family: var(--mono); font-size: 0.85em; }
  .edicoes { list-style: none; margin: 0; padding: 0; max-height: 24rem; overflow: auto; }
  .edicoes li { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--e1); padding: var(--e3) 0; border-top: 1px solid var(--linha); }
  .edicoes a { text-decoration: none; } .edicoes a:hover { color: var(--acento); }

  .sit { padding-top: 0.5em; }
  @keyframes pulsa { 50% { box-shadow: 0 0 0 9px transparent; } }
  .o { color: var(--apagado); max-width: 62ch; }
  .barra { margin-top: var(--e3); max-width: 34rem; }
  .feita .sit { color: var(--ok); } .agora .sit { color: var(--papel); }

  @media (max-width: 900px) { .sit { display: none; } }
  @media (prefers-reduced-motion: reduce) { h2 { animation: none; } }
  .escolhe { display: flex; flex-wrap: wrap; gap: var(--e3) var(--e6); align-items: center; }
  .copia { border-top: 1px solid var(--linha); padding: var(--e3) 0; } .copia summary { cursor: pointer; display: flex; flex-wrap: wrap; gap: var(--e2) var(--e6); align-items: baseline; }
  .copia .cn { font-family: var(--mono); overflow-wrap: anywhere; } .copia b { font-weight: inherit; } .copia b.alerta { color: var(--revisar); }
  .copia ul { list-style: none; margin: 0; padding: 0; max-height: 26rem; overflow-y: auto; overflow-x: hidden; } .copia li p { margin: 0; max-width: none; }
  .copia details { padding-top: var(--e3); } .copia details summary { color: var(--papel); } .copia li { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--e1); padding: var(--e3) 0; border-top: 1px solid var(--linha); animation: none; }
  .muda { overflow-wrap: anywhere; } .muda del { color: var(--revisar); text-decoration: line-through; } .muda ins { color: var(--ok); text-decoration: none; }
  .sem-capa { width: 10rem; aspect-ratio: 2 / 3; display: grid; place-items: center; border: 1px dashed var(--linha-forte); }
  .troca { display: inline-flex; flex-wrap: wrap; gap: var(--e2) var(--e4); margin-left: var(--e4); } .troca .elo { cursor: pointer; background: none; border-width: 0 0 1px; font-size: var(--t-rotulo); }
</style>
