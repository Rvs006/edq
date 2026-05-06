const { autoUpdater } = require('electron-updater');
const { dialog, Notification } = require('electron');

function writeUpdaterLog(level, message) {
  const text = message instanceof Error ? message.message : String(message);
  const stream = level === 'info' ? process.stdout : process.stderr;
  stream.write(`[updater] ${text}\n`);
}

function setupUpdater(mainWindow) {
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.logger = {
    info: (msg) => writeUpdaterLog('info', msg),
    warn: (msg) => writeUpdaterLog('warn', msg),
    error: (msg) => writeUpdaterLog('error', msg),
  };

  autoUpdater.on('checking-for-update', () => {
    writeUpdaterLog('info', 'Checking for updates...');
  });

  autoUpdater.on('update-available', (info) => {
    dialog
      .showMessageBox(mainWindow, {
        type: 'info',
        title: 'Update Available',
        message: `EDQ v${info.version} is available.`,
        detail: `A new version of EDQ is available. Would you like to download it now?\n\nCurrent: v${require('./package.json').version}\nNew: v${info.version}`,
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
    writeUpdaterLog('info', 'No update available.');
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
    writeUpdaterLog('error', `Error: ${err.message}`);
  });

  setTimeout(() => {
    autoUpdater.checkForUpdates().catch((err) => {
      writeUpdaterLog('info', `Update check skipped: ${err.message}`);
    });
  }, 10000);
}

module.exports = { setupUpdater };
