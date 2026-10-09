// Estante: programa de janela própria. O Electron traz o próprio Chromium (não depende do Edge nem do Chrome instalados).
// O processo principal sobe o servidor Python do app escondido, espera ele responder e abre a janela. Sair encerra o servidor.
const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');
const http = require('node:http');

// Instalado: a pasta resources/ do programa (Python, app, ferramentas, bin). Em desenvolvimento: a pasta do projeto.
const EMPACOTADO = app.isPackaged;
const RAIZ = EMPACOTADO ? process.resourcesPath : path.resolve(__dirname, '..');
const PYTHON = EMPACOTADO
  ? path.join(RAIZ, 'python', 'python.exe')                       // Python embutido, dentro do instalador
  : path.join(RAIZ, '.venv', 'Scripts', 'python.exe');           // ambiente do projeto, no desenvolvimento
const PORTA_PADRAO = 8765;

let servidor = null;      // processo Python
let janela = null;
let encerrando = false;

// Instalado: a biblioteca fica em %APPDATA%\Estante\livros, e não dentro da pasta do instalador (desinstalar não apaga os livros).
// A pasta livros/ do programa vira um atalho de pasta (junção) para lá. Se já houver livros na pasta do programa, não mexe.
function liga_biblioteca() {
  if (!EMPACOTADO) return;
  const dados = path.join(app.getPath('userData'), 'livros');
  const aqui = path.join(RAIZ, 'livros');
  fs.mkdirSync(dados, { recursive: true });
  try {
    if (fs.lstatSync(aqui).isSymbolicLink()) return;      // já ligada
    if (fs.readdirSync(aqui).length) return;               // há livros aqui: não mexe
    fs.rmdirSync(aqui);
  } catch { /* não existe ainda */ }
  fs.symlinkSync(dados, aqui, 'junction');
}

// primeira porta livre a partir da padrão (se o app antigo ainda estiver rodando em 8765, usa a seguinte)
function porta_livre(inicio) {
  return new Promise((resolve) => {
    const s = net.createServer();
    s.once('error', () => resolve(porta_livre(inicio + 1)));
    s.listen(inicio, '127.0.0.1', () => s.close(() => resolve(inicio)));
  });
}

function espera_servidor(porta, tentativas = 300) {
  return new Promise((resolve, reject) => {
    const tenta = (n) => {
      http.get({ host: '127.0.0.1', port: porta, path: '/api/livros', timeout: 1000 }, (r) => {
        r.resume(); resolve();
      }).on('error', () => {
        if (n <= 0) return reject(new Error('o servidor não respondeu em 30 s'));
        setTimeout(() => tenta(n - 1), 100);
      }).on('timeout', function () { this.destroy(); });
    };
    tenta(tentativas);
  });
}

function sobe_servidor(porta) {
  // o instalador não leva pastas vazias: app/dados pode não existir (e sem ela o programa abria sem janela, sem aviso)
  fs.mkdirSync(path.join(RAIZ, 'app', 'dados'), { recursive: true });
  const log = fs.openSync(path.join(RAIZ, 'app', 'dados', 'estante.log'), 'a');
  servidor = spawn(PYTHON, [path.join(RAIZ, 'app', 'servidor.py')], {
    cwd: RAIZ,
    env: {
      ...process.env,
      ESTANTE_PORTA: String(porta),
      // os modelos (vários GB, baixados na primeira abertura) ficam junto dos livros, em %APPDATA%\Estante, e não na pasta do programa.
      // ESTANTE_MODELOS, se já estiver definida, manda (para apontar para outro disco)
      ESTANTE_MODELOS: process.env.ESTANTE_MODELOS || path.join(app.getPath('userData'), 'modelos'),
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
      // o Pandoc e o Tectonic ficam em ferramentas/bin: o app os encontra pelo PATH, como se estivessem instalados
      PATH: path.join(RAIZ, 'ferramentas', 'bin') + path.delimiter + (process.env.PATH || ''),
    },
    windowsHide: true,
    stdio: ['ignore', log, log],
  });
  servidor.on('exit', (codigo) => {
    servidor = null;
    if (!encerrando) dialog.showErrorBox('Estante', `O servidor parou (código ${codigo}). Veja app/dados/estante.log.`);
  });
}

// mata o servidor e os filhos dele (no Windows, taskkill /T mata a árvore)
function para_servidor() {
  if (!servidor) return;
  try { execFileSync('taskkill', ['/pid', String(servidor.pid), '/T', '/F'], { windowsHide: true }); } catch { /* já saiu */ }
  servidor = null;
}

