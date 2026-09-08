export type NumberToken = { literal: string } | { lengths: number[] }

export function parseNumberTemplate(template: string): NumberToken[] {
  if (!template.trim() || template.length > 256 || /\s/.test(template)) throw new Error('格式不能为空、不能有空格，且最多 256 字')
  const tokens: NumberToken[] = []
  for (const part of template.split(/(\{[^{}]*\})/).filter(Boolean)) {
    if (part.startsWith('{')) {
      if (!/^\{[1-9][0-9]*(,[1-9][0-9]*)*\}$/.test(part)) throw new Error('数字段请写成 {9} 或 {3,4}')
      const lengths = [...new Set(part.slice(1, -1).split(',').map(Number))].sort((a, b) => a - b)
      if (lengths.length > 16 || lengths.some(n => n > 128)) throw new Error('每段允许位数须在 1–128 之间，最多 16 种')
      tokens.push({ lengths })
    } else {
      if (/[{}]/.test(part)) throw new Error('格式的大括号不完整')
      tokens.push({ literal: part.toUpperCase() })
    }
  }
  if (tokens.length > 32 || tokens.reduce((n, t) => n + ('literal' in t ? t.literal.length : Math.max(...t.lengths)), 0) > 128) throw new Error('格式过长，编号最多 128 字')
  return tokens
}

export function matchesNumberTemplate(template: string, value: string) {
  let tokens: NumberToken[]
  try { tokens = parseNumberTemplate(template) } catch { return false }
  value = value.toUpperCase()
  let positions = new Set([0])
  for (const token of tokens) {
    const next = new Set<number>()
    for (const at of positions) {
      if ('literal' in token) { if (value.startsWith(token.literal, at)) next.add(at + token.literal.length) }
      else for (const length of token.lengths) {
        if (at + length <= value.length && /^[0-9]+$/.test(value.slice(at, at + length))) next.add(at + length)
      }
    }
    positions = next
  }
  return positions.has(value.length)
}

export function describeNumberTemplate(template: string) {
  try { return parseNumberTemplate(template).map(t => 'literal' in t ? t.literal : `${t.lengths.join(' 或 ')} 位数字`).join('＋') }
  catch (error) { return error instanceof Error ? error.message : '格式不完整' }
}

export function recognizeNumberTemplates(values: string[]) {
  const distinct = [...new Set(values.map(v => v.trim().toUpperCase()).filter(Boolean))]
  if (distinct.some(v => v.length > 128 || /[{}\s]/.test(v))) throw new Error('样例应为完整编号，一行一个，最多 128 字')
  const groups = new Map<string, string[]>()
  for (const value of distinct) {
    const shape = value.replace(/[0-9]+/g, '{}')
    groups.set(shape, [...(groups.get(shape) || []), value])
  }
  const templates: string[] = []
  for (const [shape, examples] of groups) {
    const widths = examples.map(v => (v.match(/[0-9]+/g) || []).map(s => s.length))
    const columns = (widths[0] || []).map((_, i) => [...new Set(widths.map(w => w[i]!))].sort((a,b) => a-b))
    if (columns.filter(c => c.length > 1).length <= 1) {
      let i = 0
      templates.push(shape.replace(/\{\}/g, () => `{${columns[i++]!.join(',')}}`))
    } else templates.push(...examples.map(v => v.replace(/[0-9]+/g, digits => `{${digits.length}}`)))
  }
  const unique = [...new Set(templates)]
  if (unique.length > 20) throw new Error('识别出超过 20 种格式，请精简样例或手动整理')
  unique.forEach(parseNumberTemplate)
  return { sampleCount: distinct.length, templates: unique }
}
