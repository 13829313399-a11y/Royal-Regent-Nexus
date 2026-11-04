import { describe, expect, it, vi } from 'vitest'
import { saveUploadQueue, uploadSelection, validateUploadFiles, type QueuedUpload } from '../quickUploadQueue'
import type { QuickAsset } from '@/api/cartonQuickAssets'

function row(id: string): QueuedUpload {
  return { ...uploadSelection(), id, file: new File([id], `${id}.pdf`), state: 'pending', error: '' }
}
function request(source: QueuedUpload) {
  return { factory: 'huaxing', file: source.file, body: { request_id: `request-${source.id}`, owner_department: 'sales-business' as const,
    text: '', contract_number: source.contract, association: 'NONE' as const, status: 'PENDING' as const } }
}
function asset(id: string) { return { id } as QuickAsset }
function sized(size: number) { const file = new File(['x'], 'source.pdf'); Object.defineProperty(file, 'size', { value: size }); return file }

describe('file queue limits', () => {
  it('checks file count, total bytes and each source before adding files', () => {
    expect(validateUploadFiles(Array.from({ length: 50 }, () => sized(1)))).toBe('')
    expect(validateUploadFiles(Array.from({ length: 51 }, () => sized(1)))).toContain('50')
    expect(validateUploadFiles(Array.from({ length: 5 }, () => sized(20 * 1024 * 1024)))).toBe('')
    expect(validateUploadFiles(Array.from({ length: 6 }, () => sized(20 * 1024 * 1024)))).toContain('100MB')
    expect(validateUploadFiles([sized(20 * 1024 * 1024 + 1)])).toContain('20MB')
    expect(validateUploadFiles([sized(0)])).toContain('1字节')
    expect(validateUploadFiles([new File(['x'], 'source.exe')])).toContain('source.exe')
  })
})

describe('independent source saves', () => {
  it('keeps successes and only retries the file with a definite failure', async () => {
    const rows = [row('a'), row('b'), row('c')]
    const upload = vi.fn().mockResolvedValueOnce(asset('a')).mockRejectedValueOnce({ isAxiosError: true, response: { status: 422, data: { detail: '文件损坏' } } })
      .mockResolvedValueOnce(asset('c')).mockResolvedValueOnce(asset('b'))
    const options = { current: () => true, request, upload }
    await saveUploadQueue(rows, options)
    expect(rows.map(row => row.state)).toEqual(['saved', 'failed', 'saved'])
    expect(rows[1]!.error).toContain('文件损坏')
    expect(rows[1]!.request).toBeUndefined()
    await saveUploadQueue(rows, options)
    expect(upload.mock.calls.map(([value]) => value.file.name)).toEqual(['a.pdf', 'b.pdf', 'c.pdf', 'b.pdf'])
    expect(rows.map(row => row.state)).toEqual(['saved', 'saved', 'saved'])
  })

  it('replays the exact uncertain request and never resends a successful file', async () => {
    const rows = [row('a'), row('b')]
    rows[1]!.contract = 'B-ORIGINAL'
    const upload = vi.fn().mockResolvedValueOnce(asset('a')).mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce(asset('b'))
    const options = { current: () => true, request, upload }
    await saveUploadQueue(rows, options)
    const original = upload.mock.calls[1]![0]
    rows[1]!.contract = 'CHANGED'
    await saveUploadQueue(rows, options)
    expect(upload).toHaveBeenCalledTimes(3)
    expect(upload.mock.calls[2]![0]).toBe(original)
    expect(upload.mock.calls[2]![0].body.contract_number).toBe('B-ORIGINAL')
  })

  it.each([401, 403])('stops all remaining submissions when access is rejected (%s)', async status => {
    const rows = [row('a'), row('b')]
    const upload = vi.fn().mockRejectedValue({ response: { status } })
    await saveUploadQueue(rows, { current: () => true, request, upload })
    expect(upload).toHaveBeenCalledOnce()
    expect(rows[0]!.state).toBe('failed')
    expect(rows[1]!.state).toBe('pending')
    expect(rows[1]!.request).toBeUndefined()
  })

  it('keeps an uncertain request frozen if a retry is rejected by a later permission check', async () => {
    const rows = [row('a')]
    const upload = vi.fn().mockRejectedValueOnce(new Error('timeout')).mockRejectedValueOnce({ response: { status: 403 } }).mockResolvedValueOnce(asset('a'))
    const options = { current: () => true, request, upload }
    await saveUploadQueue(rows, options)
    const original = rows[0]!.request
    await saveUploadQueue(rows, options)
    expect(rows[0]!.state).toBe('unknown')
    expect(rows[0]!.request).toBe(original)
    await saveUploadQueue(rows, options)
    expect(upload.mock.calls.map(([request]) => request)).toEqual([original, original, original])
  })

  it('ignores a late response and does not start another factory/account source', async () => {
    const rows = [row('a'), row('b')]
    let current = true
    const upload = vi.fn(async () => { current = false; return asset('late') })
    await saveUploadQueue(rows, { current: () => current, request, upload })
    expect(upload).toHaveBeenCalledOnce()
    expect(rows[0]!.asset).toBeUndefined()
    expect(rows[1]!.request).toBeUndefined()
  })
})
