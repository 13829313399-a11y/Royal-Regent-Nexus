export interface EditorInstance { destroyEditor(): void }
export interface EditorEvent { data?: unknown }
export interface DocsApi { DocEditor: new (id: string, config: Record<string, unknown>) => EditorInstance }
declare global { interface Window { DocsAPI?: DocsApi } }

let loadedUrl = ''
let loading: Promise<DocsApi> | undefined
export function loadEditor(url: string): Promise<DocsApi> {
  if (url === loadedUrl && loading) return loading
  const parsed = new URL(url, window.location.href)
  if (!['http:', 'https:'].includes(parsed.protocol)) return Promise.reject(new Error('编辑器地址无效'))
  loadedUrl = url
  loading = new Promise<DocsApi>((resolve, reject) => {
    const script = document.createElement('script')
    const timer = window.setTimeout(() => fail(), 30000)
    const fail = () => { clearTimeout(timer); script.remove(); loading = undefined; reject(new Error('无法连接文档编辑服务，请稍后重试')) }
    script.src = parsed.href
    script.onload = () => { clearTimeout(timer); if (window.DocsAPI) resolve(window.DocsAPI); else fail() }
    script.onerror = fail
    document.head.appendChild(script)
  })
  return loading
}

export function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = name; link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
