<script>
  import Botao from '../lib/Botao.svelte'
  import Chip from '../lib/Chip.svelte'
  import Progresso from '../lib/Progresso.svelte'
  import Opcao from '../lib/Opcao.svelte'
  import Interruptor from '../lib/Interruptor.svelte'
  import { api } from '../lib/api.js'
  import { TEMAS, FONTES, ACENTOS, PADRAO, HEX, contraste, cores, fonte, exporta, importa } from '../lib/aparencia.js'
  let temaColado = $state('')
  let temaMsg = $state('')
  let temaAntes = $state(null)      // a aparência de antes de aplicar um tema colado, para desfazer
  async function copiaTema() { const t = exporta(aparencia); temaColado = t; try { await navigator.clipboard.writeText(t); temaMsg = 'Tema copiado. O texto também está no campo abaixo.' } catch { temaMsg = 'Copie o texto do campo abaixo.' } }
  function usaTema() { try { const t = importa(temaColado); temaAntes = { ...aparencia }; aparencia = { ...aparencia, ...t }; temaMsg = 'Tema aplicado.' } catch (e) { temaMsg = e.message } }


  let { aparencia = $bindable(), aba = '', aoMudarRede } = $props()
  const ABAS = [['aparencia', 'Aparência'], ['processo', 'Processamento'], ['rede', 'Rede e privacidade'], ['biblioteca', 'Biblioteca'], ['sistema', 'Sistema']]
  let atual = $derived(ABAS.some(([id]) => id === aba) ? aba : 'aparencia')

  let cfg = $state(null)       // configuração guardada no servidor local (rede e processamento)
  let sis = $state(null)
  let med = $state(null), medindo = $state(false)      // último teste de erros plantados (neste computador)
  let registro = $state([])
  let chave = $state('')
  let erro = $state('')
  let aviso = $state('')

  async function carrega() {
    try { cfg = await api('/api/config'); registro = await api('/api/rede/registro'); sis = await api('/api/sistema'); med = (await api('/api/medicoes')).ultima }
    catch (e) { erro = e.message; cfg = cfg ?? { rede: {}, processo: {} } }
  }
  $effect(() => { carrega() })
  // reinicia o programa: o Estante (desktop) relança a si mesmo; fora dele, o botão só avisa
  let reiniciando = $state(false)
  async function reiniciar() {
    if (!confirm('Reiniciar o Estante? Um livro que estiver processando volta a rodar quando o programa abrir de novo.')) return
    if (!window.estante?.reiniciar) { erro = 'Feche e abra o Estante para reiniciar.'; return }
    reiniciando = true
    await window.estante.reiniciar()
  }
  // desinstalar: só existe no programa instalado. Tira o programa e os modelos; a biblioteca só sai se a pessoa marcar
  const instalado = typeof window !== 'undefined' && !!window.estante?.desinstalar
  let apagarBiblioteca = $state(false), desinstalando = $state(false)
  async function desinstalar() {
    const oque = apagarBiblioteca ? 'o programa, os modelos de IA E A SUA BIBLIOTECA (livros e traduções)' : 'o programa e os modelos de IA. A sua biblioteca fica guardada'
    if (!confirm(`Desinstalar o Estante? Isto apaga ${oque}.`)) return
    if (apagarBiblioteca && !confirm('Confirma apagar também todos os seus livros e traduções? Não dá para desfazer.')) return
    desinstalando = true
    const r = await window.estante.desinstalar({ biblioteca: apagarBiblioteca })
    if (r && !r.ok) { erro = r.erro; desinstalando = false }
  }
  async function medirAgora() {
    medindo = true
    try { med = (await api('/api/medicoes', 'POST')).ultima; erro = '' } catch (e) { erro = e.message } finally { medindo = false }
  }

  async function salva(parte, parcial) {
    erro = ''; aviso = ''
    try { cfg = await api('/api/config', 'PUT', { [parte]: parcial }); aviso = 'Guardado'; aoMudarRede?.(cfg.rede) }
    catch (e) { erro = e.message }
  }
  const salvaFora = () => { salva('rede', { fora_url: cfg.rede.fora_url.trim(), fora_modelo: cfg.rede.fora_modelo.trim(), fora_chave: chave }); chave = '' }

  // aparência: cada mudança vale na hora, no app inteiro
  let estado = $derived(cores(aparencia))
  let proprias = $derived(HEX.test(aparencia.fundo) && HEX.test(aparencia.texto))
  let razao = $derived(proprias ? contraste(aparencia.fundo, aparencia.texto) : null)
  const outra = (grupo) => (aparencia[grupo]?.startsWith('outra:') ? aparencia[grupo].slice(6) : '')
  const GRUPOS = [
    { id: 'titulos', nome: 'Títulos', o: 'Nomes dos livros e cabeçalhos das telas.', amostra: 'A Estante' },
    { id: 'leitura', nome: 'Leitura', o: 'O texto dos livros dentro do app, na revisão e na leitura. Não muda a fonte do PDF nem do EPUB que você gera.', amostra: 'O texto do livro, como o autor escreveu.' },
    { id: 'interface', nome: 'Interface', o: 'Menus, botões e avisos.', amostra: 'Abrir a revisão' },
  ]
  const DO_PC = ['Georgia', 'Palatino Linotype', 'Cambria', 'Constantia', 'Book Antiqua', 'Times New Roman', 'Segoe UI', 'Calibri', 'Candara', 'Verdana', 'Trebuchet MS', 'Bahnschrift', 'Consolas', 'Courier New']

  const REDE = [
    { k: 'pesquisa', nome: 'Pesquisa de apoio', oque: 'No glossário, consulta dicionário e enciclopédia (Wikcionário e Wikipédia) sobre um termo.',
      ligado: 'Você decide a tradução de um termo difícil com a definição ao lado.', desligado: 'O glossário funciona igual, sem a consulta.', sai: 'Só o termo pesquisado.' },
    { k: 'edicoes', nome: 'Acervos abertos', oque: 'Busca livros e outras edições no Internet Archive, no Project Gutenberg e na Open Library, e baixa para a sua estante os que têm arquivo aberto.',
      ligado: 'Você acha um livro e o traz para o app sem sair dele, e compara edições para achar cortes.', desligado: 'Você baixa os arquivos por conta própria e solta na pasta de livros.',
      sai: 'O que você digitar na busca (título, autor) e o pedido do arquivo escolhido.' },
    { k: 'modelo_fora', nome: 'Modelo de fora', oque: 'Usa um modelo pela internet, com endereço e chave seus, num dos papéis (tradutor, auditor ou juiz).',
      ligado: 'Pode ser mais rápido ou mais capaz que os modelos que cabem no seu computador. Se ele recusar ou amenizar um trecho, o bloco é refeito pelo modelo local.',
      desligado: 'Tudo roda só no seu computador.', sai: 'O TEXTO de cada bloco enviado a ele.' },
  ]
