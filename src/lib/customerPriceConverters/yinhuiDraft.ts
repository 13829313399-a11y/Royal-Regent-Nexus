import { convertYinhuiInternalQuote, parseYinhuiMoq, type YinhuiConversionResult, type YinhuiSourceOverride } from './yinhui'
import { parseXlsxWorkbook } from './xlsxLite'

export interface YinhuiToolCandidate { source: string; moldNo: string; partNo: string; description: string }
export interface YinhuiHeaderMapping { sheet: string; row: number; moldCell: string; descriptionCell: string }
export interface YinhuiDraft {
  buffer: ArrayBuffer
  sourceFileName: string
  overrides: YinhuiSourceOverride[]
  result: YinhuiConversionResult
  candidates: YinhuiToolCandidate[]
  headerMappings?: YinhuiHeaderMapping[]
}
const text = (v: unknown) => String(v ?? '').trim()
const record = (v: unknown): Record<string, unknown> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : {}
const fields = ['model', 'productName', 'quoteDate', 'packaging', 'stage', 'adaptor', 'tryMe', 'battery'] as const
const groups = ['tools', 'plastic', 'mechanical', 'electronic', 'fabric', 'packagingRows', 'documentFees'] as const
const MAX_SOURCE_BYTES = 40 * 1024 * 1024

/** Candidates are identifiers only. Selecting one must not replace weights, usage or prices. */
function toolCandidates(buffer: ArrayBuffer, mappings: YinhuiHeaderMapping[] = []): YinhuiToolCandidate[] {
  const sheets = parseXlsxWorkbook(buffer, { sheetNames: ['Tool PLan', 'Tool Plan', 'Tool plan', 'TOOL PLAN'], valuesOnly: true }).sheets
  const candidates: YinhuiToolCandidate[] = []
  if (mappings.length > 12) throw new Error('模具表头映射过多')
  const column = (cell: string) => cell.replace(/\d/g, '').split('').reduce((n, c) => n * 26 + c.charCodeAt(0) - 64, 0) - 1
  for (const mapping of mappings) {
    const row = sheets.find(s => s.name === mapping.sheet)?.rows[mapping.row - 1]
    if (!Number.isInteger(mapping.row) || !row || ![mapping.moldCell, mapping.descriptionCell].every(c => typeof c === 'string' && /^[A-Z]{1,3}[1-9]\d*$/.test(c) && Number(c.replace(/[A-Z]/g, '')) === mapping.row && text(row[column(c)])) || mapping.moldCell === mapping.descriptionCell) throw new Error('模具表头映射与原表不一致')
  }
  for (const sheet of sheets) {
    let columns: { mold: number; description: number; part: number } | undefined
    let moldNo = ''
    for (const [index, row] of sheet.rows.entries()) {
      if (!row) continue
      const normalized = row.map(v => text(v).normalize('NFKC').replace(/\s/g, '').toLowerCase())
      const mapping = mappings.find(m => m.sheet === sheet.name && m.row === index + 1)
      const mold = mapping ? column(mapping.moldCell) : normalized.findIndex(v => /模[号號]|模具[编編][号號]|moldno/.test(v))
      const description = mapping ? column(mapping.descriptionCell) : normalized.findIndex(v => /^(?:名称|名稱)$|零件名[称稱]|部件名[称稱]|description/.test(v))
      if (mold >= 0 && description >= 0 && mold !== description) {
        columns = { mold, description, part: normalized.findIndex(v => /partno|物料[编編][号號]|零件[编編][号號]/.test(v)) }
        moldNo = ''
        continue
      }
      if (!columns) continue
      const name = text(row[columns.description])
      const moldValue = text(row[columns.mold])
      if (moldValue) moldNo = moldValue
      if (!name || /^#|合计|合計|total/i.test(name) || !moldNo || candidates.length >= 500) continue
      candidates.push({ source: `${sheet.name}!${index + 1}`, moldNo, partNo: columns.part < 0 ? '' : text(row[columns.part]), description: name })
    }
  }
  return candidates
}

export function createYinhuiDraft(buffer: ArrayBuffer, sourceFileName: string, overrides: YinhuiSourceOverride[] = [], headerMappings: YinhuiHeaderMapping[] = []): YinhuiDraft {
  if (buffer.byteLength > MAX_SOURCE_BYTES) throw new Error('银辉草稿原文件不能超过 40 MB')
  const result = convertYinhuiInternalQuote(buffer, sourceFileName, { draft: true, overrides })
  return { buffer, sourceFileName, overrides, result, candidates: toolCandidates(buffer, headerMappings), headerMappings }
}

export function applyYinhuiHeaderMapping(draft: YinhuiDraft, mapping: YinhuiHeaderMapping): YinhuiDraft {
  const headerMappings = [...(draft.headerMappings || []).filter(m => m.sheet !== mapping.sheet || m.row !== mapping.row), mapping]
  return { ...draft, headerMappings, candidates: toolCandidates(draft.buffer, headerMappings) }
}

export function correctYinhuiDraft(draft: YinhuiDraft, changes: YinhuiSourceOverride[]): YinhuiDraft {
  const allowed = new Set(draft.result.quoteData.importIssues?.flatMap(i => i.cells.map(c => `${c.sheet}!${c.cell}`)))
  const overrides = new Map(draft.overrides.map(o => [`${o.sheet}!${o.cell}`, o]))
  for (const change of changes) {
    const key = `${change.sheet}!${change.cell}`
    if (!allowed.has(key)) throw new Error('只能补正当前问题清单列出的原表字段')
    overrides.set(key, change)
  }
  return createYinhuiDraft(draft.buffer, draft.sourceFileName, [...overrides.values()], draft.headerMappings)
}

export function setYinhuiDraftMoq(result: YinhuiConversionResult, value: unknown) {
  try {
    result.quoteData.moq = parseYinhuiMoq(value)
    result.quoteData.importIssues = result.quoteData.importIssues?.filter(i => !i.source.endsWith(' · MOQ'))
  } catch { result.quoteData.moq = 0 }
}

export function selectYinhuiToolCandidate(draft: YinhuiDraft, index: number, source: string) {
  const line = draft.result.quoteData.tools[index]
  if (!line) return
  const candidate = draft.candidates.find(c => c.source === source)
  if (!candidate) return
  line.moldNo = candidate.moldNo
  line.partNo = candidate.partNo
}

function encode(buffer: ArrayBuffer) {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let start = 0; start < bytes.length; start += 8192) binary += String.fromCharCode(...bytes.subarray(start, start + 8192))
  return btoa(binary)
}
function reviewValues(result: YinhuiConversionResult) {
  const data = result.quoteData
  return {
    ...Object.fromEntries(fields.map(key => [key, data[key]])),
    moq: data.moq, freightFclHkd: data.freightFclHkd, freightLclHkd: data.freightLclHkd,
    names: Object.fromEntries(groups.map(key => [key, (data[key] || []).map(line => ({ description: line.description }))])),
    tools: data.tools.map(line => ({ moldNo: line.moldNo, partNo: line.partNo })),
  }
}

