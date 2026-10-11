const key = 'rr:last-login-account'
export interface LastLoginAccount { username: string; displayName: string; savedAt: string }
export function readRecentAccount(): LastLoginAccount | null {
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return null
    const value = JSON.parse(raw)
    if (typeof value.username !== 'string' || !value.username.trim()) return null
    return { username: value.username.trim(), displayName: typeof value.displayName === 'string' ? value.displayName : '', savedAt: typeof value.savedAt === 'string' ? value.savedAt : '' }
  } catch { return null }
}
export function saveRecentAccount(user: { username: string; display_name?: string }) {
  try { window.localStorage.setItem(key, JSON.stringify({ username: user.username, displayName: user.display_name || user.username, savedAt: new Date().toISOString() })) } catch { /* Preferences never change authentication success. */ }
}
export function removeRecentAccount() {
  try { window.localStorage.removeItem(key) } catch { /* Restricted browsers can still sign in. */ }
}
// One handoff in memory, never a URL or persistent profile store.
let registrationUsername = ''
export function handoffRegistrationUsername(value: string) { registrationUsername = value }
export function takeRegistrationUsername() { const value = registrationUsername; registrationUsername = ''; return value }
