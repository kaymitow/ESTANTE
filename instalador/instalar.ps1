# Instalador do Estante a partir do código (quem só quer usar baixa o Estante Setup na página de Releases). Instala o que faltar, prepara o app e o abre.
#   instalar.bat (na pasta principal)     abre a janela de instalação
#   instalar.bat -Simular                 percorre os passos sem instalar nem baixar nada
#   instalador\instalar.ps1 -Teste a.png -Pagina 2    desenha uma página da janela num arquivo e sai (para conferir o visual)
# Usa o winget (já vem no Windows 10 e 11). Nada é enviado a lugar nenhum: só baixa os programas e os modelos dos sites oficiais.
# Este arquivo é UTF-8 com marca (BOM); sem ela o PowerShell 5.1 troca os acentos. ferramentas/publicar.py confere isso.
param([switch]$Simular, [string]$Teste = '', [int]$Pagina = 0, [switch]$Auto)      # -Auto (com -Simular): percorre tudo sozinho e fecha, para teste
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot      # o instalador fica numa pasta; os caminhos do app são a partir da pasta principal
Set-Location $raiz
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
trap { [void][Windows.Forms.MessageBox]::Show("O instalador parou com um erro:`n`n" + $_.Exception.Message + "`n`nLinha " + $_.InvocationInfo.ScriptLineNumber, 'Estante'); exit 1 }