export function saveYinhuiDraft(draft: YinhuiDraft): string {
  return JSON.stringify({ kind: 'yinhui-import-draft', version: 1, factory: 'huaxing', customer: 'yinhui', sourceFileName: draft.sourceFileName,
    source: encode(draft.buffer), overrides: draft.overrides, headerMappings: draft.headerMappings || [], review: reviewValues(draft.result) })
}

export function loadYinhuiDraft(content: string): YinhuiDraft {
  if (content.length > MAX_SOURCE_BYTES * 1.5) throw new Error('银辉草稿文件过大')
  const saved = record(JSON.parse(content))
  if (saved.kind !== 'yinhui-import-draft' || saved.version !== 1 || saved.factory !== 'huaxing' || saved.customer !== 'yinhui'
    || typeof saved.source !== 'string' || typeof saved.sourceFileName !== 'string' || !saved.sourceFileName.toLowerCase().endsWith('.xlsx')) throw new Error('不是有效的华兴银辉导入草稿')
  const binary = atob(saved.source)
  if (binary.length > MAX_SOURCE_BYTES) throw new Error('银辉草稿原文件不能超过 40 MB')
  const buffer = Uint8Array.from(binary, c => c.charCodeAt(0)).buffer
  // Reparse the source and replay only current, identified corrections; never trust saved costs or issues.
  let draft = createYinhuiDraft(buffer, saved.sourceFileName)
  if (saved.headerMappings !== undefined) {
    if (!Array.isArray(saved.headerMappings) || saved.headerMappings.length > 12) throw new Error('模具表头映射无效')
    for (const value of saved.headerMappings) {
      const mapping = record(value)
      if (typeof mapping.sheet !== 'string' || typeof mapping.row !== 'number' || typeof mapping.moldCell !== 'string' || typeof mapping.descriptionCell !== 'string') throw new Error('模具表头映射无效')
      draft = applyYinhuiHeaderMapping(draft, mapping as unknown as YinhuiHeaderMapping)
    }
  }
  if (!Array.isArray(saved.overrides) || saved.overrides.length > 2000) throw new Error('草稿补正记录无效')
  const pending = saved.overrides.map(value => {
    const o = record(value)
    if (typeof o.sheet !== 'string' || typeof o.cell !== 'string' || !['string', 'number'].includes(typeof o.value)) throw new Error('草稿补正记录无效')
    return o as unknown as YinhuiSourceOverride
  })
  while (pending.length) {
    const allowed = new Set(draft.result.quoteData.importIssues?.flatMap(i => i.cells.map(c => `${c.sheet}!${c.cell}`)))
    const next = pending.filter(o => allowed.has(`${o.sheet}!${o.cell}`))
    if (!next.length) throw new Error('草稿补正记录与原表问题不一致，请重新导入原表')
    draft = correctYinhuiDraft(draft, next)
    next.forEach(o => pending.splice(pending.indexOf(o), 1))
  }
  const review = record(saved.review)
  const data = draft.result.quoteData
  for (const key of fields) if (typeof review[key] === 'string' && (review[key] as string).length < 2000) {
    if (key === 'adaptor') { if (['', 'included', 'not included'].includes(review[key] as string)) data.adaptor = review[key] as typeof data.adaptor }
    else if (key === 'tryMe') { if (['', 'YES', 'NO'].includes(review[key] as string)) data.tryMe = review[key] as typeof data.tryMe }
    else data[key] = review[key] as string
  }
  if (typeof review.moq === 'number') setYinhuiDraftMoq(draft.result, review.moq)
  for (const key of ['freightFclHkd', 'freightLclHkd'] as const) if (review[key] === null || (typeof review[key] === 'number' && Number.isFinite(review[key]))) data[key] = review[key] as number | null
  for (const group of groups) {
    const names = record(review.names)[group]
    if (!Array.isArray(names) || names.length !== (data[group] || []).length) continue
    names.forEach((value, i) => { const name = record(value).description; if (typeof name === 'string' && name.length < 2000) data[group]![i]!.description = name })
  }
  if (Array.isArray(review.tools) && review.tools.length === data.tools.length) review.tools.forEach((value, i) => {
    const entry = record(value)
    for (const key of ['moldNo', 'partNo'] as const) if (typeof entry[key] === 'string' && entry[key].length < 200) data.tools[i]![key] = entry[key]
  })
  return draft
}
