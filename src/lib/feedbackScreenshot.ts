export interface ScreenshotMark { x: number; y: number; width: number; height: number; note: string }
export function screenshotRectangle(start: { x: number; y: number }, end: { x: number; y: number }, width: number, height: number): ScreenshotMark {
  const x1 = Math.max(0, Math.min(width, start.x)), x2 = Math.max(0, Math.min(width, end.x))
  const y1 = Math.max(0, Math.min(height, start.y)), y2 = Math.max(0, Math.min(height, end.y))
  return { x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1), note: '' }
}

export async function captureFeedbackScreenshot(signal: AbortSignal): Promise<File> {
  if (!navigator.mediaDevices?.getDisplayMedia) throw new Error('当前浏览器不支持页面截图，请使用系统截图后粘贴，或选择图片。')
  const stream = await navigator.mediaDevices.getDisplayMedia({ video: { displaySurface: 'browser' }, audio: false, preferCurrentTab: true } as DisplayMediaStreamOptions)
  const video = document.createElement('video')
  const stop = () => stream.getTracks().forEach(track => track.stop())
  signal.addEventListener('abort', stop, { once: true })
  try {
    if (signal.aborted) throw new Error('截图已取消')
    if (stream.getVideoTracks()[0]?.getSettings().displaySurface !== 'browser') throw new Error('请选择当前浏览器标签页进行截图。')
    video.muted = true; video.srcObject = stream
    await video.play()
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => done(new Error('截图未就绪，请重试或粘贴系统截图。')), 5000)
      const abort = () => done(new Error('截图已取消'))
      function done(error?: Error) { window.clearTimeout(timer); signal.removeEventListener('abort', abort); error ? reject(error) : resolve() }
      signal.addEventListener('abort', abort, { once: true })
      if (signal.aborted) abort()
      else if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(() => done())
      else if (video.videoWidth) done()
      else video.addEventListener('loadeddata', () => done(), { once: true })
    })
    if (signal.aborted) throw new Error('截图已取消')
    const canvas = document.createElement('canvas')
    const scale = Math.min(1, 2000 / video.videoWidth)
    canvas.width = Math.round(video.videoWidth * scale); canvas.height = Math.round(video.videoHeight * scale)
    if (!canvas.width || !canvas.height) throw new Error('未取得有效截图，请重试或粘贴系统截图。')
    canvas.getContext('2d')!.drawImage(video, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/png'))
    if (signal.aborted) throw new Error('截图已取消')
    if (!blob) throw new Error('截图生成失败，请使用系统截图后粘贴。')
    return new File([blob], '页面截图.png', { type: 'image/png' })
  } finally { signal.removeEventListener('abort', stop); stop(); video.srcObject = null }
}
