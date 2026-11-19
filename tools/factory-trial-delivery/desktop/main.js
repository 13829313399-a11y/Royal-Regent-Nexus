'use strict'
const { app, BrowserWindow, session, dialog } = require('electron')
const path = require('path')
const root = path.resolve(__dirname, '..')
const address = process.argv.find(value => /^http:\/\/127\.0\.0\.1:\d+\/$/.test(value))
if (!address) app.exit(2)
else {
  const origin = new URL(address).origin
  app.setPath('userData', path.join(root, 'data', 'browser'))
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
      title: '华康A · Green Toys 订单排期', autoHideMenuBar: true,
      webPreferences: { session: local, nodeIntegration: false, contextIsolation: true, sandbox: true } })
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
      if (code !== -3) dialog.showErrorBox('页面未能打开', '请保持 START.cmd 窗口打开。\n' + description)
    })
    window.loadURL(address)
  })
  app.on('window-all-closed', () => app.quit())
}
