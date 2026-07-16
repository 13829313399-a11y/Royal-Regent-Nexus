export type InternalQuoteStatus = 'drafting' | 'fully_approved' | 'exported' | 'reopened' | 'archived'
export type InternalQuoteSectionStatus = 'draft' | 'pending_review' | 'approved' | 'rejected'
export type InternalQuoteImportType = 'mold' | 'electronic' | 'sewing' | 'assembly' | 'painting'
export type InternalQuoteDepartment =
  | 'sales'
  | 'engineering'
  | 'electronic'
  | 'molding'
  | 'painting'
  | 'slush'
  | 'sewing'
  | 'assembly'

export interface InternalQuoteWorkshop {
  code: string
  name: string
}

export interface InternalQuoteCostLine {
  id: string
  category: string
  itemName: string
  specification: string
  quantity: number
  unitPriceHkd: number
  amountHkd: number
  note: string
  fields: Record<string, unknown>
}

export interface InternalQuoteSectionPayload {
  currency: 'HKD'
  lossPct: number
  parameters: Record<string, unknown>
  referenceSnapshot: Record<string, unknown>
  rows: InternalQuoteCostLine[]
}

export interface InternalQuoteLineCalculation {
  lineId: string
  label: string
  formula: string
  amountHkd: number
}

export interface InternalQuoteSectionCalculation {
  formulaVersion: string
  subtotalHkd: number
  lossAmountHkd: number
  totalHkd: number
  totalRmb: number
  totalUsd: number
  lineBreakdown: InternalQuoteLineCalculation[]
  warnings: string[]
  referenceSnapshot: Record<string, unknown>
}

export interface InternalQuoteSection {
  id: string
  quoteId: string
  department: InternalQuoteDepartment
  departmentName: string
  status: InternalQuoteSectionStatus
  payload: InternalQuoteSectionPayload
  calculation: InternalQuoteSectionCalculation
  revision: number
  filledBy: string
  filledAt: string
  submittedBy: string
  submittedAt: string
  reviewedBy: string
  reviewedAt: string
  reviewComment: string
  updatedAt: string
}

export interface InternalQuoteAuditLog {
  id: string
  quoteId: string
  department: string
  actorId: string
  actorName: string
  action: string
  detail: string
  createdAt: string
}

export interface InternalQuoteSummary {
  id: string
  factoryId: string
  workshopCode: string
  workshopName: string
  quoteNo: string
  productName: string
  customer: string
  qty: number
  versionLabel: string
  status: InternalQuoteStatus
  approvedCount: number
  totalSections: number
  totalHkd: number
  createdBy: string
  createdByName: string
  createdAt: string
  updatedAt: string
}

export interface InternalQuoteDetail extends InternalQuoteSummary {
  sections: InternalQuoteSection[]
  auditLogs: InternalQuoteAuditLog[]
}

export interface InternalQuoteCreateInput {
  factoryId: string
  workshopCode: string
  quoteNo: string
  productName: string
  customer: string
  qty: number
  versionLabel: string
}

export interface InternalQuoteReviewInput {
  action: 'approve' | 'reject' | 'reopen'
  comment?: string
}

export interface InternalQuoteImportPreview {
  batchId: string
  quoteId: string
  importType: InternalQuoteImportType
  targetDepartment: InternalQuoteDepartment
  sourceFileName: string
  sourceSha256: string
  sheetName: string
  headerRow: number
  rows: InternalQuoteCostLine[]
  parameters: Record<string, unknown>
  warnings: string[]
  status: 'previewed' | 'confirmed'
  createdByName: string
  createdAt: string
  confirmedByName: string
  confirmedAt: string
}

export interface InternalQuoteAttachment {
  id: string
  quoteId: string
  department: string
  fileName: string
  contentType: string
  sizeBytes: number
  sha256: string
  uploadedByName: string
  uploadedAt: string
}

export interface InternalQuoteExportFile {
  id: string
  quoteId: string
  fileName: string
  contentType: string
  sizeBytes: number
  sha256: string
  sectionRevisions: Record<string, number>
  status: 'current' | 'superseded'
  exportedByName: string
  exportedAt: string
  supersededAt: string
}
