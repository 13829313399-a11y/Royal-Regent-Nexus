import { afterEach, describe, expect, it, vi } from 'vitest'
import { captureFeedbackScreenshot, screenshotRectangle } from '../feedbackScreenshot'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
describe('feedback screenshot safety', () => {
  it('normalizes backwards drags and clamps annotations to the image', () => {
    expect(screenshotRectangle({ x: 90, y: 80 }, { x: -20, y: 110 }, 100, 100)).toEqual({ x: 0, y: 80, width: 90, height: 20, note: '' })
  })
  it('stops screen sharing when a non-tab surface is selected', async () => {
    const stop = vi.fn(), track = { stop, getSettings: () => ({ displaySurface: 'monitor' }) }
    vi.stubGlobal('navigator', { mediaDevices: { getDisplayMedia: vi.fn().mockResolvedValue({ getVideoTracks: () => [track], getTracks: () => [track] }) } })
    await expect(captureFeedbackScreenshot(new AbortController().signal)).rejects.toThrow('当前浏览器标签页')
    expect(stop).toHaveBeenCalledOnce()
  })
  it('stops a late stream after cancellation while the browser selection prompt was open', async () => {
    const stop = vi.fn(), track = { stop, getSettings: () => ({ displaySurface: 'browser' }) }
    const controller = new AbortController(); controller.abort()
    vi.stubGlobal('navigator', { mediaDevices: { getDisplayMedia: vi.fn().mockResolvedValue({ getVideoTracks: () => [track], getTracks: () => [track] }) } })
    await expect(captureFeedbackScreenshot(controller.signal)).rejects.toThrow('截图已取消')
    expect(stop).toHaveBeenCalledOnce()
  })
  it('offers paste or upload when native tab capture is unavailable', async () => {
    vi.stubGlobal('navigator', { mediaDevices: {} })
    await expect(captureFeedbackScreenshot(new AbortController().signal)).rejects.toThrow('粘贴')
  })
  it('captures a ready tab frame and releases every media track', async () => {
    const stop = vi.fn(), track = { stop, getSettings: () => ({ displaySurface: 'browser' }) }, drawImage = vi.fn()
    const video = { muted: false, srcObject: null, videoWidth: 320, videoHeight: 180, play: vi.fn().mockResolvedValue(undefined), requestVideoFrameCallback: (callback: () => void) => callback() }
    const canvas = { width: 0, height: 0, getContext: () => ({ drawImage }), toBlob: (callback: (blob: Blob) => void) => callback(new Blob(['png'], { type: 'image/png' })) }
    vi.stubGlobal('navigator', { mediaDevices: { getDisplayMedia: vi.fn().mockResolvedValue({ getVideoTracks: () => [track], getTracks: () => [track] }) } })
    vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => tag === 'video' ? video : canvas) as never)
    const file = await captureFeedbackScreenshot(new AbortController().signal)
    expect(file.type).toBe('image/png'); expect(file.name).toBe('页面截图.png')
    expect(drawImage).toHaveBeenCalledWith(video, 0, 0, 320, 180)
    expect(stop).toHaveBeenCalledOnce(); expect(video.srcObject).toBeNull()
  })
  it('stops sharing immediately when cancelled while video playback is pending', async () => {
    const stop = vi.fn(), track = { stop, getSettings: () => ({ displaySurface: 'browser' }) }, controller = new AbortController()
    let resume: () => void = () => {}
    const video = { muted: false, srcObject: null, play: () => new Promise<void>(resolve => { resume = resolve }) }
    vi.stubGlobal('navigator', { mediaDevices: { getDisplayMedia: vi.fn().mockResolvedValue({ getVideoTracks: () => [track], getTracks: () => [track] }) } })
    vi.spyOn(document, 'createElement').mockReturnValue(video as never)
    const pending = captureFeedbackScreenshot(controller.signal)
    await Promise.resolve(); await Promise.resolve(); controller.abort()
    expect(stop).toHaveBeenCalledOnce()
    resume(); await expect(pending).rejects.toThrow('截图已取消')
    expect(video.srcObject).toBeNull()
  })
})
