import { applyYinhuiHeaderMapping, correctYinhuiDraft, selectYinhuiToolCandidate, type YinhuiDraft } from './yinhuiDraft'
import { parseXlsxWorkbook, type XlsxParsedSheet } from './xlsxLite'
import { selectYinhuiMainSheet, YINHUI_MAIN_SHEET_NAMES } from './yinhui'

export interface RecognitionEvidence { sheet: string; cell: string; text: string }
export interface RecognitionChoice { id: string; label: string; evidence: RecognitionEvidence[] }
export interface RecognitionTask {
  id: string; kind: 'tool_match' | 'header' | 'cost_category'; target: string
  source: RecognitionEvidence; context: RecognitionEvidence[]; choices: RecognitionChoice[]
}
export interface RecognitionItem { task_id: string; choice_id: string | null; reason: string }
export interface RecognitionResponse { items: RecognitionItem[]; engine: string; model: string }
const str = (v: unknown) => String(v ?? '').trim()
const col = (index: number): string => index < 26 ? String.fromCharCode(65 + index) : col(Math.floor(index / 26) - 1) + col(index % 26)
const categories = ['五金', '电子', '包装', '纸箱', '车衣', '装配工', '油漆', '文件费']
const sourceCache = new WeakMap<ArrayBuffer, XlsxParsedSheet[]>()

/** Only names, identifiers and header labels leave the browser. Source amounts are never sent. */
export function buildYinhuiRecognitionTasks(draft: YinhuiDraft): { tasks: RecognitionTask[]; notice: string } {
  let sheets = sourceCache.get(draft.buffer)
  if (!sheets) {
    sheets = parseXlsxWorkbook(draft.buffer, { sheetNames: [...YINHUI_MAIN_SHEET_NAMES, 'Tool PLan', 'Tool Plan', 'Tool plan', 'TOOL PLAN'], valuesOnly: true }).sheets
    sourceCache.set(draft.buffer, sheets)
  }
  const tasks: RecognitionTask[] = []
  let skipped = 0
  const add = (task: RecognitionTask) => {
    const evidence = [task.source, ...task.context, ...task.choices.flatMap(c => c.evidence)]
    if (!task.choices.length || task.choices.length > 80 || evidence.some(e => !e.text || e.text.length > 400) || task.choices.some(c => c.label.length > 500) || tasks.length >= 40 || JSON.stringify([...tasks, task]).length > 95000) { skipped++; return }
    tasks.push(task)
  }
  for (const sheet of sheets.filter(s => /tool plan/i.test(s.name))) {
    for (const [i, row] of sheet.rows.entries()) {
      if (!row || draft.headerMappings?.some(m => m.sheet === sheet.name && m.row === i + 1)) continue
      // Locate potential header rows; the model decides roles only within those original cells.
      const labels = row.flatMap((v, c) => typeof v === 'string' && /模|名稱|名称|品名|零件|部件|图片|圖片|材料|出模|mould|mold|tool|part|description|material|cavity/i.test(v) && v.length <= 100 ? [{ sheet: sheet.name, cell: `${col(c)}${i + 1}`, text: str(v) }] : [])
      if (labels.length < 3 || labels.length > 8) continue
      const normalized = labels.map(e => e.text.replace(/\s/g, '').toLowerCase())
      if (normalized.some(v => /模[号號]|模具[编編][号號]|moldno/.test(v)) && normalized.some(v => /^(?:名称|名稱)$|零件名[称稱]|部件名[称稱]|description/.test(v))) continue
      const choices = labels.flatMap(mold => labels.filter(name => name !== mold).map(name => ({ id: `${mold.cell}|${name.cell}`, label: `模号列：${mold.text}；名称列：${name.text}`, evidence: [mold, name] })))
      add({ id: `header:${sheet.name}:${i + 1}`, kind: 'header', target: '模号列与部件名称列', source: labels[0]!, context: labels.slice(1), choices })
    }
  }
  const main = selectYinhuiMainSheet(sheets)
  const candidates = draft.candidates.map(candidate => {
    const split = candidate.source.lastIndexOf('!')
    const sheet = sheets.find(s => s.name === candidate.source.slice(0, split))
    const rowIndex = Number(candidate.source.slice(split + 1)) - 1
    const row = sheet?.rows[rowIndex]
    const c = row?.findIndex(v => str(v) === candidate.description) ?? -1
    return { id: candidate.source, label: `${candidate.moldNo} · ${candidate.description} · ${candidate.partNo}`, evidence: sheet && c >= 0 ? [{ sheet: sheet.name, cell: `${col(c)}${rowIndex + 1}`, text: candidate.description }] : [] }
  }).filter(c => c.evidence.length)
  if (main) draft.result.quoteData.tools.forEach((line, index) => {
    const description = line.originalDescription || line.description
    const matches = main.rows.flatMap((row, r) => str(row?.[2]) === description ? [{ sheet: main.name, cell: `C${r + 1}`, text: description }] : [])
    if (matches.length !== 1 || !candidates.length) return
    add({ id: `tool:${index}`, kind: 'tool_match', target: '模具对应部件', source: matches[0]!, context: [], choices: candidates })
  })
  for (const issue of draft.result.quoteData.importIssues || []) {
    if (!issue.message.includes('尚未映射成本类别')) continue
    const category = issue.cells.find(c => c.label === '成本类别')
    const name = issue.cells.find(c => c.label === '名称/用量')
    if (!category || !name) continue
    add({ id: `cost:${category.sheet}:${category.cell}`, kind: 'cost_category', target: '成本类别', source: { sheet: category.sheet, cell: category.cell, text: str(category.value) }, context: [{ sheet: name.sheet, cell: name.cell, text: str(name.value) }], choices: categories.map(c => ({ id: c, label: c, evidence: [] })) })
  }
  return { tasks, notice: skipped ? `${skipped} 项超出本次识别范围，请手工核对；每次最多处理 40 项。` : '' }
}

