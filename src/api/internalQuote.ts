import { http } from '@/lib/http'
import type {
  InternalQuoteAttachment,
  InternalQuoteAuditLog,
  InternalQuoteCostLine,
  InternalQuoteCreateInput,
  InternalQuoteDepartment,
  InternalQuoteDetail,
  InternalQuoteExportFile,
  InternalQuoteImportPreview,
  InternalQuoteImportType,
  InternalQuoteReviewInput,
  InternalQuoteSection,
  InternalQuoteSectionPayload,
  InternalQuoteSectionStatus,
  InternalQuoteStatus,
  InternalQuoteSummary,
  InternalQuoteWorkshop,
} from '@/types/internalQuote'

interface ApiCostLine {
  id: string
  category: string
  item_name: string
  specification: string
  quantity: number
  unit_price_hkd: number
  amount_hkd: number
  note: string
  fields?: Record<string, unknown>
}

interface ApiSectionPayload {
  currency: 'HKD'
  loss_pct: number
  parameters?: Record<string, unknown>
  reference_snapshot?: Record<string, unknown>
  rows: ApiCostLine[]
}

interface ApiSection {
  id: string
  quote_id: string
  department: InternalQuoteDepartment
  department_name: string
  status: InternalQuoteSectionStatus
  payload: ApiSectionPayload
  calculation: {
    formula_version?: string
    subtotal_hkd: number
    loss_amount_hkd: number
    total_hkd: number
    total_rmb?: number
    total_usd?: number
    line_breakdown?: Array<{ line_id: string; label: string; formula: string; amount_hkd: number }>
    warnings?: string[]
    reference_snapshot?: Record<string, unknown>
  }
  revision: number
  filled_by: string
  filled_at: string
  submitted_by: string
  submitted_at: string
  reviewed_by: string
  reviewed_at: string
  review_comment: string
  updated_at: string
}

interface ApiAuditLog {
  id: string
  quote_id: string
  department: string
  actor_id: string
  actor_name: string
  action: string
  detail: string
  created_at: string
}

interface ApiQuoteSummary {
  id: string
  factory_id: string
  workshop_code: string
  workshop_name: string
  quote_no: string
  product_name: string
  customer: string
  qty: number
  version_label: string
  status: InternalQuoteStatus
  approved_count: number
  total_sections: number
  total_hkd: number
  created_by: string
  created_by_name: string
  created_at: string
  updated_at: string
}

interface ApiQuoteDetail extends ApiQuoteSummary {
  sections: ApiSection[]
  audit_logs: ApiAuditLog[]
}

interface ApiImportPreview {
  batch_id: string
  quote_id: string
  import_type: InternalQuoteImportType
  target_department: InternalQuoteDepartment
  source_file_name: string
  source_sha256: string
  sheet_name: string
  header_row: number
  rows: ApiCostLine[]
  parameters?: Record<string, unknown>
  warnings?: string[]
  status: 'previewed' | 'confirmed'
  created_by_name: string
  created_at: string
  confirmed_by_name: string
  confirmed_at: string
}

interface ApiAttachment {
  id: string
  quote_id: string
  department: string
  file_name: string
  content_type: string
  size_bytes: number
  sha256: string
  uploaded_by_name: string
  uploaded_at: string
}

interface ApiExportFile {
  id: string
  quote_id: string
  file_name: string
  content_type: string
  size_bytes: number
  sha256: string
  section_revisions: Record<string, number>
  status: 'current' | 'superseded'
  exported_by_name: string
  exported_at: string
  superseded_at: string
}

function toCostLine(row: ApiCostLine): InternalQuoteCostLine {
  return {
    id: row.id,
    category: row.category,
    itemName: row.item_name,
    specification: row.specification,
    quantity: row.quantity,
    unitPriceHkd: row.unit_price_hkd,
    amountHkd: row.amount_hkd,
    note: row.note,
    fields: row.fields ?? {},
  }
}

function fromCostLine(row: InternalQuoteCostLine): ApiCostLine {
  return {
    id: row.id,
    category: row.category,
    item_name: row.itemName,
    specification: row.specification,
    quantity: Number(row.quantity) || 0,
    unit_price_hkd: Number(row.unitPriceHkd) || 0,
    amount_hkd: Number(row.amountHkd) || 0,
    note: row.note,
    fields: row.fields ?? {},
  }
}

function toSectionPayload(payload: ApiSectionPayload): InternalQuoteSectionPayload {
  return {
    currency: payload.currency,
    lossPct: payload.loss_pct,
    parameters: payload.parameters ?? {},
    referenceSnapshot: payload.reference_snapshot ?? {},
    rows: payload.rows.map(toCostLine),
  }
}

