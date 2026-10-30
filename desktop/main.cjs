const { app, BrowserWindow, Menu, shell } = require('electron');

const serviceUrl = process.env.LANTERN_URL || 'https://lantern-p2p.onrender.com';
let trustedOrigin;

try {
  const parsed = new URL(serviceUrl);
  if (parsed.protocol !== 'https:' && !['localhost', '127.0.0.1'].includes(parsed.hostname)) {
    throw new Error('LANTERN_URL must use HTTPS outside localhost.');
  }
  trustedOrigin = parsed.origin;
} catch (error) {
  app.whenReady().then(() => {
    const window = new BrowserWindow({ width: 560, height: 220, autoHideMenuBar: true });
    window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`<meta charset="utf-8"><style>body{font:16px system-ui;background:#101514;color:#eef2e9;padding:28px}code{color:#d3f17a}</style><h2>Lantern could not start</h2><p>${error.message}</p><p>Set <code>LANTERN_URL</code> to the HTTPS address of your Lantern service.</p>`)}`);
  });
}

function openExternal(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'https:') shell.openExternal(parsed.href);
  } catch { /* Reject malformed and non-web URLs. */ }
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1320,
    height: 900,
    minWidth: 720,
    minHeight: 620,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: '#0c1012',
    title: 'Lantern — direct file transfer',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      spellcheck: false
    }
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    openExternal(url);
    return { action: 'deny' };
  });
  window.webContents.on('will-navigate', (event, url) => {
    try {
      if (new URL(url).origin !== trustedOrigin) event.preventDefault();
    } catch { event.preventDefault(); }
  });
  window.once('ready-to-show', () => window.show());
  window.loadURL(trustedOrigin);
  return window;
}

if (trustedOrigin) {
  const gotLock = app.requestSingleInstanceLock();
  if (!gotLock) app.quit();
  else {
    app.whenReady().then(() => {
      app.setAppUserModelId('org.lanternp2p.desktop');
      Menu.setApplicationMenu(Menu.buildFromTemplate([
        {
          label: 'Lantern',
          submenu: [
            { label: 'Reload', accelerator: 'CmdOrCtrl+R', click: (_item, window) => window?.reload() },
            { label: 'Open Lantern in browser', click: () => openExternal(trustedOrigin) },
            { type: 'separator' },
            { role: 'quit' }
          ]
        },
        { label: 'Edit', submenu: [{ role: 'copy' }, { role: 'paste' }, { role: 'selectAll' }] },
        { label: 'View', submenu: [{ role: 'toggleDevTools' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }] }
      ]));
      createWindow();
      app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
      });
    });
    app.on('window-all-closed', () => {
      if (process.platform !== 'darwin') app.quit();
    });
  }
}
