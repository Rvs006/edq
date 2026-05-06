const { autoUpdater } = require('electron-updater');
const { dialog } = require('electron');
const { version: currentVersion } = require('./package.json');

function setupUpdater(mainWindow) {
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.logger = {
    info: (msg) => console.info('[updater]', msg),
    warn: (msg) => console.warn('[updater]', msg),
    error: (msg) => console.error('[updater]', msg),
  };

  autoUpdater.on('checking-for-update', () => {
    console.info('[updater] Checking for updates...');
  });

  autoUpdater.on('update-available', (info) => {
    dialog
      .showMessageBox(mainWindow, {
        type: 'info',
        title: 'Update Available',
        message: `EDQ v${info.version} is available.`,
        detail: `A new version of EDQ is available. Would you like to download it now?\n\nCurrent: v${currentVersion}\nNew: v${info.version}`,
        buttons: ['Download', 'Later'],
        defaultId: 0,
      })
      .then(({ response }) => {
        if (response === 0) {
          autoUpdater.downloadUpdate();
        }
      });
  });

  autoUpdater.on('update-not-available', () => {
    console.info('[updater] No update available.');
  });

  autoUpdater.on('download-progress', (progress) => {
    const pct = Math.round(progress.percent);
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.setProgressBar(pct / 100);
    }
  });

  autoUpdater.on('update-downloaded', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.setProgressBar(-1);
    }

    dialog
      .showMessageBox(mainWindow, {
        type: 'info',
        title: 'Update Ready',
        message: 'Update downloaded successfully.',
        detail: 'The update has been downloaded. EDQ will restart to install the new version.',
        buttons: ['Restart Now', 'Later'],
        defaultId: 0,
      })
      .then(({ response }) => {
        if (response === 0) {
          autoUpdater.quitAndInstall(false, true);
        }
      });
  });

  autoUpdater.on('error', (err) => {
    console.error('[updater] Error:', err.message);
  });

  setTimeout(() => {
    autoUpdater.checkForUpdates().catch((err) => {
      console.info('[updater] Update check skipped:', err.message);
    });
  }, 10000);
}

module.exports = { setupUpdater };
