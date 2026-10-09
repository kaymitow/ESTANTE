// Ponte mínima entre a tela e o programa: a tela só ganha o que precisa (reiniciar), sem acesso ao sistema.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('estante', {
  programa: true,
  reiniciar: () => ipcRenderer.invoke('reiniciar'),
  desinstalar: (opcoes) => ipcRenderer.invoke('desinstalar', opcoes),
});
