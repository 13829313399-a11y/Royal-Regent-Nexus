import './initBuffer.js'
import { analyzeCodexFile } from './codexImport.js'

self.onmessage = async ({ data }) => {
  const { id, fileName, buffer, kind = 'auto' } = data || {}
  try {
    const result = await analyzeCodexFile(fileName, buffer, kind)
    self.postMessage({ id, ok: true, result })
  } catch (error) {
    self.postMessage({ id, ok: false, error: error instanceof Error ? error.message : String(error) })
  }
}
