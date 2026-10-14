/** Normalize only a complete pasted pair/triple of dimensions, without guessing units. */
export function normalizeCartonDimensionPaste(value: string): string | null {
  const parts = value.normalize('NFKC').trim().split(/\s+/u)
  if (parts.length < 2 || parts.length > 3 || parts.some(part => !/^\d+(?:\.\d+)?$/.test(part))) return null
  return parts.join('*')
}

export function applyCartonDimensionPaste(event: ClipboardEvent, update: (value: string) => void): boolean {
  const input = event.target
  if (!(input instanceof HTMLInputElement) || input.disabled || input.readOnly) return false
  const dimensions = normalizeCartonDimensionPaste(event.clipboardData?.getData('text/plain') ?? '')
  if (!dimensions) return false
  const start = input.selectionStart ?? input.value.length
  const end = input.selectionEnd ?? start
  const value = `${input.value.slice(0, start)}${dimensions}${input.value.slice(end)}`
  event.preventDefault()
  input.value = value
  update(value)
  input.setSelectionRange(start + dimensions.length, start + dimensions.length)
  return true
}