export function validateYinhuiRecognition(response: RecognitionResponse, tasks: RecognitionTask[]): RecognitionItem[] {
  if (!response || !Array.isArray(response.items) || response.items.length !== tasks.length) throw new Error('AI 返回结果不完整，请重新识别')
  return response.items.map((item, i) => {
    if (!item || item.task_id !== tasks[i]!.id || typeof item.reason !== 'string' || !item.reason.trim() || item.reason.length > 300 || (item.choice_id !== null && !tasks[i]!.choices.some(c => c.id === item.choice_id))) throw new Error('AI 返回未知候选，建议未应用')
    return { task_id: item.task_id, choice_id: item.choice_id, reason: item.reason }
  })
}

export function applyYinhuiRecognition(draft: YinhuiDraft, task: RecognitionTask, item: RecognitionItem): YinhuiDraft {
  const current = buildYinhuiRecognitionTasks(draft).tasks.find(t => t.id === task.id)
  if (!current || JSON.stringify(current) !== JSON.stringify(task)) throw new Error('原表或草稿已变化，请重新识别')
  validateYinhuiRecognition({ items: [item], engine: '', model: '' }, [current])
  const choice = current.choices.find(c => c.id === item.choice_id)
  if (!choice) throw new Error('该项没有可靠建议，请手工核对')
  if (task.kind === 'header') {
    const [mold, name] = choice.evidence
    return applyYinhuiHeaderMapping(draft, { sheet: mold!.sheet, row: Number(mold!.cell.replace(/[A-Z]/g, '')), moldCell: mold!.cell, descriptionCell: name!.cell })
  }
  if (task.kind === 'cost_category') return correctYinhuiDraft(draft, [{ sheet: task.source.sheet, cell: task.source.cell, value: choice.id }])
  selectYinhuiToolCandidate(draft, Number(task.id.split(':')[1]), choice.id)
  return draft
}
