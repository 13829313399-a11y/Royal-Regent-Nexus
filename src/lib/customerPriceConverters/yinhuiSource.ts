import { parseXlsxWorkbook, type XlsxCellValue, type XlsxParsedSheet } from './xlsxLite'

const text = (value: unknown) => String(value ?? '').trim()
export const yinhuiSheetKey = (value: string) => value.normalize('NFKC').toLowerCase()
  .replace(/[\s\u200b-\u200d\ufeff+_.()\-]/g, '').replace(/細/g, '细').replace(/內/g, '内').replace(/報/g, '报').replace(/價/g, '价')
export const yinhuiHeaderKey = (value: unknown) => text(value).normalize('NFKC').toLowerCase().replace(/[\s\u200b-\u200d\ufeff().:：]/g, '')

export function yinhuiMainHeader(rows: XlsxCellValue[][]) {
  return rows.findIndex(row => /^(?:名称|名稱|物料名称|物料名稱|零件名称|零件名稱|description|name)$/.test(yinhuiHeaderKey(row?.[2]))
    && /^(?:料型|胶料|膠料|material)$/.test(yinhuiHeaderKey(row?.[3]))
    && /^(?:料重(?:g|克)?|weightg)$/.test(yinhuiHeaderKey(row?.[4])))
}
const mainName = (sheet: XlsxParsedSheet) => /^(?:内部)?明细/.test(yinhuiSheetKey(sheet.name))
const mainStructure = (sheet: XlsxParsedSheet) => {
  const header = yinhuiMainHeader(sheet.rows)
  return header > 0 && /^#\s*[\w-]+/.test(text(sheet.rows[header - 1]?.[0]))
    && sheet.rows.some(row => /^(?:出厂价|出廠價)$/.test(text(row?.[3])))
}

export function selectYinhuiMainSheet(sheets: XlsxParsedSheet[]) {
  const candidates = sheets.filter(sheet => mainName(sheet) || mainStructure(sheet))
  const variants = candidates.filter(sheet => /开窗盒|開窗盒|密封盒/.test(yinhuiSheetKey(sheet.name)))
  if (variants.length) {
    const windowBox = variants.filter(sheet => /开窗盒|開窗盒/.test(yinhuiSheetKey(sheet.name)))
    if (windowBox.length !== 1 || !windowBox[0]!.rows.slice(0, 12).some(row => /^#\s*89127\b/.test(text(row?.[0])))
      || candidates.some(sheet => !variants.includes(sheet))) throw new Error(`银辉存在包装版本明细，但无法唯一确认 89127 开窗盒页；请明确本次包装版本：${candidates.map(s => `“${s.name}”`).join('、')}`)
    return windowBox[0]
  }
  if (candidates.length > 1) throw new Error(`银辉找到多张可能的内部明细，不能自动选取：${candidates.map(s => `“${s.name}”`).join('、')}；请明确本次要转换的明细页，保留该页后重试`)
  return candidates[0]
}

export const isYinhuiToolPlanName = (name: string) => /^(?:toolplan|工模表|产品工模表|產品工模表|模具表)/.test(yinhuiSheetKey(name))
const moldHeader = (value: unknown) => /^(?:(?:hk|香港|大陆|大陸)?(?:模[号號]|模具[编編][号號]))?(?:mou?ldno)?$/.test(yinhuiHeaderKey(value)) && Boolean(text(value))
const descriptionHeader = (value: unknown) => /^(?:(?:零件|部件|物料|中文)?名[称稱])?(?:description|chinesename)?$/.test(yinhuiHeaderKey(value)) && Boolean(text(value))
export function isYinhuiToolPlanSheet(sheet: XlsxParsedSheet) {
  return isYinhuiToolPlanName(sheet.name) || sheet.rows.slice(0, 80).some(row => row?.some(moldHeader) && row.some(descriptionHeader)
    && row.some(v => /cavity|出模[数數量]/i.test(text(v))) && row.some(v => /material|[胶膠]料|产品材料|產品材料/i.test(text(v))))
}

export function yinhuiToolIdentityColumns(row: XlsxCellValue[]) {
  const unique = (test: (value: unknown) => boolean) => {
    const indexes = row.flatMap((value, i) => test(value) ? [i] : [])
    return indexes.length === 1 ? indexes[0]! : -1
  }
  const hk = unique(value => /^(?:hk|香港)模[号號](?:mou?ldno)?$/.test(yinhuiHeaderKey(value)))
  return { mold: hk >= 0 ? hk : unique(moldHeader), description: unique(descriptionHeader),
    part: unique(value => /^(?:(?:物料|零件)?[编編][号號])?(?:partno)?$/.test(yinhuiHeaderKey(value)) && Boolean(text(value))) }
}

export function selectYinhuiToolPlan(sheets: XlsxParsedSheet[]) {
  const plans = sheets.filter(isYinhuiToolPlanSheet)
  if (plans.length > 1) throw new Error(`银辉找到多张可能的 Tool Plan：${plans.map(s => `“${s.name}”`).join('、')}；请明确对应模具表，不能自动拼接或任选一张`)
  return plans[0]
}

export function readYinhuiSource(buffer: ArrayBuffer) {
  // Probe every sheet by content, then load only relevant sheets fully. Never rename source sheets:
  // corrections, formula references, drawings, saved drafts and AI evidence must use actual names.
  const preview = parseXlsxWorkbook(buffer, { valuesOnly: true, maxRows: 80 })
  const names = preview.sheets.filter(sheet => mainName(sheet) || mainStructure(sheet) || isYinhuiToolPlanSheet(sheet)
    || ['模具报价', 'bom'].includes(yinhuiSheetKey(sheet.name)) || ['结构化数据', '审批与版本'].includes(sheet.name)).map(sheet => sheet.name)
  return parseXlsxWorkbook(buffer, { sheetNames: names, valuesOnly: true, includeFormulas: true })
}
