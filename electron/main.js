const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require('electron');
const path = require('path');
const DockerManager = require('./docker-manager');
const { setupTray } = require('./tray');
const { setupUpdater } = require('./updater');

let mainWindow = null;
let splashWindow = null;
const dockerManager = new DockerManager();

const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
}

app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

app.on('ready', async () => {
  splashWindow = createSplashWindow();

  const dockerAvailable = await dockerManager.checkDocker();
  if (!dockerAvailable) {
    if (splashWindow) {
      splashWindow.close();
      splashWindow = null;
    }
    await showDockerInstallGuide();
    app.quit();
    return;
  }

  updateSplashStatus('Starting Docker containers...');

  try {
    await dockerManager.startContainers((line) => {
      updateSplashStatus(line);
    });
  } catch (err) {
    if (splashWindow) {
      splashWindow.close();
      splashWindow = null;
    }
    dialog.showErrorBox(
      'EDQ Startup Error',
      `Failed to start services:\n\n${err.message}\n\nMake sure Docker Desktop is running and try again.`
    );
    app.quit();
    return;
  }

  updateSplashStatus('Waiting for services to become healthy...');

  try {
    await dockerManager.waitForHealth(120000, (status) => {
      updateSplashStatus(status);
    });
  } catch (err) {
    if (splashWindow) {
      splashWindow.close();
      splashWindow = null;
    }
    dialog.showErrorBox(
      'EDQ Startup Error',
      `Services did not become healthy:\n\n${err.message}`
    );
    await dockerManager.stopContainers();
    app.quit();
    return;
  }

  updateSplashStatus('Ready!');

  mainWindow = createMainWindow();

  mainWindow.webContents.on('did-finish-load', () => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close();
      splashWindow = null;
    }
    mainWindow.show();
  });

  mainWindow.webContents.on('did-fail-load', (_e, code, desc) => {
    if (code !== -3) {
      setTimeout(() => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.loadURL('http://localhost:80');
        }
      }, 2000);
    }
  });

  mainWindow.on('close', (e) => {
    if (process.platform === 'darwin') {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  setupTray(mainWindow, dockerManager);
  setupUpdater(mainWindow);
  registerIpcHandlers();

  const menu = Menu.buildFromTemplate([
    {
      label: 'EDQ',
      submenu: [
        { role: 'about' },
        { type: 'separator' },
        {
          label: 'Open DevTools',
          accelerator: 'CmdOrCtrl+Shift+I',
          click: () => {
            if (mainWindow) mainWindow.webContents.openDevTools();
          },
        },
        { type: 'separator' },
        { role: 'quit' },
      ],
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
  ]);
  Menu.setApplicationMenu(menu);
});

app.on('before-quit', async (e) => {
  e.preventDefault();
  try {
    await dockerManager.stopContainers();
  } catch (_) {}
  app.exit(0);
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow) {
    mainWindow.show();
  }
});

function createSplashWindow() {
  const win = new BrowserWindow({
    width: 420,
    height: 320,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    center: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  win.loadFile(path.join(__dirname, 'splash.html'));
  return win;
}

function createMainWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    title: 'EDQ — Device Qualifier',
    icon: path.join(__dirname, 'assets', 'icon.png'),
    backgroundColor: '#0f172a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  win.loadURL('http://localhost:80');
  return win;
}

function updateSplashStatus(text) {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents
      .executeJavaScript(
        `document.getElementById('status-text') && (document.getElementById('status-text').textContent = ${JSON.stringify(text)})`
      )
      .catch(() => {});
  }
}

function registerIpcHandlers() {
  ipcMain.handle('get-app-version', () => app.getVersion());

  ipcMain.handle('get-docker-status', async () => {
    return dockerManager.getStatus();
  });

  ipcMain.handle('restart-services', async () => {
    await dockerManager.stopContainers();
    await dockerManager.startContainers();
    await dockerManager.waitForHealth();
    return { success: true };
  });
}

async function showDockerInstallGuide() {
  const { response } = await dialog.showMessageBox({
    type: 'warning',
    title: 'Docker Desktop Required',
    message: 'EDQ requires Docker Desktop to run security scanning tools.',
    detail:
      'Docker Desktop must be installed and running before using EDQ.\n\nWould you like to download Docker Desktop now?',
    buttons: ['Download Docker', 'Cancel'],
    defaultId: 0,
  });
  if (response === 0) {
    shell.openExternal('https://www.docker.com/products/docker-desktop/');
  }
}
