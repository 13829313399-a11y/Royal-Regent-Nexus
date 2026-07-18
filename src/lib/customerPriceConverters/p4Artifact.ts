import { parseXlsxWorkbook, type XlsxCellValue } from './xlsxLite'

export const P4_ARTIFACT_TEMPLATE_VERSION = 'internal-quote-p4-v2'
export const P4_STRUCTURED_DATA_SCHEMA_VERSION = 'internal-quote-structured-data-v1'

export const P4_SECTION_CODES = [
  'sales',
  'engineering',
  'electronic',
  'molding',
  'painting',
  'slush',
  'sewing',
  'assembly',
] as const

export type P4SectionCode = typeof P4_SECTION_CODES[number]

export interface P4InternalQuoteSection {
  code: P4SectionCode
  name: string
  status: string
  revision: number
  calculationStatus: string
  dependencyStatus: string
  calculationHash: string
  isRequired: boolean
  payload: Record<string, unknown>
  calculation: Record<string, unknown>
}

export interface P4InternalQuoteArtifact {
  templateVersion: string
  structuredDataSchemaVersion: string
  quoteNo: string
  versionLabel: string
  customer: string
  quantity: number
  productName: string
  factoryAndWorkshop: string
  formulaVersion: string
  referenceSnapshotId: string
  referenceSnapshot: Record<string, unknown>
  sections: Record<P4SectionCode, P4InternalQuoteSection>
}

interface StructuredChunkRow {
  recordType: string
  code: string
  name: string
  status: string
  revision: number
  calculationStatus: string
  dependencyStatus: string
  calculationHash: string
  isRequired: boolean
  chunkIndex: number
  chunkTotal: number
  chunk: string
}

export class P4ArtifactValidationError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'P4ArtifactValidationError'
  }
}

function text(value: XlsxCellValue) {
  return String(value ?? '').trim()
}

function numberValue(value: XlsxCellValue) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function objectValue(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new P4ArtifactValidationError(`${label} 必须是 JSON 对象`)
  }
  return value as Record<string, unknown>
}

function requiredSheet(
  workbook: ReturnType<typeof parseXlsxWorkbook>,
  name: string,
) {
  const sheet = workbook.sheets.find((item) => item.name === name)
  if (!sheet) {
    throw new P4ArtifactValidationError(`P4 受控文件缺少“${name}”工作表`)
  }
  return sheet
}

function parseStructuredRows(rows: XlsxCellValue[][]) {
  const headers = rows[2] ?? []
  const indexes = new Map(headers.map((value, index) => [text(value), index]))
  const requiredHeaders = [
    '记录类型',
    '分段代码',
    '分段名称',
    '状态',
    'revision',
    '计算状态',
    '依赖状态',
    '计算hash',
    '分片序号',
    '分片总数',
    'JSON分片',
  ]
  const missingHeaders = requiredHeaders.filter((header) => !indexes.has(header))
  if (missingHeaders.length > 0) {
    throw new P4ArtifactValidationError(`结构化数据表头缺少：${missingHeaders.join('、')}`)
  }
  const read = (row: XlsxCellValue[], header: string) => row[indexes.get(header) as number]

  return rows.slice(3).flatMap<StructuredChunkRow>((row) => {
    const recordType = text(read(row, '记录类型'))
    const code = text(read(row, '分段代码'))
    if (!recordType && !code) return []
    return [{
      recordType,
      code,
      name: text(read(row, '分段名称')),
      status: text(read(row, '状态')),
      revision: numberValue(read(row, 'revision')),
      calculationStatus: text(read(row, '计算状态')),
      dependencyStatus: text(read(row, '依赖状态')),
      calculationHash: text(read(row, '计算hash')),
      isRequired: indexes.has('是否参与') ? text(read(row, '是否参与')) !== '否' : true,
      chunkIndex: numberValue(read(row, '分片序号')),
      chunkTotal: numberValue(read(row, '分片总数')),
      chunk: String(read(row, 'JSON分片') ?? ''),
    }]
  })
}

function reconstructJson(
  rows: StructuredChunkRow[],
  recordType: string,
  code: string,
) {
  const chunks = rows
    .filter((row) => row.recordType === recordType && row.code === code)
    .sort((left, right) => left.chunkIndex - right.chunkIndex)
  if (chunks.length === 0) {
    throw new P4ArtifactValidationError(`结构化数据缺少 ${code}/${recordType}`)
  }
  const expectedTotal = chunks[0]?.chunkTotal ?? 0
  const indexes = chunks.map((row) => row.chunkIndex)
  if (
    expectedTotal !== chunks.length
    || chunks.some((row) => row.chunkTotal !== expectedTotal)
    || indexes.some((value, index) => value !== index + 1)
  ) {
    throw new P4ArtifactValidationError(`结构化数据 ${code}/${recordType} 分片不完整`)
  }
  try {
    return objectValue(JSON.parse(chunks.map((row) => row.chunk).join('')), `${code}/${recordType}`)
  } catch (error) {
    if (error instanceof P4ArtifactValidationError) throw error
    throw new P4ArtifactValidationError(`结构化数据 ${code}/${recordType} 不是有效 JSON`)
  }
}