function fromSectionPayload(payload: InternalQuoteSectionPayload): ApiSectionPayload {
  return {
    currency: payload.currency,
    loss_pct: Number(payload.lossPct) || 0,
    parameters: payload.parameters ?? {},
    reference_snapshot: payload.referenceSnapshot ?? {},
    rows: payload.rows.map(fromCostLine),
  }
}

function toSection(section: ApiSection): InternalQuoteSection {
  return {
    id: section.id,
    quoteId: section.quote_id,
    department: section.department,
    departmentName: section.department_name,
    status: section.status,
    payload: toSectionPayload(section.payload),
    calculation: {
      formulaVersion: section.calculation.formula_version ?? 'p1-generic-v1',
      subtotalHkd: section.calculation.subtotal_hkd,
      lossAmountHkd: section.calculation.loss_amount_hkd,
      totalHkd: section.calculation.total_hkd,
      totalRmb: section.calculation.total_rmb ?? 0,
      totalUsd: section.calculation.total_usd ?? 0,
      lineBreakdown: (section.calculation.line_breakdown ?? []).map((row) => ({
        lineId: row.line_id,
        label: row.label,
        formula: row.formula,
        amountHkd: row.amount_hkd,
      })),
      warnings: section.calculation.warnings ?? [],
      referenceSnapshot: section.calculation.reference_snapshot ?? {},
    },
    revision: section.revision,
    filledBy: section.filled_by,
    filledAt: section.filled_at,
    submittedBy: section.submitted_by,
    submittedAt: section.submitted_at,
    reviewedBy: section.reviewed_by,
    reviewedAt: section.reviewed_at,
    reviewComment: section.review_comment,
    updatedAt: section.updated_at,
  }
}

function toAuditLog(row: ApiAuditLog): InternalQuoteAuditLog {
  return {
    id: row.id,
    quoteId: row.quote_id,
    department: row.department,
    actorId: row.actor_id,
    actorName: row.actor_name,
    action: row.action,
    detail: row.detail,
    createdAt: row.created_at,
  }
}

function toSummary(quote: ApiQuoteSummary): InternalQuoteSummary {
  return {
    id: quote.id,
    factoryId: quote.factory_id,
    workshopCode: quote.workshop_code,
    workshopName: quote.workshop_name,
    quoteNo: quote.quote_no,
    productName: quote.product_name,
    customer: quote.customer,
    qty: quote.qty,
    versionLabel: quote.version_label,
    status: quote.status,
    approvedCount: quote.approved_count,
    totalSections: quote.total_sections,
    totalHkd: quote.total_hkd,
    createdBy: quote.created_by,
    createdByName: quote.created_by_name,
    createdAt: quote.created_at,
    updatedAt: quote.updated_at,
  }
}

function toDetail(quote: ApiQuoteDetail): InternalQuoteDetail {
  return {
    ...toSummary(quote),
    sections: quote.sections.map(toSection),
    auditLogs: quote.audit_logs.map(toAuditLog),
  }
}

function toImportPreview(row: ApiImportPreview): InternalQuoteImportPreview {
  return {
    batchId: row.batch_id,
    quoteId: row.quote_id,
    importType: row.import_type,
    targetDepartment: row.target_department,
    sourceFileName: row.source_file_name,
    sourceSha256: row.source_sha256,
    sheetName: row.sheet_name,
    headerRow: row.header_row,
    rows: row.rows.map(toCostLine),
    parameters: row.parameters ?? {},
    warnings: row.warnings ?? [],
    status: row.status,
    createdByName: row.created_by_name,
    createdAt: row.created_at,
    confirmedByName: row.confirmed_by_name,
    confirmedAt: row.confirmed_at,
  }
}

function toAttachment(row: ApiAttachment): InternalQuoteAttachment {
  return {
    id: row.id,
    quoteId: row.quote_id,
    department: row.department,
    fileName: row.file_name,
    contentType: row.content_type,
    sizeBytes: row.size_bytes,
    sha256: row.sha256,
    uploadedByName: row.uploaded_by_name,
    uploadedAt: row.uploaded_at,
  }
}

function toExportFile(row: ApiExportFile): InternalQuoteExportFile {
  return {
    id: row.id,
    quoteId: row.quote_id,
    fileName: row.file_name,
    contentType: row.content_type,
    sizeBytes: row.size_bytes,
    sha256: row.sha256,
    sectionRevisions: row.section_revisions,
    status: row.status,
    exportedByName: row.exported_by_name,
    exportedAt: row.exported_at,
    supersededAt: row.superseded_at,
  }
}

