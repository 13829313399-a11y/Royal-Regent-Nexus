import type { Router } from 'vue-router'

const GUARD_STATE_KEY = '__rr_browser_back_exit_guard__'

let isInstalled = false
let currentLockedFullPath = ''
let lastWrittenFullPath = ''

function canUseBrowserHistory() {
  return typeof window !== 'undefined' && typeof window.history?.pushState === 'function'
}

function buildGuardState() {
  const currentState = window.history.state
  const state = currentState && typeof currentState === 'object' ? currentState : {}

  return {
    ...state,
    [GUARD_STATE_KEY]: true,
  }
}

function writeGuardHistoryEntry(method: 'replaceState' | 'pushState', fullPath: string) {
  if (method === 'replaceState') {
    window.history.replaceState(buildGuardState(), '', fullPath)
    return
  }

  window.history.pushState(buildGuardState(), '', fullPath)
}

export function installBrowserBackExitGuard(router: Router) {
  if (!canUseBrowserHistory()) {
    return {
      lock(fullPath: string) {
        currentLockedFullPath = fullPath
      },
      unlock() {
        currentLockedFullPath = ''
      },
    }
  }

  if (!isInstalled) {
    isInstalled = true

    window.addEventListener('popstate', () => {
      if (!currentLockedFullPath) {
        return
      }

      writeGuardHistoryEntry('pushState', currentLockedFullPath)

      if (router.currentRoute.value.fullPath !== currentLockedFullPath) {
        void router.replace(currentLockedFullPath)
      }
    })
  }

  return {
    lock(fullPath: string) {
      currentLockedFullPath = fullPath
      if (lastWrittenFullPath === fullPath && window.history.state?.[GUARD_STATE_KEY]) {
        return
      }

      writeGuardHistoryEntry('replaceState', fullPath)
      writeGuardHistoryEntry('pushState', fullPath)
      lastWrittenFullPath = fullPath
    },
    unlock() {
      currentLockedFullPath = ''
      lastWrittenFullPath = ''
    },
  }
}
