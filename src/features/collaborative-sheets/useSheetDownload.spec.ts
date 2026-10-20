import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { h, ref } from 'vue'
import { useSheetDownload, type DownloadContext } from './useSheetDownload'
import type { SheetDownloadOptions } from '@/api/collaborativeSheets'
import { advanceAuthenticationGeneration } from '@/lib/authenticationGeneration'

const target = ref<DownloadContext>({ id: 'a', factory: 'huaxing', account: 'owner', name: 'test.xlsx' })
let wrapper: VueWrapper, download: ReturnType<typeof useSheetDownload>
const fetch = vi.fn<(target: DownloadContext, progress: (loaded: number, total?: number) => void, options: SheetDownloadOptions) => Promise<Blob>>()
const prepare = vi.fn<(current: () => boolean) => Promise<boolean>>()
const deferred = <T>() => { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r }); return { promise, resolve } }
function start() {
  wrapper = mount({ setup() { download = useSheetDownload(() => target.value, prepare, fetch); return () => h('div') } })
}
beforeEach(() => {
  vi.useFakeTimers(); target.value = { id: 'a', factory: 'huaxing', account: 'owner', name: 'test.xlsx' }
  fetch.mockReset().mockResolvedValue(new Blob(['xlsx'])); prepare.mockReset().mockResolvedValue(true)
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:qa'), revokeObjectURL: vi.fn() }))
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  vi.spyOn(console, 'info').mockImplementation(() => {})
})
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('bounded, context-bound workbook downloads', () => {
  it('locks before saving, so repeated clicks cannot enqueue duplicate requests', async () => {
    const pending = deferred<boolean>(); prepare.mockReturnValue(pending.promise); start()
    const first = download.start(); const second = download.start()
    expect(download.active.value).toBe(true); expect(download.status.value).toContain('确认填写')
    expect(prepare).toHaveBeenCalledTimes(1); pending.resolve(true); await Promise.all([first, second])
    expect(fetch).toHaveBeenCalledTimes(1); expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1)
  })
  it('times out a stuck editor without applying a late confirmation or downloading', async () => {
    const editor = deferred<boolean>(); const apply = vi.fn()
    prepare.mockImplementation(async current => { await editor.promise; if (!current()) return false; apply(); return true })
    start(); const operation = download.start(); await vi.advanceTimersByTimeAsync(30_000); await operation
    expect(download.active.value).toBe(false); expect(download.error.value).toContain('确认填写超时')
    editor.resolve(true); await flushPromises(); expect(apply).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled()
    expect(download.readyUrl.value).toBe('')
  })
  it('invalidates A -> B -> A and ignores the old finally while the new request is active', async () => {
    const old = deferred<Blob>(), next = deferred<Blob>(); fetch.mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise)
    start(); const one = download.start(); await flushPromises()
    target.value = { ...target.value, id: 'b' }; target.value = { ...target.value, id: 'a' }
    const two = download.start(); await flushPromises(); await one
    expect(download.active.value).toBe(true)
    old.resolve(new Blob(['old'])); await flushPromises(); expect(URL.createObjectURL).not.toHaveBeenCalled()
    next.resolve(new Blob(['new'])); await two; expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
  })
  it('cancels only the download, aborts transport and ignores late progress and data', async () => {
    const response = deferred<Blob>(); fetch.mockReturnValue(response.promise); start()
    const operation = download.start(); await flushPromises()
    const options = fetch.mock.calls[0]![2], progress = fetch.mock.calls[0]![1]
    download.cancel(); await operation; expect(options.signal?.aborted).toBe(true)
    progress(20, 100); response.resolve(new Blob(['old'])); await flushPromises()
    expect(download.status.value).toContain('取消'); expect(download.readyUrl.value).toBe('')
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
  })
  it('bounds transport time and allows a retry without reusing its aborted controller', async () => {
    const response = deferred<Blob>(); fetch.mockReturnValueOnce(response.promise); start()
    const operation = download.start(); await flushPromises(); await vi.advanceTimersByTimeAsync(300_000); await operation
    expect(download.error.value).toContain('下载超时'); expect(fetch.mock.calls[0]![2].signal?.aborted).toBe(true)
    await download.start(); expect(fetch).toHaveBeenCalledTimes(2); expect(fetch.mock.calls[1]![2].signal?.aborted).toBe(false)
  })
  it('keeps a manual save link for a fresh user gesture, and revokes it on context change', async () => {
    start(); await download.start(); expect(download.readyUrl.value).toBe('blob:qa'); expect(download.readyName.value).toBe('test-已填写.xlsx')
    download.handoff(); expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(2)
    target.value = { ...target.value, id: 'b' }; expect(download.readyUrl.value).toBe(''); expect(download.status.value).toBe('')
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:qa')
  })
  it('cancels a pending response at a login boundary', async () => {
    const response = deferred<Blob>(); fetch.mockReturnValue(response.promise); start(); const operation = download.start(); await flushPromises()
    advanceAuthenticationGeneration(); window.dispatchEvent(new Event('auth-session-boundary-changed')); await operation
    response.resolve(new Blob(['private'])); await flushPromises(); expect(download.readyUrl.value).toBe('')
  })
})
