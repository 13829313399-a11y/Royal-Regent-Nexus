import { afterEach, describe, expect, it, vi } from 'vitest'
import { writeSpreadsheetClipboard } from '../spreadsheetClipboard'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
const data = { text: '00123\t77780', html: '<table><tr><td x:str>00123</td><td x:str>77780</td></tr></table>' }
describe('spreadsheet clipboard', () => {
  it('writes both formats without adding apostrophes', async () => {
    const write = vi.fn().mockResolvedValue(undefined)
    const items: Record<string, Blob>[] = []
    vi.stubGlobal('navigator', { clipboard: { write } })
    vi.stubGlobal('ClipboardItem', class { constructor(value: Record<string, Blob>) { items.push(value) } })
    expect(await writeSpreadsheetClipboard(data)).toBe('rich')
    expect(write).toHaveBeenCalledOnce()
    expect(Object.keys(items[0]!)).toEqual(['text/plain', 'text/html'])
  })
  it('uses a copy event for older HTTP browsers and never renders source HTML', async () => {
    vi.stubGlobal('navigator', {})
    const setData = vi.fn()
    const exec = vi.fn(() => {
      const event = new Event('copy', { cancelable: true })
      Object.defineProperty(event, 'clipboardData', { value: { setData } })
      document.dispatchEvent(event)
      return true
    })
    const old = document.execCommand
    document.execCommand = exec
    try {
      expect(await writeSpreadsheetClipboard(data)).toBe('rich')
      expect(setData).toHaveBeenCalledWith('text/plain', data.text)
      expect(setData).toHaveBeenCalledWith('text/html', data.html)
      expect(document.querySelector('table')).toBeNull()
      setData.mockClear(); document.dispatchEvent(new Event('copy'))
      expect(setData).not.toHaveBeenCalled()
    } finally { document.execCommand = old }
  })
  it('falls back to raw text for old saved responses', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    expect(await writeSpreadsheetClipboard({ text: data.text })).toBe('plain')
    expect(writeText).toHaveBeenCalledWith('00123\t77780')
  })
  it('tries plain fallback if the modern HTML clipboard is rejected', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { write: vi.fn().mockRejectedValue(new Error('unsupported MIME')), writeText } })
    vi.stubGlobal('ClipboardItem', class {})
    expect(await writeSpreadsheetClipboard(data)).toBe('plain')
    expect(writeText).toHaveBeenCalledWith(data.text)
  })
})
