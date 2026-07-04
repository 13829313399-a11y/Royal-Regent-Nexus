import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { installBrowserBackExitGuard } from '../../lib/browserBackExitGuard.js'

const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')
const guardSource = readFileSync(join(process.cwd(), 'src/lib/browserBackExitGuard.ts'), 'utf8')

assert.match(routerSource, /installBrowserBackExitGuard/)
assert.match(routerSource, /browserBackExitGuard\.lock\(to\.fullPath\)/)
assert.match(routerSource, /browserBackExitGuard\.unlock\(\)/)

for (const requiredImplementation of [
  'popstate',
  'history.pushState',
  'history.replaceState',
  'currentLockedFullPath',
  'isBoundaryActive',
  'readGuardEntryType',
  'window.history.length',
  'router\\.replace\\(boundaryFullPath\\)',
  '__rr_browser_back_exit_guard__',
]) {
  assert.match(guardSource, new RegExp(requiredImplementation))
}

type PopStateListener = () => void

interface HistoryEntry {
  state: Record<string, unknown>
  url: string
}

function createBackExitProbe() {
  const listeners: PopStateListener[] = []
  const historyStack: HistoryEntry[] = [
    { state: { page: 'outside' }, url: 'https://outside.example/' },
    { state: { page: 'app' }, url: '/' },
  ]
  const location = {
    pathname: '/',
    search: '',
    hash: '',
  }
  let position = historyStack.length - 1
  let exited = false

  function setLocation(url: string) {
    const parsed = new URL(url, 'https://app.local')
    location.pathname = parsed.pathname
    location.search = parsed.search
    location.hash = parsed.hash
  }

  const history = {
    get length() {
      return historyStack.length
    },
    get state() {
      return historyStack[position]?.state
    },
    pushState(state: Record<string, unknown>, _title: string, url: string) {
      historyStack.splice(position + 1)
      historyStack.push({ state: { ...state }, url })
      position = historyStack.length - 1
      setLocation(url)
    },
    replaceState(state: Record<string, unknown>, _title: string, url: string) {
      historyStack[position] = { state: { ...state }, url }
      setLocation(url)
    },
    back() {
      if (position === 0) {
        exited = true
        return
      }

      const from = historyStack[position]
      position -= 1
      const to = historyStack[position]

      if (!to.url.startsWith('/')) {
        exited = true
        return
      }

      setLocation(to.url)
      const stateChanged = JSON.stringify(from.state) !== JSON.stringify(to.state)
      if (from.url !== to.url || stateChanged) {
        listeners.forEach((listener) => listener())
      }
    },
  }

  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      history,
      location,
      addEventListener(eventName: string, listener: PopStateListener) {
        if (eventName === 'popstate') {
          listeners.push(listener)
        }
      },
    },
  })

  return {
    history,
    navigate(url: string) {
      history.pushState({ page: url }, '', url)
    },
    back() {
      history.back()
    },
    get currentFullPath() {
      return `${location.pathname}${location.search}${location.hash}`
    },
    get exited() {
      return exited
    },
  }
}

const probe = createBackExitProbe()
const replacements: string[] = []
const router = {
  currentRoute: { value: { fullPath: '/' } },
  replace(fullPath: string) {
    replacements.push(fullPath)
    router.currentRoute.value.fullPath = fullPath
  },
}

const guard = installBrowserBackExitGuard(router)

guard.lock('/')

probe.navigate('/modules/molding-sample')
router.currentRoute.value.fullPath = '/modules/molding-sample'
guard.lock('/modules/molding-sample')

probe.back()
assert.equal(probe.currentFullPath, '/')
assert.deepEqual(replacements, [])

probe.back()

assert.equal(probe.exited, false)
assert.equal(probe.currentFullPath, '/')
assert.deepEqual(replacements, ['/'])
