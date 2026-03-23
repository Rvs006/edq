const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('edqDesktop', {
  isDesktopApp: true,
  platform: process.platform,
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  getDockerStatus: () => ipcRenderer.invoke('get-docker-status'),
  restartServices: () => ipcRenderer.invoke('restart-services'),
});
