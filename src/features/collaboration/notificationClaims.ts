const CLAIM_LIMIT = 150
const DATABASE = 'rr-connect-notification-claims'
const STORE = 'claims'
const localClaims = new Map<string, string[]>()

function eventIds(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string').slice(-CLAIM_LIMIT) : []
}

function openClaimsDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1)
    let settled = false
    const fail = () => { if (!settled) { settled = true; clearTimeout(timer); reject(new Error('Notification storage unavailable')) } }
    const timer = setTimeout(fail, 3000)
    request.onblocked = fail
    request.onerror = fail
    request.onupgradeneeded = () => { request.result.createObjectStore(STORE) }
    request.onsuccess = () => {
      clearTimeout(timer)
      if (settled) { request.result.close(); return }
      settled = true
      request.result.onversionchange = () => request.result.close()
      resolve(request.result)
    }
  })
}

async function claimInDatabase(owner: string, id: string): Promise<boolean> {
  const database = await openClaimsDatabase()
  try {
    return await new Promise<boolean>((resolve, reject) => {
      // A readwrite transaction serializes competing windows, including plain HTTP.
      const transaction = database.transaction(STORE, 'readwrite')
      const store = transaction.objectStore(STORE)
      const request = store.get(owner)
      let claimed = false
      request.onsuccess = () => {
        const ids = eventIds(request.result)
        if (!ids.includes(id)) { store.put([...ids, id].slice(-CLAIM_LIMIT), owner); claimed = true }
      }
      transaction.oncomplete = () => resolve(claimed)
      transaction.onabort = () => reject(transaction.error ?? new Error('Notification claim aborted'))
      transaction.onerror = () => reject(transaction.error ?? new Error('Notification claim failed'))
    })
  } finally { database.close() }
}

function claimInFocusedWindow(owner: string, id: string): boolean {
  if (document.hidden || !document.hasFocus()) return false
  const ids = localClaims.get(owner) ?? []
  if (ids.includes(id)) return false
  localClaims.delete(owner)
  localClaims.set(owner, [...ids, id].slice(-CLAIM_LIMIT))
  if (localClaims.size > 8) localClaims.delete(localClaims.keys().next().value!)
  return true
}

export async function claimCollaborationNotification(owner: string, id: string): Promise<boolean> {
  if (!owner || !id) return false
  const key = `rr.connect.claims.${owner}`
  if (navigator.locks) {
    try {
      return await navigator.locks.request(key, () => {
        const ids = eventIds(JSON.parse(localStorage.getItem(key) || '[]'))
        if (ids.includes(id)) return false
        localStorage.setItem(key, JSON.stringify([...ids, id].slice(-CLAIM_LIMIT)))
        return true
      })
    } catch { /* Fall back when Web Locks or localStorage is unavailable. */ }
  }
  try { return await claimInDatabase(owner, id) }
  catch { return claimInFocusedWindow(owner, id) }
}
