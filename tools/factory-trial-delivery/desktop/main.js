'use strict'
const { app, BrowserWindow, session, dialog } = require('electron')
const path = require('path')
const root = path.resolve(__dirname, '..')
const address = process.argv.find(value => /^http:\/\/127\.0\.0\.1:\d+\/$/.test(value))
const instance = process.argv.find(value => /^--trial-instance=[a-f0-9]{32}$/.test(value))
if (!address || !instance) app.exit(2)
else {
  const origin = new URL(address).origin
  // A stale window from a stopped backend must not steal a new backend's lock.
  // Business records remain in data; this subdirectory only holds browser cache.
  app.setPath('userData', path.join(root, 'data', 'browser', instance.split('=')[1]))
  if (!app.requestSingleInstanceLock()) app.quit()
  else {
  let currentWindow = null
  app.on('second-instance', () => {
    if (currentWindow) {
      if (currentWindow.isMinimized()) currentWindow.restore()
      currentWindow.show()
      currentWindow.focus()
    }
  })
  // Some Win7 display drivers cannot initialize Chromium's GPU process.
  app.disableHardwareAcceleration()
  app.whenReady().then(() => {
    const local = session.fromPartition('persist:local-orders')
    local.setPermissionRequestHandler((_contents, _permission, callback) => callback(false))
    local.webRequest.onBeforeRequest((details, callback) => {
      const permitted = details.url.startsWith(origin + '/') || /^(blob:|data:)/.test(details.url)
      callback({ cancel: !permitted })
    })
    const window = new BrowserWindow({ width: 1366, height: 900, minWidth: 900, minHeight: 600,
      title: '客户订单中心 · 本机试用', autoHideMenuBar: true,
      webPreferences: { session: local, nodeIntegration: false, contextIsolation: true, sandbox: true } })
    currentWindow = window
    window.on('closed', () => { currentWindow = null })
    window.webContents.setWindowOpenHandler(({ url }) => {
      const target = new URL(url)
      // The shared ledger opens its retained original documents in a new tab.
      // Download those through this local session instead of silently dropping it.
      if (target.origin === origin && target.pathname.startsWith('/api/customer-order-ledger/sources/')) {
        window.webContents.downloadURL(url)
      }
      return { action: 'deny' }
    })
    window.webContents.on('will-navigate', (event, target) => {
      if (new URL(target).origin !== origin) event.preventDefault()
    })
    window.webContents.on('did-fail-load', (_event, code, description) => {
      if (code !== -3) dialog.showErrorBox('页面未能打开', '本机服务连接失败，请重新打开试用程序。\n' + description)
    })
    window.loadURL(address)
  })
  app.on('window-all-closed', () => app.quit())
  }
}
