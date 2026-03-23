const { Tray, Menu, nativeImage, BrowserWindow } = require('electron');
const path = require('path');

let tray = null;
let logsWindow = null;

function setupTray(mainWindow, dockerManager) {
  const iconPath = path.join(__dirname, 'assets', 'tray-icon.png');
  const icon = nativeImage.createFromPath(iconPath);
  tray = new Tray(icon.resize({ width: 22, height: 22 }));

  const buildMenu = () => {
    return Menu.buildFromTemplate([
      {
        label: 'Open EDQ',
        click: () => {
          mainWindow.show();
          mainWindow.focus();
        },
      },
      { type: 'separator' },
      {
        label: 'Restart Services',
        click: async () => {
          tray.setToolTip('EDQ — Restarting services...');
          try {
            await dockerManager.stopContainers();
            await dockerManager.startContainers();
            await dockerManager.waitForHealth();
            tray.setToolTip('EDQ — Device Qualifier');
          } catch (err) {
            const { dialog } = require('electron');
            dialog.showErrorBox('Restart Failed', err.message);
            tray.setToolTip('EDQ — Error');
          }
        },
      },
      {
        label: 'View Logs',
        click: async () => {
          if (logsWindow && !logsWindow.isDestroyed()) {
            logsWindow.focus();
            return;
          }

          logsWindow = new BrowserWindow({
            width: 900,
            height: 600,
            title: 'EDQ — Docker Logs',
            icon: path.join(__dirname, 'assets', 'icon.png'),
            backgroundColor: '#18181b',
            webPreferences: {
              nodeIntegration: false,
              contextIsolation: true,
            },
          });

          const logs = await dockerManager.getLogs(null, 200);
          const escaped = logs
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');

          const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>EDQ Logs</title>
  <style>
    body {
      margin: 0; padding: 16px;
      background: #18181b; color: #e4e4e7;
      font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
      font-size: 12px; line-height: 1.5;
    }
    pre { white-space: pre-wrap; word-wrap: break-word; margin: 0; }
    h2 { color: #f59e0b; font-size: 14px; margin: 0 0 12px; font-family: Inter, sans-serif; }
  </style>
</head>
<body>
  <h2>EDQ Docker Logs (last 200 lines)</h2>
  <pre>${escaped}</pre>
</body>
</html>`;

          logsWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
          logsWindow.setMenuBarVisibility(false);

          logsWindow.on('closed', () => {
            logsWindow = null;
          });
        },
      },
      {
        label: 'Container Status',
        click: async () => {
          const status = await dockerManager.getStatus();
          const { dialog } = require('electron');

          if (!status.length) {
            dialog.showMessageBox({
              type: 'warning',
              title: 'Container Status',
              message: 'No containers found',
              detail: 'EDQ containers may not be running.',
            });
            return;
          }

          const lines = status.map((c) => {
            const name = c.Name || c.Service || 'unknown';
            const state = c.State || c.Status || 'unknown';
            return `  ${name}: ${state}`;
          });

          dialog.showMessageBox({
            type: 'info',
            title: 'Container Status',
            message: 'EDQ Service Status',
            detail: lines.join('\n'),
          });
        },
      },
      { type: 'separator' },
      {
        label: 'Quit EDQ',
        click: async () => {
          tray.setToolTip('EDQ — Shutting down...');
          const { app } = require('electron');
          app.quit();
        },
      },
    ]);
  };

  tray.setToolTip('EDQ — Device Qualifier');
  tray.setContextMenu(buildMenu());

  tray.on('click', () => {
    if (mainWindow.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  tray.on('right-click', () => {
    tray.setContextMenu(buildMenu());
  });
}

module.exports = { setupTray };
