import type { QuickAsset, QuickUploadBody } from '@/api/cartonQuickAssets'
import { responseStatus } from './quickAssets'
import { getApiErrorMessage } from '@/lib/http'

export interface UploadSelection {
  contract: string
  chosenTargets: string[]
  associationTouched: boolean
  orderSearch: string
  needsReview: boolean
}
export interface QueuedUpload extends UploadSelection {
  id: string
  file: File
  state: 'pending' | 'saving' | 'saved' | 'failed' | 'unknown'
  error: string
  asset?: QuickAsset
  request?: { factory: string; body: QuickUploadBody; file: File }
}

export function uploadSelection(): UploadSelection {
  return { contract: '', chosenTargets: [], associationTouched: false, orderSearch: '', needsReview: false }
}

export function validateUploadFiles(files: File[]) {
  if (files.length > 50 || files.reduce((sum, file) => sum + file.size, 0) > 100 * 1024 * 1024)
    return '每批最多50个文件、合计100MB，单个文件最多20MB。'
  for (const file of files) {
    if (!/\.(pdf|xls|xlsx|xlsm|jpe?g|png|webp)$/i.test(file.name)) return `${file.name}：请选择 PDF、Excel、JPG、PNG 或 WebP 文件。`
    if (!file.size || file.size > 20 * 1024 * 1024 || file.name.length > 255) return `${file.name}：文件须为1字节至20MB，文件名不超过255个字符。`
  }
  return ''
}

/** A retry reuses each uncertain request; successful files never run twice. */
export async function saveUploadQueue(rows: QueuedUpload[], options: {
  current: () => boolean
  request: (row: QueuedUpload) => NonNullable<QueuedUpload['request']>
  upload: (request: NonNullable<QueuedUpload['request']>) => Promise<QuickAsset>
}) {
  let latest: QuickAsset | undefined
  for (const row of rows) {
    if (!options.current()) break
    if (row.state === 'saved') continue
    const uncertain = row.state === 'unknown'
    const request = row.request ?? options.request(row)
    row.request = request; row.state = 'saving'; row.error = ''
    try {
      const asset = await options.upload(request)
      if (!options.current()) break
      row.asset = asset; row.state = 'saved'; row.request = undefined; latest = asset
    } catch (cause) {
      if (!options.current()) break
      const code = responseStatus(cause)
      if (uncertain || code === undefined || code >= 500) {
        row.state = 'unknown'
        row.error = (uncertain && code !== undefined && code < 500 ? `${getApiErrorMessage(cause)}。` : '')
          + '保存结果尚未确认。请原样重试核实，系统会沿用同一次请求，避免重复上传。'
      } else {
        row.state = 'failed'; row.request = undefined
        if (code === 409) row.needsReview = true
        row.error = code === 409 ? '资料或关联目标已更新，请刷新关联后核对再保存。' : getApiErrorMessage(cause)
      }
      // Revoked access must stop the rest of the queue immediately.
      if (code === 401 || code === 403) break
    }
  }
  return latest
}