export const internalQuoteApi = {
  async listWorkshops(factoryId: string) {
    const response = await http.get<InternalQuoteWorkshop[]>('/internal-quotes/workshops', {
      params: { factory_id: factoryId },
    })
    return response.data
  },

  async listQuotes(
    factoryId: string,
    filters: { workshopCode?: string; status?: string; keyword?: string } = {},
  ) {
    const response = await http.get<ApiQuoteSummary[]>('/internal-quotes', {
      params: {
        factory_id: factoryId,
        ...(filters.workshopCode ? { workshop_code: filters.workshopCode } : {}),
        ...(filters.status ? { status_filter: filters.status } : {}),
        ...(filters.keyword ? { keyword: filters.keyword } : {}),
      },
    })
    return response.data.map(toSummary)
  },

  async getQuote(quoteId: string) {
    const response = await http.get<ApiQuoteDetail>(`/internal-quotes/${quoteId}`)
    return toDetail(response.data)
  },

  async createQuote(payload: InternalQuoteCreateInput) {
    const response = await http.post<ApiQuoteDetail>('/internal-quotes', {
      factory_id: payload.factoryId,
      workshop_code: payload.workshopCode,
      quote_no: payload.quoteNo,
      product_name: payload.productName,
      customer: payload.customer,
      qty: payload.qty,
      version_label: payload.versionLabel,
    })
    return toDetail(response.data)
  },

  async updateSection(
    quoteId: string,
    department: InternalQuoteDepartment,
    revision: number,
    payload: InternalQuoteSectionPayload,
    submit = false,
  ) {
    const response = await http.put<ApiQuoteDetail>(
      `/internal-quotes/${quoteId}/sections/${department}`,
      { revision, payload: fromSectionPayload(payload), submit },
    )
    return toDetail(response.data)
  },

  async reviewSection(
    quoteId: string,
    department: InternalQuoteDepartment,
    payload: InternalQuoteReviewInput,
  ) {
    const response = await http.post<ApiQuoteDetail>(
      `/internal-quotes/${quoteId}/sections/${department}/review`,
      payload,
    )
    return toDetail(response.data)
  },

  async previewImport(quoteId: string, importType: InternalQuoteImportType, file: File) {
    const form = new FormData()
    form.append('file', file)
    const response = await http.post<ApiImportPreview>(
      `/internal-quotes/${quoteId}/imports/${importType}/preview`,
      form,
    )
    return toImportPreview(response.data)
  },

  async listImports(quoteId: string) {
    const response = await http.get<ApiImportPreview[]>(`/internal-quotes/${quoteId}/imports`)
    return response.data.map(toImportPreview)
  },

  async confirmImport(
    quoteId: string,
    batchId: string,
    revision: number,
    mode: 'append' | 'replace',
  ) {
    const response = await http.post<ApiQuoteDetail>(
      `/internal-quotes/${quoteId}/imports/${batchId}/confirm`,
      { revision, mode },
    )
    return toDetail(response.data)
  },

  async uploadAttachment(quoteId: string, department: InternalQuoteDepartment, file: File) {
    const form = new FormData()
    form.append('department', department)
    form.append('file', file)
    const response = await http.post<ApiAttachment>(`/internal-quotes/${quoteId}/attachments`, form)
    return toAttachment(response.data)
  },

  async listAttachments(quoteId: string) {
    const response = await http.get<ApiAttachment[]>(`/internal-quotes/${quoteId}/attachments`)
    return response.data.map(toAttachment)
  },

  async downloadAttachment(quoteId: string, attachmentId: string) {
    const response = await http.get<Blob>(
      `/internal-quotes/${quoteId}/attachments/${attachmentId}/download`,
      { responseType: 'blob' },
    )
    return response.data
  },

  async listExports(quoteId: string) {
    const response = await http.get<ApiExportFile[]>(`/internal-quotes/${quoteId}/exports`)
    return response.data.map(toExportFile)
  },

  async downloadRetainedExport(quoteId: string, exportId: string) {
    const response = await http.get<Blob>(
      `/internal-quotes/${quoteId}/exports/${exportId}/download`,
      { responseType: 'blob' },
    )
    return response.data
  },

  async exportQuote(quoteId: string) {
    const response = await http.get<Blob>(`/internal-quotes/${quoteId}/export`, {
      responseType: 'blob',
    })
    return response.data
  },
}
