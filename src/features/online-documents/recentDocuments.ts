export interface RecentDocument { id: string; opened: number }
export function recentKey(account: string, epoch: number, factory: string) {
  return `rr-online-documents-recent:${JSON.stringify([account, epoch, factory])}`
}
export function readRecent(key: string): RecentDocument[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
    if (!Array.isArray(value)) return []
    const seen = new Set<string>()
    return value.filter((v): v is RecentDocument => {
      if (!v || typeof v.id !== 'string' || !/^[a-zA-Z0-9-]{1,64}$/.test(v.id) || !Number.isFinite(v.opened) || v.opened <= 0 || seen.has(v.id)) return false
      seen.add(v.id); return true
    }).sort((a, b) => b.opened - a.opened).slice(0, 100)
  } catch { return [] }
}
export function rememberDocument(key: string, id: string, previous: RecentDocument[]) {
  const entries = [{ id, opened: Date.now() }, ...previous.filter(v => v.id !== id)].slice(0, 100)
  try { localStorage.setItem(key, JSON.stringify(entries)) } catch { /* Session-only recents remain usable when browser storage is unavailable. */ }
  return entries
}