export function parseP4InternalQuoteArtifact(buffer: ArrayBuffer): P4InternalQuoteArtifact {
  let workbook: ReturnType<typeof parseXlsxWorkbook>
  try {
    workbook = parseXlsxWorkbook(buffer)
  } catch {
    throw new P4ArtifactValidationError('文件不是可读取的 P4 XLSX 受控工作簿')
  }

  const summary = requiredSheet(workbook, '报价明细')
  const approval = requiredSheet(workbook, '审批与版本')
  const templateVersion = text(approval.rows[1]?.[1])
  if (templateVersion !== P4_ARTIFACT_TEMPLATE_VERSION) {
    const suffix = templateVersion === 'internal-quote-p4-v1'
      ? '旧 P4 v1 没有完整原始参数，请在内部报价台修改后重新提交并最终放行'
      : `期望 ${P4_ARTIFACT_TEMPLATE_VERSION}，实际 ${templateVersion || '未知版本'}`
    throw new P4ArtifactValidationError(`当前受控文件不能直接转换：${suffix}`)
  }
  if (text(approval.rows[3]?.[1]) !== 'P4 最终业务放行') {
    throw new P4ArtifactValidationError('当前工作簿不是 P4 最终业务放行文件')
  }
  if (text(approval.rows[4]?.[1]) !== '最终业务放行完成，可交接客价转换台') {
    throw new P4ArtifactValidationError('P4 放行边界标记缺失或已被修改')
  }

  const structured = requiredSheet(workbook, '结构化数据')
  const structuredDataSchemaVersion = text(structured.rows[1]?.[1])
  if (structuredDataSchemaVersion !== P4_STRUCTURED_DATA_SCHEMA_VERSION) {
    throw new P4ArtifactValidationError(`不支持的 P4 结构化数据版本：${structuredDataSchemaVersion || '未知版本'}`)
  }
  const chunkRows = parseStructuredRows(structured.rows)
  const referenceSnapshot = reconstructJson(chunkRows, 'reference_snapshot', 'quote')
  const sections = {} as Record<P4SectionCode, P4InternalQuoteSection>

  P4_SECTION_CODES.forEach((code) => {
    const sectionRows = chunkRows.filter((row) => row.code === code)
    const metadata = sectionRows[0]
    if (!metadata) {
      throw new P4ArtifactValidationError(`P4 结构化数据缺少 ${code} 分段`)
    }
    if (sectionRows.some((row) => (
      row.name !== metadata.name
      || row.status !== metadata.status
      || row.revision !== metadata.revision
      || row.calculationStatus !== metadata.calculationStatus
      || row.dependencyStatus !== metadata.dependencyStatus
      || row.calculationHash !== metadata.calculationHash
      || row.isRequired !== metadata.isRequired
    ))) {
      throw new P4ArtifactValidationError(`${metadata.name || code} 的结构化分片元数据不一致`)
    }
    if (metadata.isRequired && !['approved', 'not_applicable'].includes(metadata.status)) {
      throw new P4ArtifactValidationError(`${metadata.name || code} 尚未最终通过`)
    }
    if (metadata.isRequired && metadata.dependencyStatus !== 'current') {
      throw new P4ArtifactValidationError(`${metadata.name || code} 依赖状态不是 current`)
    }
    if (metadata.isRequired && metadata.status === 'approved' && metadata.calculationStatus !== 'valid') {
      throw new P4ArtifactValidationError(`${metadata.name || code} 计算状态不是 valid`)
    }
    if (metadata.isRequired && metadata.status === 'not_applicable' && metadata.calculationStatus !== 'not_applicable') {
      throw new P4ArtifactValidationError(`${metadata.name || code} 的不适用计算状态无效`)
    }
    const payload = reconstructJson(chunkRows, 'payload', code)
    const calculation = reconstructJson(chunkRows, 'calculation', code)
    if (metadata.isRequired && metadata.status === 'approved') {
      if (text(calculation.calculation_hash as XlsxCellValue) !== metadata.calculationHash) {
        throw new P4ArtifactValidationError(`${metadata.name || code} 计算 hash 与结构化清单不一致`)
      }
      if (text(calculation.formula_version as XlsxCellValue) !== text(summary.rows[2]?.[5])) {
        throw new P4ArtifactValidationError(`${metadata.name || code} 公式版本与报价清单不一致`)
      }
      if (text(calculation.reference_snapshot_id as XlsxCellValue) !== text(summary.rows[2]?.[7])) {
        throw new P4ArtifactValidationError(`${metadata.name || code} 参考快照与报价清单不一致`)
      }
    }
    sections[code] = {
      code,
      name: metadata.name,
      status: metadata.status,
      revision: metadata.revision,
      calculationStatus: metadata.calculationStatus,
      dependencyStatus: metadata.dependencyStatus,
      calculationHash: metadata.calculationHash,
      isRequired: metadata.isRequired,
      payload,
      calculation,
    }
  })

  return {
    templateVersion,
    structuredDataSchemaVersion,
    quoteNo: text(summary.rows[1]?.[1]),
    versionLabel: text(summary.rows[1]?.[3]),
    customer: text(summary.rows[1]?.[5]),
    quantity: numberValue(summary.rows[1]?.[7]),
    productName: text(summary.rows[2]?.[1]),
    factoryAndWorkshop: text(summary.rows[2]?.[3]),
    formulaVersion: text(summary.rows[2]?.[5]),
    referenceSnapshotId: text(summary.rows[2]?.[7]),
    referenceSnapshot,
    sections,
  }
}