function cria_janela(porta) {
  janela = new BrowserWindow({
    width: 1200,
    height: 820,
    minWidth: 480,
    minHeight: 480,
    title: 'Estante',
    icon: path.join(__dirname, 'build', 'icon.png'),
    backgroundColor: '#121212',
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  janela.once('ready-to-show', () => janela.show());
  janela.on('closed', () => { janela = null; });
  // links para fora do app abrem no navegador padrão, e não numa aba nova do programa
  janela.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
  janela.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith(`http://127.0.0.1:${porta}/`)) { e.preventDefault(); shell.openExternal(url); }
  });
  janela.loadURL(`http://127.0.0.1:${porta}/`);
}

ipcMain.handle('reiniciar', () => {
  // o app reabre sozinho: relança o próprio programa e encerra este processo
  encerrando = true;
  app.relaunch();
  app.exit(0);
});

// Desinstalar pela tela de Configurações: tira os modelos baixados, desfaz o atalho de pasta da biblioteca e chama o desinstalador do Windows.
// A biblioteca (livros e traduções) só é apagada se a pessoa marcar: é o trabalho dela, não veio com o programa.
ipcMain.handle('desinstalar', (_e, opcoes) => {
  if (!EMPACOTADO) return { ok: false, erro: 'Só o programa instalado pode ser desinstalado por aqui.' };
  const desinstalador = path.join(path.dirname(process.execPath), 'Uninstall Estante.exe');
  if (!fs.existsSync(desinstalador)) return { ok: false, erro: 'Não encontrei o desinstalador na pasta do programa.' };
  encerrando = true;
  para_servidor();
  const dados = app.getPath('userData');
  // modelos: só os arquivos do catálogo (e os pedaços de download), nunca a pasta inteira, que pode ser de outra coisa
  const pasta = process.env.ESTANTE_MODELOS || path.join(dados, 'modelos');
  try {
    const catalogo = JSON.parse(fs.readFileSync(path.join(RAIZ, 'app', 'modelos.json'), 'utf8'));
    for (const m of catalogo) {
      for (const nome of [m.arquivo, m.mmproj && m.mmproj.arquivo].filter(Boolean)) {
        for (const alvo of [nome, nome + '.part']) fs.rmSync(path.join(pasta, alvo), { force: true });
      }
    }
    if (fs.existsSync(pasta) && !fs.readdirSync(pasta).length) fs.rmdirSync(pasta);
  } catch { /* sem catálogo ou sem pasta: nada a apagar */ }
  // o atalho de pasta resources/livros aponta para a biblioteca: sai só o atalho, para o desinstalador não seguir por ele
  const atalho = path.join(RAIZ, 'livros');
  try { if (fs.lstatSync(atalho).isSymbolicLink()) fs.rmdirSync(atalho); } catch { /* não havia atalho */ }
  if (opcoes && opcoes.biblioteca === true) fs.rmSync(path.join(dados, 'livros'), { recursive: true, force: true });
  spawn(desinstalador, [], { detached: true, stdio: 'ignore' }).unref();
  app.exit(0);
  return { ok: true };
});

// uma instância só: se o programa já estiver aberto, a segunda abertura só traz a janela da frente
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => { if (janela) { if (janela.isMinimized()) janela.restore(); janela.focus(); } });

  app.whenReady().then(async () => {
    try {
      await inicia();
    } catch (e) {
      // sem isto, uma falha aqui fechava o programa em silêncio
      dialog.showErrorBox('Estante', `Não consegui iniciar: ${e.message}`);
      para_servidor();
      app.quit();
    }
  });

  async function inicia() {
    const porta = await porta_livre(Number(process.env.ESTANTE_PORTA) || PORTA_PADRAO);
    if (!fs.existsSync(PYTHON)) {
      dialog.showErrorBox('Estante', 'Não encontrei o ambiente Python do app (.venv). Rode o instalador antes.');
      app.quit();
      return;
    }
    liga_biblioteca();
    sobe_servidor(porta);
    try {
      await espera_servidor(porta);
    } catch (e) {
      dialog.showErrorBox('Estante', String(e.message));
      para_servidor();
      app.quit();
      return;
    }
    cria_janela(porta);
  }

  app.on('window-all-closed', () => app.quit());
  app.on('before-quit', () => { encerrando = true; para_servidor(); });
}
