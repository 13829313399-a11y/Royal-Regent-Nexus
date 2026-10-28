import { afterEach, describe, expect, it, vi } from 'vitest'
import { readRecent, recentKey, rememberDocument } from './recentDocuments'

afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })
describe('本机最近文档', () => {
  it('separates accounts, employment epochs and factories without persisting titles', () => {
    const key = recentKey('a', 1, 'group')
    rememberDocument(key, 'doc-1', [])
    expect(readRecent(key).map(v => v.id)).toEqual(['doc-1'])
    for (const other of [recentKey('b', 1, 'group'), recentKey('a', 2, 'group'), recentKey('a', 1, 'huaxing')]) expect(readRecent(other)).toEqual([])
    expect(Object.keys(readRecent(key)[0]!)).toEqual(['id', 'opened'])
  })
  it('deduplicates, caps and rejects malformed browser storage', () => {
    const key = recentKey('a', 1, 'group')
    const entries = Array.from({ length: 110 }, (_, i) => ({ id: `d${i}`, opened: i + 1 }))
    localStorage.setItem(key, JSON.stringify([...entries, { id: 'bad/path', opened: 4 }, null]))
    expect(readRecent(key)).toHaveLength(100)
    const next = rememberDocument(key, 'd109', readRecent(key))
    expect(next.filter(v => v.id === 'd109')).toHaveLength(1)
    localStorage.setItem(key, '{broken')
    expect(readRecent(key)).toEqual([])
  })
  it('keeps session recents when browser persistence is unavailable', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    expect(rememberDocument('key', 'doc', [])[0]?.id).toBe('doc')
  })
})
