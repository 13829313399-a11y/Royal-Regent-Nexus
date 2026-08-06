export const MAX_PDF_FILE_SIZE_BYTES = 20 * 1024 * 1024

export function formatPdfFileSize(size: number) {
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export function validatePdfFile(file: File) {
  if (!file.name.toLowerCase().endsWith('.pdf')) return '只支持上传 .pdf 文件。'
  if (file.type && file.type !== 'application/pdf') return '文件类型不是有效的 PDF。'
  if (file.size <= 0) return 'PDF 文件不能为空。'
  if (file.size > MAX_PDF_FILE_SIZE_BYTES) return '单个 PDF 不可超过 20MB。'
  return ''
}

export function downloadToolBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}