</script>

<header class="topo-tela">
  <div class="rotulo">Configurações · ficam só neste computador</div>
  <h2>Configurações</h2>
  <p class="sub">O app é seu: aparência, modelos e o que ele pode ou não fazer são escolhas suas. Cada opção diz para que serve e o que muda.</p>
</header>

<nav class="abas" aria-label="Seções das configurações">
  {#each ABAS as [id, nome]}<a href="#config/{id}" class:on={atual === id} aria-current={atual === id ? 'page' : undefined}>{nome}</a>{/each}
</nav>

{#if erro}<p class="estado" role="alert"><Chip estado="erro">{erro}</Chip></p>{/if}

{#if atual === 'aparencia'}
  <section>
    <div class="titulo-secao"><h3>Tema</h3><p class="o">As cores do app inteiro. Vale na hora e não muda nada nos livros que você gera.</p></div>
    <div class="temas">
      {#each TEMAS as t}
        <button class="tema" class:on={aparencia.tema === t.id && !estado.proprio} onclick={() => { aparencia.tema = t.id; aparencia.fundo = ''; aparencia.texto = '' }} aria-pressed={aparencia.tema === t.id}
                style:background={t.cores.fundo} style:color={t.cores.papel} style:border-color={t.cores['linha-forte']}>
          <span class="mini" aria-hidden="true"><b style:background={t.cores.acento}></b><i style:background={t.cores.papel}></i><i style:background={t.cores.apagado}></i><i style:background={t.cores.apagado} style:width="55%"></i></span>
          <span class="tn">{t.nome}</span>
          <span class="to" style:color={t.cores.apagado}>{t.o}</span>
        </button>
      {/each}
    </div>
  </section>

  <section>
    <Opcao nome="Cor de destaque" oque="A cor dos botões principais, das linhas ativas e do texto selecionado. Escolha uma das sugeridas ou qualquer outra.">
      <div class="bolas">
        <button class="bola auto" class:on={!aparencia.acento} onclick={() => (aparencia.acento = '')} title="A do tema" aria-label="Cor do tema"></button>
        {#each ACENTOS as c}<button class="bola" class:on={aparencia.acento === c} style:background={c} onclick={() => (aparencia.acento = c)} aria-label="Cor {c}"></button>{/each}
        <label class="outra-cor" title="Outra cor"><input type="color" value={HEX.test(aparencia.acento) ? aparencia.acento : estado.c.acento} oninput={(e) => (aparencia.acento = e.currentTarget.value)} /><span class="rotulo">Outra</span></label>
      </div>
    </Opcao>
  </section>

  <section>
    <div class="titulo-secao"><h3>Fontes</h3><p class="o">Todas vêm dentro do app; nada é buscado na internet. Você também pode usar qualquer fonte instalada no seu computador.</p></div>
    {#each GRUPOS as g}
      <div class="grupo">
        <div class="gcab"><span class="rotulo claro">{g.nome}</span><span class="o">{g.o}</span></div>
        <div class="fontes">
          {#each FONTES[g.id] as f}
            <button class="fonte" class:on={aparencia[g.id] === f.id} onclick={() => (aparencia[g.id] = f.id)} aria-pressed={aparencia[g.id] === f.id}>
              <span class="amostra" style:font-family={f.pilha}>{g.amostra}</span><span class="rotulo">{f.nome}</span>
            </button>
          {/each}
          <label class="fonte propria" class:on={!!outra(g.id)}>
            <input list="fontes-do-pc" placeholder="Outra fonte" aria-label="Outra fonte, do seu computador" value={outra(g.id)} style:font-family={outra(g.id) ? fonte(g.id, aparencia[g.id]).pilha : null}
                   onchange={(e) => (aparencia[g.id] = e.currentTarget.value.trim() ? 'outra:' + e.currentTarget.value.trim() : PADRAO[g.id])} />
            <span class="rotulo">Do seu computador</span>
          </label>
        </div>
      </div>
    {/each}
    <datalist id="fontes-do-pc">{#each DO_PC as n}<option value={n}></option>{/each}</datalist>
  </section>

  <section class="grade">
    <Opcao nome="Tamanho do texto" oque="Aumenta ou diminui tudo de uma vez: textos, botões e espaços.">
      <div class="segmento">{#each [90, 100, 112, 125] as t}<button class:on={aparencia.tamanho === t} onclick={() => (aparencia.tamanho = t)}>{t}%</button>{/each}</div>
    </Opcao>
    <Opcao nome="Cantos" oque="O formato dos botões, campos e cartões.">
      <div class="segmento">{#each [['retos', 'Retos'], ['suaves', 'Suaves'], ['redondos', 'Redondos']] as [id, n]}<button class:on={aparencia.cantos === id} onclick={() => (aparencia.cantos = id)}>{n}</button>{/each}</div>
    </Opcao>
    <Opcao nome="Títulos em maiúsculas" ligado="Títulos em caixa-alta, como na lombada de um livro antigo." desligado="Títulos escritos como no original, com maiúsculas e minúsculas.">
      <Interruptor ligado={aparencia.caixa} rotulo="Títulos em maiúsculas" onclick={() => (aparencia.caixa = !aparencia.caixa)} />
    </Opcao>
    <Opcao nome="Tribunal" oque="Como o trabalho dos modelos aparece na tela do livro: uma cena desenhada com tradutor, auditor e juiz, ou só as caixas de texto. Em tela estreita valem as caixas.">
      <div class="segmento">{#each [['personagens', 'Personagens'], ['quadros', 'Quadros']] as [id, n]}<button class:on={aparencia.tribunal === id} onclick={() => (aparencia.tribunal = id)}>{n}</button>{/each}</div>
    </Opcao>
    <Opcao nome="Animações" ligado="Transições entre as telas e efeitos ao passar o mouse." desligado="Tudo aparece na hora. Bom se o movimento incomoda ou se o computador é lento.">
      <Interruptor ligado={aparencia.movimento} rotulo="Animações" onclick={() => (aparencia.movimento = !aparencia.movimento)} />
    </Opcao>
    <Opcao nome="Abertura" ligado="A animação de entrada toda vez que o app abre." desligado="O app abre direto na Biblioteca.">
      <Interruptor ligado={aparencia.abertura} rotulo="Abertura animada" onclick={() => (aparencia.abertura = !aparencia.abertura)} />
    </Opcao>
  </section>

  <section>
    <details>
      <summary class="rotulo">Cores próprias (avançado)</summary>
      <div class="avancado">
        <p class="o">Escolha o fundo e a cor do texto; as linhas e os tons intermediários são calculados a partir dos dois. Um par ilegível não é aplicado, para ninguém ficar preso numa tela em branco.</p>
        <div class="linha">
          <label class="cor"><input type="color" value={HEX.test(aparencia.fundo) ? aparencia.fundo : estado.c.fundo} oninput={(e) => { aparencia.fundo = e.currentTarget.value; if (!HEX.test(aparencia.texto)) aparencia.texto = TEMAS.find((t) => t.id === aparencia.tema).cores.papel }} /><span class="rotulo">Fundo</span></label>
          <label class="cor"><input type="color" value={HEX.test(aparencia.texto) ? aparencia.texto : TEMAS.find((t) => t.id === aparencia.tema).cores.papel} oninput={(e) => { aparencia.texto = e.currentTarget.value; if (!HEX.test(aparencia.fundo)) aparencia.fundo = TEMAS.find((t) => t.id === aparencia.tema).cores.fundo }} /><span class="rotulo">Texto</span></label>
          {#if proprias}
            {#if razao < 3}<Chip estado="erro">Contraste {razao.toFixed(1)} : 1 · ilegível, não aplicado</Chip>
            {:else if razao < 4.5}<Chip estado="revisar">Contraste {razao.toFixed(1)} : 1 · cansa a vista</Chip>
            {:else}<Chip estado="ok">Contraste {razao.toFixed(1)} : 1</Chip>{/if}
            <Botao variante="texto" onclick={() => { aparencia.fundo = ''; aparencia.texto = '' }}>Voltar às cores do tema</Botao>
          {/if}
        </div>
      </div>
    </details>
    <div class="linha"><Botao onclick={() => (aparencia = { ...PADRAO })}>Voltar tudo ao padrão</Botao><span class="rotulo">O nome e a marca do Estante não mudam; a cor deles acompanha o tema.</span></div>
  </section>
  <section>
    <div class="titulo-secao"><h3>Compartilhar</h3><p class="o">Um tema cabe num texto curto, que você manda para quem quiser. Vai só o visual (cores, fontes, cantos); nada do seu computador nem dos seus livros.</p></div>
    <div class="linha"><Botao onclick={copiaTema}>Copiar este tema</Botao>
      <Botao variante="cheio" disabled={!temaColado.trim()} onclick={usaTema}>Usar o tema colado</Botao>
      {#if temaAntes}<Botao variante="texto" onclick={() => { aparencia = temaAntes; temaAntes = null; temaMsg = 'Voltou ao que era.' }}>Desfazer</Botao>{/if}</div>
    <textarea rows="3" bind:value={temaColado} placeholder="Cole aqui um tema recebido (começa com estante-tema:1:)" aria-label="Texto do tema" spellcheck="false"></textarea>
    {#if temaMsg}<p class="rotulo" aria-live="polite">{temaMsg}</p>{/if}
  </section>

{:else if cfg === null}
  <Progresso rotulo="Abrindo" />

{:else if atual === 'processo'}
  <section>
    <div class="titulo-secao"><h3>Processamento</h3><p class="o">Como o app trabalha num livro. Nada aqui muda o princípio: o texto do autor não é alterado, e nada entra no livro sem o seu aceite.</p></div>
    <Opcao nome="Juiz" oque="Um terceiro modelo decide as disputas entre o tradutor e o auditor. Se o auditor tem razão, o juiz reescreve o trecho da tradução e você confere antes de aceitar."
           ligado="Bem menos blocos para revisar: num livro de 750 blocos, ficaram 32 para você e 77 corrigidos pelo juiz para conferir. Custa uns 15 minutos a mais por livro. Ele erra: por isso o que ele corrige vem separado."
           desligado="Todo bloco com objeção vai para a sua revisão, sem filtro. Mais trabalho, nenhuma decisão automática.">
      <Interruptor ligado={cfg.processo.juiz} rotulo="Juiz" onclick={() => salva('processo', { juiz: !cfg.processo.juiz })} />
    </Opcao>
    <Opcao nome="Refazer trechos abrandados" oque="Quando o tradutor rápido troca uma palavra forte do autor por uma branda, o bloco é refeito pelo modelo maior, se houver um instalado."
           ligado="Mantém a força do original nos trechos mais crus (acertou os 3 casos do livro de teste). Custa uma troca de modelo por livro."
           desligado="O bloco só recebe o alerta e vai para a sua revisão.">
      <Interruptor ligado={cfg.processo.refazer_abrandado} rotulo="Refazer trechos abrandados" onclick={() => salva('processo', { refazer_abrandado: !cfg.processo.refazer_abrandado })} />
      <Interruptor ligado={cfg.processo.aceite_automatico} rotulo="Aceitar tudo ao terminar, sem revisão" onclick={() => salva('processo', { aceite_automatico: !cfg.processo.aceite_automatico })} />
      <p class="o">Desligado por padrão. Ligado, o app aceita os blocos que sobraram ao fim do processamento (inclusive os que pediam atenção). Cada aceite fica no histórico, e a prova de fidelidade mostra o caminho de cada bloco.</p>
    </Opcao>
    <div class="linha"><a class="elo" href="#modelos">Escolher o modelo de cada papel →</a></div>
  </section>

{:else if atual === 'rede'}
  <section>
    <div class="titulo-secao"><h3>Rede e privacidade</h3><p class="o">O Estante funciona inteiro sem internet. Cada item abaixo vem desligado; ligado, o app só faz o que está descrito, quando você pede, e anota tudo no registro.
      Nada que vem de fora entra no texto do livro sozinho.</p></div>
    {#each REDE as c}
      <Opcao nome={c.nome} oque={c.oque} ligado={c.ligado} desligado={c.desligado} sai={c.sai}>
        <Interruptor ligado={cfg.rede[c.k]} rotulo={c.nome} onclick={() => salva('rede', { [c.k]: !cfg.rede[c.k] })} />
      </Opcao>
    {/each}

    {#if cfg.rede.modelo_fora}
      <form class="fora" onsubmit={(e) => { e.preventDefault(); salvaFora() }}>
        <label><span class="rotulo">Endereço do serviço (formato OpenAI)</span><input bind:value={cfg.rede.fora_url} placeholder="https://…/v1" /></label>
        <label><span class="rotulo">Nome do modelo</span><input bind:value={cfg.rede.fora_modelo} placeholder="nome-do-modelo" /></label>
        <label><span class="rotulo">Chave {cfg.rede.tem_chave ? '(já guardada; preencha só para trocar)' : ''}</span><input type="password" bind:value={chave} autocomplete="off" /></label>
        <div class="linha"><Botao>Guardar</Botao><span class="rotulo">Depois, escolha "modelo de fora" num papel na tela Modelos</span></div>
      </form>
    {/if}
    {#if aviso}<p><Chip estado="ok">{aviso}</Chip></p>{/if}

    <details>
      <summary class="rotulo">Registro do que saiu ({registro.length})</summary>
      <ol class="registro">
        {#each registro as r}<li><span class="rotulo">{r.quando} · {r.destino}</span> {r.enviado}</li>{:else}<li class="rotulo">Nada saiu deste computador pelo app.</li>{/each}
      </ol>
    </details>
  </section>

{:else if atual === 'biblioteca'}
  <section>
    <div class="titulo-secao"><h3>Biblioteca</h3><p class="o">Onde ficam os seus livros. Cada livro é uma pasta com o arquivo de origem, o texto aprovado e o histórico de tudo o que mudou.</p></div>
    <Opcao nome="Pasta dos livros" oque={sis?.biblioteca ?? ''}></Opcao>
    <Opcao nome="Cópia de segurança" oque="Um arquivo .zip com os textos, os arquivos de origem e o histórico. Os PDFs e EPUBs gerados ficam de fora, porque dá para gerar de novo.">
      <a class="elo" href="/api/backup">Baixar a cópia →</a>
    </Opcao>
  </section>

{:else}
  <section>
    <div class="titulo-secao"><h3>Sistema</h3><p class="o">O que o app encontrou neste computador. O que falta pode ser instalado rodando o instalador de novo.</p></div>
    {#if sis}
      <ul class="sistema">
        <li><span class="rotulo">Placa de vídeo</span><span>{sis.placa ? `${sis.placa.nome} · ${sis.placa.gb} GB` : 'não detectada'}</span></li>
        <li><span class="rotulo">Espaço livre</span><span>{sis.disco_livre_gb} GB</span></li>
        <li><span class="rotulo">Python</span><span>{sis.python}</span></li>
        {#each sis.componentes as c}
          <li><span class="rotulo">{c.nome}</span><span class="para">{c.para}</span>{#if c.versao}<Chip estado="ok">{c.versao.length > 34 ? 'instalado' : c.versao}</Chip>{:else}<Chip estado="revisar">não instalado</Chip>{/if}</li>
        {/each}
      </ul>
    {/if}
    <div class="titulo-secao">
      <h3>Reiniciar o aplicativo</h3>
      <p class="o">Fecha e abre de novo o programa. Use depois de atualizar o código.</p>
    </div>
    <div class="comando"><Botao onclick={reiniciar} disabled={reiniciando}>{reiniciando ? 'Reiniciando…' : 'Reiniciar o app'}</Botao></div>
    {#if instalado}
      <div class="titulo-secao">
        <h3>Desinstalar o Estante</h3>
        <p class="o">Tira o programa e os modelos de IA baixados (vários GB). A sua biblioteca, com os livros e as traduções, fica guardada, a não ser que você marque a opção abaixo.</p>
      </div>
      <label class="o"><input type="checkbox" bind:checked={apagarBiblioteca} /> Apagar também a minha biblioteca (livros e traduções). Não dá para desfazer.</label>
      <div class="comando"><Botao onclick={desinstalar} disabled={desinstalando}>{desinstalando ? 'Desinstalando…' : 'Desinstalar'}</Botao></div>
    {/if}
    <div class="titulo-secao">
      <h3>Medir neste computador</h3>
      <p class="o">Estraga de propósito traduções boas (frase tirada, número trocado, "não" tirado…) e conta quantos erros as checagens automáticas pegam. Aqui roda só isso: leva segundos e não usa a placa. Com auditor e juiz, use a linha de comando <code>python app/medir.py --auditor MODELO --juiz MODELO</code>.</p>
    </div>
    <div class="comando"><Botao onclick={medirAgora} disabled={medindo}>{medindo ? 'Medindo…' : 'Medir agora'}</Botao></div>
    {#if med}
      <p class="o">Última medição: {med.quando} · {med.segundos} s · sem auditor nem juiz</p>
      <ul class="sistema">
        {#each Object.entries(med.tipos).filter(([, r]) => r[0]) as [tipo, r]}
          <li><span class="rotulo">{tipo === 'limpo' ? 'Tradução boa' : tipo}</span><span>{tipo === 'limpo' ? `${r[1]} de ${r[0]} com alerta (ideal: 0)` : `${r[1]} de ${r[0]} pegos`}</span></li>
        {/each}
      </ul>
    {/if}
  </section>
{/if}

<style>
  .estado { padding-top: var(--e4); }
  .abas { display: flex; flex-wrap: wrap; gap: var(--e2) var(--e8); padding: var(--e4) 0; border-bottom: 1px solid var(--linha); position: sticky; top: 0; background: var(--fundo); z-index: 5; }
  .abas a { font-family: var(--mono); font-size: var(--t-rotulo); text-transform: uppercase; letter-spacing: 0.22em; text-decoration: none; color: var(--apagado); padding: var(--e2) 0; border-bottom: 1px solid transparent; transition: color var(--medio) var(--curva), border-color var(--medio) var(--curva); }
  .abas a:hover { color: var(--papel); } .abas a.on { color: var(--papel); border-color: var(--acento); }
  section { padding: var(--e8) 0; border-bottom: 1px solid var(--linha); display: grid; gap: var(--e6); }
  section.grade { grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr)); align-items: start; }
  .titulo-secao { display: grid; gap: var(--e2); }
  .o { color: var(--apagado); max-width: 70ch; }
  .claro { color: var(--papel); }

  .temas { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 12rem), 1fr)); gap: var(--e4); }
  .tema { all: unset; cursor: pointer; box-sizing: border-box; display: grid; gap: var(--e2); align-content: start; padding: var(--e4); border: 1px solid; border-radius: var(--raio); min-height: 9rem;
          transition: transform var(--medio) var(--curva), box-shadow var(--medio) var(--curva); }
  .tema:hover { transform: translateY(-3px); }
  .tema.on { box-shadow: 0 0 0 2px var(--acento); }
  .tema:focus-visible { outline: 2px solid var(--acento); outline-offset: 3px; }
  .mini { display: grid; gap: 5px; margin-bottom: var(--e2); } .mini b { width: 2rem; height: 3px; } .mini i { height: 5px; width: 80%; opacity: 0.85; } .mini i:first-of-type { height: 9px; width: 62%; opacity: 1; }
  .tn { font-family: var(--marca); text-transform: uppercase; letter-spacing: 0.08em; font-size: 1rem; }
  .to { font-size: 0.8125rem; line-height: 1.35; }

  .bolas { display: flex; flex-wrap: wrap; gap: var(--e3); align-items: center; }
  .bola { all: unset; cursor: pointer; width: 1.6rem; height: 1.6rem; border-radius: 50%; box-shadow: 0 0 0 1px var(--linha-forte); transition: transform var(--rapido) var(--curva); }
  .bola:hover { transform: scale(1.15); } .bola.on { box-shadow: 0 0 0 2px var(--fundo), 0 0 0 4px var(--papel); }
  .bola.auto { background: conic-gradient(var(--papel) 0 50%, var(--fundo) 0); }
  .bola:focus-visible { outline: 1px solid var(--acento); outline-offset: 4px; }
  .outra-cor, .cor { display: inline-flex; align-items: center; gap: var(--e2); cursor: pointer; }
  input[type='color'] { width: 2rem; height: 2rem; padding: 0; border: 1px solid var(--linha-forte); border-radius: 50%; background: none; cursor: pointer; overflow: hidden; }
  input[type='color']::-webkit-color-swatch-wrapper { padding: 0; } input[type='color']::-webkit-color-swatch { border: 0; border-radius: 50%; }

  .grupo { display: grid; gap: var(--e3); }
  .gcab { display: flex; flex-wrap: wrap; gap: var(--e2) var(--e4); align-items: baseline; }
  .fontes { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 12.5rem), 1fr)); gap: var(--e3); }
  .fonte { all: unset; cursor: pointer; box-sizing: border-box; display: grid; gap: var(--e2); align-content: space-between; padding: var(--e4); min-height: 5.75rem; border: 1px solid var(--linha); border-radius: var(--raio);
           transition: border-color var(--medio) var(--curva), background var(--medio) var(--curva); }
  .fonte:hover { border-color: var(--linha-forte); } .fonte.on { border-color: var(--acento); background: color-mix(in srgb, var(--acento) 10%, transparent); }
  .fonte:focus-visible, .fonte:focus-within { outline: 1px solid var(--acento); outline-offset: 2px; }
  .amostra { font-size: 1.25rem; line-height: 1.2; overflow-wrap: anywhere; }
  .propria { cursor: text; } .propria input { border: 0; border-bottom: 1px solid var(--linha-forte); border-radius: 0; background: transparent; padding: var(--e1) 0; width: 100%; font-size: 1.05rem; }


  .avancado { display: grid; gap: var(--e4); padding-top: var(--e4); }
  .fora { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr)); gap: var(--e4); padding: var(--e6); border: 1px solid var(--linha); border-radius: var(--raio); }
  .fora .linha { grid-column: 1 / -1; }
  label { display: grid; gap: var(--e2); } .fora label input { width: 100%; }
  .linha { display: flex; flex-wrap: wrap; gap: var(--e4) var(--e6); align-items: center; }
  summary { cursor: pointer; } summary:hover { color: var(--papel); }
  .registro { list-style: none; margin: var(--e4) 0 0; padding: 0; display: grid; gap: var(--e2); color: var(--apagado); max-height: 18rem; overflow: auto; }
  .sistema { list-style: none; margin: 0; padding: 0; display: grid; }
  .sistema li { display: grid; grid-template-columns: 11rem minmax(0, 1fr) auto; gap: var(--e2) var(--e6); align-items: baseline; padding: var(--e3) 0; border-top: 1px solid var(--linha); }
  .sistema .para { color: var(--apagado); }
  @media (max-width: 640px) { .sistema li { grid-template-columns: 1fr; } }
</style>
