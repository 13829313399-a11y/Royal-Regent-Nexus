import type { Router } from 'vue-router'

const GUARD_STATE_KEY = '__rr_browser_back_exit_guard__'

let isInstalled = false
let currentLockedFullPath = ''
let isBoundaryActive = false
let hasProcessedInitialLock = false
let guardStateSequence = 0

function canUseBrowserHistory() {
  return typeof window !== 'undefined'
    && typeof window.history?.pushState === 'function'
    && typeof window.history?.replaceState === 'function'
}

function shouldInstallExitBoundary() {
  return typeof window.history.length !== 'number' || window.history.length > 1
}

function buildGuardState(entryType: 'anchor' | 'trap') {
  const currentState = window.history.state
  const state = currentState && typeof currentState === 'object' ? currentState : {}

  return {
    ...state,
    [GUARD_STATE_KEY]: {
      entryType,
      sequence: ++guardStateSequence,
    },
  }
}

function writeGuardHistoryEntry(method: 'replaceState' | 'pushState', fullPath: string, entryType: 'anchor' | 'trap') {
  if (method === 'replaceState') {
    window.history.replaceState(buildGuardState(entryType), '', fullPath)
    return
  }

  window.history.pushState(buildGuardState(entryType), '', fullPath)
}

function readGuardEntryType() {
  const currentState = window.history.state
  if (!currentState || typeof currentState !== 'object') {
    return ''
  }

  const guardState = (currentState as Record<string, unknown>)[GUARD_STATE_KEY]
  if (!guardState || typeof guardState !== 'object') {
    return ''
  }

  const entryType = (guardState as { entryType?: unknown }).entryType
  return entryType === 'anchor' || entryType === 'trap' ? entryType : ''
}

function getBrowserFullPath(fallback: string) {
  const location = window.location
  const fullPath = `${location.pathname}${location.search}${location.hash}`

  return fullPath || fallback
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
      if (!currentLockedFullPath || readGuardEntryType() !== 'anchor') {
        return
      }

      const boundaryFullPath = getBrowserFullPath(currentLockedFullPath)

      writeGuardHistoryEntry('pushState', boundaryFullPath, 'trap')

      if (router.currentRoute.value.fullPath !== boundaryFullPath) {
        void router.replace(boundaryFullPath)
      }
    })
  }

  return {
    lock(fullPath: string) {
      currentLockedFullPath = fullPath
      if (isBoundaryActive || hasProcessedInitialLock) {
        return
      }

      hasProcessedInitialLock = true
      if (!shouldInstallExitBoundary()) {
        return
      }

      writeGuardHistoryEntry('replaceState', fullPath, 'anchor')
      writeGuardHistoryEntry('pushState', fullPath, 'trap')
      isBoundaryActive = true
    },
    unlock() {
      currentLockedFullPath = ''
      isBoundaryActive = false
      hasProcessedInitialLock = false
    },
  }
}