function Tem($cmd) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { return $false }
    if ($cmd -ne 'python') { return $true }
    # o Windows traz um "python" falso que só abre a loja: confere se responde a versão
    try { return [bool]((& python --version 2>$null) -match 'Python 3') } catch { return $false }
}
function AtualizaPath { $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User') }

# ---------- o que pode ser instalado ----------
$programas = @(
    @{ id = 'Python.Python.3.12';       cmd = 'python';        nome = 'Python 3.12'; para = 'o motor do app';                                        necessario = $true },
    @{ id = 'Git.Git';                  cmd = 'git';           nome = 'Git';         para = 'guarda o histórico de cada mudança nos seus livros';    necessario = $true },
    @{ id = 'JohnMacFarlane.Pandoc';    cmd = 'pandoc';        nome = 'Pandoc';      para = 'lê e gera EPUB, Word e os outros formatos';             necessario = $true },
    @{ id = 'MiKTeX.MiKTeX';            cmd = 'xelatex';       nome = 'MiKTeX';      para = 'gerar PDF com tipografia de livro';                     marcado = $true },
    @{ id = 'tectonic'; proprio = $true; cmd = 'tectonic';      nome = 'Tectonic';    para = 'gerar PDF sem o MiKTeX: 20 MB, mais uns 50 MB de pacotes';   marcado = $false },
    @{ id = 'UB-Mannheim.TesseractOCR'; cmd = 'tesseract';     nome = 'Tesseract';   para = 'leitura clássica de páginas escaneadas (sinal extra)';  marcado = $false },
    @{ id = 'calibre.calibre';          cmd = 'ebook-convert'; nome = 'Calibre';     para = 'gerar AZW3, para Kindle antigo';                        marcado = $false })
$modelos = @(
    @{ nome = 'translategemma:12b';        gb = 7.3;  para = 'traduz';                                                                 marcado = $true },
    @{ nome = 'qwen3-vl:8b-instruct';      gb = 6.2;  para = 'confere a tradução e lê páginas escaneadas';                             marcado = $true },
    @{ nome = 'glm-ocr:latest';            gb = 1.4;  para = 'segundo leitor de páginas escaneadas, para conferir o primeiro';         marcado = $true },
    @{ nome = 'gemma4:26b';                gb = 18.1; para = 'auditor mais rigoroso; não cabe inteiro em placa de 12 GB, fica mais lento'; marcado = $false },
    @{ nome = 'qwen3-vl:30b-a3b-instruct'; gb = 19.6; para = 'juiz das disputas e trechos difíceis; lento em placas de até 12 GB';      marcado = $false })
foreach ($p in $programas) { $p.tem = Tem $p.cmd }
foreach ($p in $programas) { if ($p.proprio) { $p.tem = (Test-Path 'ferramentas\bin\tectonic.exe') -or (Tem 'tectonic') } }
$pastaModelos = if ($env:ESTANTE_MODELOS) { $env:ESTANTE_MODELOS } else { Join-Path $env:APPDATA 'Estante\modelos' }
$catalogo = Get-Content -Raw -Encoding UTF8 'app\modelos.json' | ConvertFrom-Json
foreach ($m in $modelos) {
    $c = $catalogo | Where-Object { $_.nome -eq $m.nome } | Select-Object -First 1
    $arqs = @($c.arquivo) + @($c.mmproj.arquivo) | Where-Object { $_ }
    if ($c) { $m.gb = [double]$c.gb }      # o tamanho de verdade é o do catálogo do app
    $m.tem = [bool]$c -and -not ($arqs | Where-Object { -not (Test-Path (Join-Path $pastaModelos $_)) })
}
$temWinget = Tem 'winget'

# ---------- janela ----------
$C = @{ fundo = [Drawing.Color]::FromArgb(18, 18, 18); sup = [Drawing.Color]::FromArgb(28, 28, 28); texto = [Drawing.Color]::FromArgb(242, 239, 232)
        apagado = [Drawing.Color]::FromArgb(154, 149, 139); acento = [Drawing.Color]::FromArgb(200, 41, 36); ok = [Drawing.Color]::FromArgb(127, 169, 138); alerta = [Drawing.Color]::FromArgb(212, 162, 74) }
function Fonte($tam, $estilo = 'Regular', $nome = 'Segoe UI') { New-Object Drawing.Font($nome, $tam, [Drawing.FontStyle]$estilo) }
function Texto($pai, $t, $x, $y, $w, $h, $fonte = (Fonte 10), $cor = $C.texto) {
    $l = New-Object Windows.Forms.Label; $l.Text = $t; $l.SetBounds($x, $y, $w, $h); $l.Font = $fonte; $l.ForeColor = $cor; $l.BackColor = [Drawing.Color]::Transparent
    $pai.Controls.Add($l); return $l
}
function Botao($t, $x, $cheio = $false) {
    $b = New-Object Windows.Forms.Button; $b.Text = $t; $b.SetBounds($x, 418, 130, 34); $b.FlatStyle = 'Flat'; $b.Font = Fonte 9 'Bold'; $b.Cursor = 'Hand'
    $b.ForeColor = $C.texto; $b.BackColor = $(if ($cheio) { $C.acento } else { $C.fundo }); $b.FlatAppearance.BorderColor = $(if ($cheio) { $C.acento } else { $C.apagado })
    $form.Controls.Add($b); return $b
}
# uma linha de opção: caixa de marcar, para que serve, e a situação à direita
function Linha($pai, $y, $item, $titulo, $situacao, $corSituacao, $travada) {
    $cx = New-Object Windows.Forms.CheckBox; $cx.Text = $titulo; $cx.SetBounds(4, $y, 300, 22); $cx.Font = Fonte 10 'Bold'; $cx.ForeColor = $C.texto; $cx.FlatStyle = 'Flat'
    $cx.Checked = [bool]($item.tem -or $item.necessario -or $item.marcado); $cx.AutoCheck = -not $travada
    $pai.Controls.Add($cx); $item.caixa = $cx
    [void](Texto $pai $item.para 24 ($y + 22) 440 18 (Fonte 9) $C.apagado)
    $s = Texto $pai $situacao 470 $y 190 20 (Fonte 9) $corSituacao; $s.TextAlign = 'TopRight'
}

$form = New-Object Windows.Forms.Form
$form.Text = 'Estante · instalação' + $(if ($Simular) { ' (simulação)' } else { '' }); $form.ClientSize = New-Object Drawing.Size(720, 470); $form.StartPosition = 'CenterScreen'
$icone = Join-Path $raiz 'desktop\build\icon.ico'
if (Test-Path $icone) { $form.Icon = New-Object Drawing.Icon $icone }
$form.FormBorderStyle = 'FixedDialog'; $form.MaximizeBox = $false; $form.BackColor = $C.fundo; $form.ForeColor = $C.texto; $form.Font = Fonte 10
[void](Texto $form 'E S T A N T E' 28 22 400 30 (Fonte 15 'Regular' 'Georgia'))
$passo = Texto $form '' 28 56 660 20 (Fonte 9) $C.apagado
$regua = New-Object Windows.Forms.Panel; $regua.SetBounds(28, 84, 664, 1); $regua.BackColor = $C.apagado; $form.Controls.Add($regua)

$paginas = @()
function Pagina { $p = New-Object Windows.Forms.Panel; $p.SetBounds(28, 98, 664, 306); $p.BackColor = $C.fundo; $p.Visible = $false; $form.Controls.Add($p); return $p }

# 0 · boas-vindas
$p0 = Pagina; $paginas += $p0
[void](Texto $p0 'Livros antigos, traduzidos e reeditados no seu computador.' 0 6 660 30 (Fonte 14 'Regular' 'Georgia'))
[void](Texto $p0 ("O Estante roda inteiro nesta máquina: sem conta, sem senha, sem enviar os seus livros a lugar nenhum.`n`n" +
    "Este instalador põe no computador o que o app precisa, prepara o app e o abre no fim.`n`n" +
    "Os programas são baixados dos sites oficiais pelo winget, do próprio Windows. Os modelos de IA são arquivos grandes: escolha na próxima tela quais quer agora; os outros o app baixa depois, na tela Modelos.") 0 50 650 170 (Fonte 10))
[void](Texto $p0 ('Pasta do app:  ' + $raiz) 0 250 660 20 (Fonte 9) $C.apagado)
if (-not $temWinget) { [void](Texto $p0 "O winget não foi encontrado. Instale o 'Instalador de Aplicativo' pela Microsoft Store e abra este instalador de novo." 0 274 660 30 (Fonte 9 'Bold') $C.alerta) }

# 1 · programas
$p1 = Pagina; $paginas += $p1
$y = 0
foreach ($p in $programas) {
    $sit = if ($p.tem) { 'já instalado' } elseif ($p.necessario) { 'necessário · será instalado' } else { 'opcional' }
    $cor = if ($p.tem) { $C.ok } elseif ($p.necessario) { $C.texto } else { $C.apagado }
    Linha $p1 $y $p $p.nome $sit $cor ([bool]($p.tem -or $p.necessario)); $y += 43
}

# 2 · modelos (quem já está instalado fica marcado e travado; os outros se escolhem)
$p2 = Pagina; $paginas += $p2
$y = 0
foreach ($m in $modelos) {
    $sit = if ($m.tem) { 'já instalado' } else { ('{0:N1} GB' -f $m.gb) }
    Linha $p2 $y $m $m.nome $sit $(if ($m.tem) { $C.ok } else { $C.apagado }) ([bool]$m.tem); $y += 44
}
$total = Texto $p2 '' 0 228 660 20 (Fonte 10 'Bold')
[void](Texto $p2 'Os modelos são baixados pelo próprio app, na tela Modelos. Sem eles o app abre e organiza os livros, mas não traduz.' 0 254 660 36 (Fonte 9) $C.apagado)
$unidade = Split-Path -Qualifier $pastaModelos
$livre = [math]::Round((Get-PSDrive -Name $unidade.TrimEnd(':')).Free / 1GB, 1)
function Soma {
    $gb = ($modelos | Where-Object { $_.caixa.Checked -and -not $_.tem } | ForEach-Object { $_.gb } | Measure-Object -Sum).Sum
    $total.Text = ('Para o app baixar: {0:N1} GB   ·   livre em {1} {2:N1} GB' -f [double]$gb, $unidade, $livre)
    $total.ForeColor = $(if ($gb -gt $livre) { $C.alerta } else { $C.texto })
}
foreach ($m in $modelos) { $m.caixa.Add_CheckedChanged({ Soma }) }
Soma

# 3 · instalando
$p3 = Pagina; $paginas += $p3
$agora = Texto $p3 '' 0 4 660 24 (Fonte 12 'Regular' 'Georgia')
$barra = New-Object Windows.Forms.ProgressBar; $barra.SetBounds(0, 40, 660, 10); $barra.Style = 'Continuous'; $barra.Maximum = 1000; $p3.Controls.Add($barra)
$detalhe = Texto $p3 '' 0 58 660 20 (Fonte 9) $C.apagado
$log = New-Object Windows.Forms.TextBox; $log.Multiline = $true; $log.ReadOnly = $true; $log.ScrollBars = 'Vertical'; $log.SetBounds(0, 86, 660, 216)
$log.BackColor = $C.sup; $log.ForeColor = $C.apagado; $log.BorderStyle = 'None'; $log.Font = Fonte 9 'Regular' 'Consolas'; $p3.Controls.Add($log)

# 4 · pronto
$p4 = Pagina; $paginas += $p4
$fim = Texto $p4 '' 0 6 660 34 (Fonte 14 'Regular' 'Georgia')
$fimDetalhe = Texto $p4 '' 0 52 660 230 (Fonte 10)

$TITULOS = @('Bem-vindo', 'Programas', 'Modelos de IA', 'Instalando', 'Pronto')
$bVoltar = Botao 'Voltar' 284; $bAvancar = Botao 'Avançar' 424 $true; $bFechar = Botao 'Cancelar' 564
$atual = 0
$passos = New-Object System.Collections.ArrayList

function MontaPassos {
    $passos.Clear()
    foreach ($p in $programas) { if ($p.caixa.Checked -and -not $p.tem -and -not $p.proprio) { [void]$passos.Add(@{ nome = "Instalando $($p.nome)"; exe = 'winget'; cmd = $p.cmd
        arg = "install --id $($p.id) -e --accept-source-agreements --accept-package-agreements --disable-interactivity" }) } }
    if (-not (Test-Path .venv\Scripts\python.exe)) {
        [void]$passos.Add(@{ nome = 'Criando o ambiente do app'; exe = 'python'; arg = '-m venv .venv' })
    }
    if (-not (Test-Path .venv\Scripts\uvicorn.exe)) {      # à parte do ambiente: se a rede caiu no meio, a próxima execução instala o que faltou
        [void]$passos.Add(@{ nome = 'Instalando as bibliotecas do app'; exe = '.venv\Scripts\python.exe'; arg = '-m pip install -q --disable-pip-version-check -r requirements.txt' })
    }
    # o motor de IA (llama.cpp) é baixado do GitHub oficial pelo próprio app, conferindo o hash; com placa NVIDIA vem também a versão de CUDA (uns 700 MB)
    if (-not (Test-Path 'ferramentas\llama\cpu\llama-server.exe') -or ((Tem 'nvidia-smi') -and -not (Test-Path 'ferramentas\llama\cuda\llama-server.exe'))) {
        [void]$passos.Add(@{ nome = 'Baixando o motor de IA (llama.cpp)'; exe = '.venv\Scripts\python.exe'; arg = 'app\motor.py --preparar' })
    }
    # o Tectonic não está no winget: o próprio app baixa o executável (conferindo o hash) e guarda os pacotes de que os livros precisam
    foreach ($p in $programas) { if ($p.proprio -and $p.caixa.Checked -and -not $p.tem) { [void]$passos.Add(@{ nome = 'Baixando o Tectonic e os pacotes de PDF'; exe = '.venv\Scripts\python.exe'; arg = 'ferramentas\construir.py --preparar-tectonic' }) } }
}
function Mostra($i) {
    $script:atual = $i
    for ($k = 0; $k -lt $paginas.Count; $k++) { $paginas[$k].Visible = ($k -eq $i) }
    $passo.Text = ('PASSO {0} DE {1}   ·   {2}' -f ($i + 1), $paginas.Count, $TITULOS[$i].ToUpper())
    $bVoltar.Visible = ($i -ge 1 -and $i -le 2)
    $bAvancar.Visible = ($i -le 2); $bAvancar.Text = $(if ($i -eq 2) { 'Instalar' } else { 'Avançar' }); $bAvancar.Enabled = $temWinget
    $bFechar.Text = $(if ($i -eq 4) { 'Fechar' } else { 'Cancelar' }); $bFechar.Enabled = ($i -ne 3)
}

# ---------- instalação: um passo por vez, em processo separado, para a janela não travar ----------
$relogio = New-Object Windows.Forms.Timer; $relogio.Interval = 400
$proc = $null; $saida = ''; $indice = 0; $falhas = New-Object System.Collections.ArrayList
function Diz($t) { $log.AppendText($t + "`r`n") }
function Inicia($p) {
    AtualizaPath
    $script:saida = [IO.Path]::GetTempFileName()
    $agora.Text = $p.nome + '…'; $detalhe.Text = ''; Diz ('> ' + $p.nome)
    $exe = $p.exe; $arg = $p.arg
    if (-not $Simular -and $exe -eq 'python' -and -not (Tem 'python')) {      # sem isto o Windows abriria a loja no lugar do Python recém-instalado
        Diz '  o Python acabou de ser instalado e ainda não aparece nesta janela'; [void]$falhas.Add($p.nome); $script:proc = $null; $script:indice++; return
    }
    if ($Simular) { $exe = 'cmd.exe'; $arg = "/c echo (simulado) $($p.exe) $($p.arg) & ping -n 2 127.0.0.1 >nul" }
    try { $script:proc = Start-Process -FilePath $exe -ArgumentList $arg -WindowStyle Hidden -PassThru -RedirectStandardOutput $script:saida -RedirectStandardError ($script:saida + '.err'); $null = $script:proc.Handle }      # sem guardar o Handle, o PowerShell 5.1 não devolve o código de saída
    catch { Diz ('  não foi possível iniciar: ' + $_.Exception.Message); [void]$falhas.Add($p.nome); $script:proc = $null; $script:indice++ }
}
function Termina {
    $relogio.Stop()
    $temApp = (Test-Path .venv\Scripts\python.exe)
    if ($falhas.Count) {
        $fim.Text = 'Quase lá.'; $fim.ForeColor = $C.alerta
        $fimDetalhe.Text = "Estes passos não terminaram:`n" + (($falhas | ForEach-Object { '  ·  ' + $_ }) -join "`n") +
            "`n`nO mais comum é o Windows só enxergar um programa recém-instalado numa janela nova. Feche esta janela e abra o instalar.bat de novo: ele continua de onde parou e pula o que já está pronto."
    } else {
        $fim.Text = $(if ($Simular) { 'Simulação concluída: nada foi instalado.' } else { 'O Estante está pronto.' })
        $fimDetalhe.Text = "O app abre agora, numa janela própria. Depois, abra por instalador\iniciar-app.bat.`n`nO app roda só neste computador. Para começar, solte um PDF ou EPUB na pasta livros, ou use o botão Novo livro."
        if (-not $Simular -and $temApp) { Start-Process (Join-Path $PSScriptRoot 'iniciar-app.bat') -WindowStyle Minimized }
    }
    Mostra 4
    if ($Auto) { Write-Host $log.Text; Write-Host ('FIM: ' + $fim.Text); $script:atual = 4; $form.Close() }
}
$relogio.Add_Tick({
    if ($null -eq $script:proc) {
        if ($script:indice -ge $passos.Count) { Termina; return }
        Inicia $passos[$script:indice]; return
    }
    $txt = ''
    try { $fs = [IO.File]::Open($script:saida, 'Open', 'Read', 'ReadWrite'); $r = New-Object IO.StreamReader($fs); $txt = $r.ReadToEnd(); $r.Close() } catch {}
    $ultima = ($txt -split "[`r`n]+" | Where-Object { $_.Trim() } | Select-Object -Last 1)
    if ($ultima) { $limpa = ($ultima -replace '[^\x20-\x7E -ɏ]', ' ').Trim(); $detalhe.Text = $limpa.Substring(0, [math]::Min(110, $limpa.Length)) }
    $pct = 0; if ($ultima -match '(\d{1,3})%') { $pct = [math]::Min(100, [int]$Matches[1]) }
    $barra.Value = [math]::Min(1000, [int](1000 * ($script:indice + $pct / 100) / [math]::Max(1, $passos.Count)))
    if ($script:proc.HasExited) {
        $p = $passos[$script:indice]; AtualizaPath
        $deu = ($script:proc.ExitCode -eq 0) -or ($p.cmd -and (Tem $p.cmd))
        if ($deu) { Diz '  ok' } else { Diz ('  não terminou (código ' + $script:proc.ExitCode + ')'); $e = Get-Content ($script:saida + '.err') -Raw -ErrorAction SilentlyContinue; if ($e) { Diz ('  ' + $e.Trim()) }; [void]$falhas.Add($p.nome) }
        $script:proc = $null; $script:indice++
    }
})

$bVoltar.Add_Click({ Mostra ($script:atual - 1) })
$bFechar.Add_Click({ $form.Close() })
$bAvancar.Add_Click({
    if ($script:atual -lt 2) { Mostra ($script:atual + 1); return }
    # botão Instalar: monta a lista do que falta e começa
    MontaPassos
    Mostra 3; $barra.Value = 0; $script:indice = 0; $falhas.Clear(); $log.Clear()
    if ($passos.Count) { Diz ('O que será feito: ' + (($passos | ForEach-Object { $_.nome }) -join ' · ')) } else { Diz 'Está tudo instalado. Nada a baixar.' }
    $relogio.Start()
})
$form.Add_FormClosing({ if ($script:atual -eq 3) { $_.Cancel = $true } })

Mostra $Pagina
if ($Teste) {      # desenha a página pedida num arquivo, fora da tela, e sai
    $form.StartPosition = 'Manual'; $form.Location = New-Object Drawing.Point(-3000, -3000); $form.ShowInTaskbar = $false; $form.Show(); $form.Refresh()
    $bmp = New-Object Drawing.Bitmap($form.Width, $form.Height); $form.DrawToBitmap($bmp, (New-Object Drawing.Rectangle(0, 0, $form.Width, $form.Height))); $bmp.Save($Teste); $form.Close()
    MontaPassos; Write-Host "pagina $Pagina desenhada; passos previstos: $($passos.Count)"; exit 0
}
if ($Auto -and $Simular) { $form.Add_Shown({ 1..3 | ForEach-Object { $bAvancar.PerformClick() } }) }
try { [void]$form.ShowDialog() }
catch { [void][Windows.Forms.MessageBox]::Show("O instalador parou com um erro:`n`n" + $_.Exception.Message, 'Estante') }
