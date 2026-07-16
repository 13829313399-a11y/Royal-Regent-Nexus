export type InternalQuoteSectionCode =
  | 'sales'
  | 'engineering'
  | 'electronic'
  | 'molding'
  | 'painting'
  | 'slush'
  | 'sewing'
  | 'assembly'

export type InternalQuoteSectionStatus =
  | 'draft'
  | 'pending_review'
  | 'approved'
  | 'rejected'
  | 'na_pending'
  | 'not_applicable'

export type InternalQuoteStatus =
  | 'drafting'
  | 'pending_review'
  | 'rejected'
  | 'fully_approved'
  | 'final_pending'
  | 'released'
  | 'exported'
  | 'archived'

export type InternalQuoteInitiatorDepartment = 'sales-business' | 'engineering'
export type InternalQuoteCurrency = 'HKD' | 'RMB' | 'USD'

export interface InternalQuoteCostLine {
  id: string
  item: string
  specification: string
  quantity: number
  unit: string
  unitPrice: number
  currency: InternalQuoteCurrency
  formula: string
  amountHkd: number
}

export interface InternalQuoteSection {
  code: InternalQuoteSectionCode
  label: string
  owner: string
  status: InternalQuoteSectionStatus
  isRequired: boolean
  revision: number
  totalHkd: number
  updatedAt: string
  submittedBy?: string
  reviewer?: string
  reviewedAt?: string
  notApplicableReason?: string
  formulaHint: string
  dependencies: string[]
  warnings: string[]
  lines: InternalQuoteCostLine[]
  attachments: InternalQuoteAttachmentRecord[]
  payload: Record<string, unknown>
  calculationStatus: string
  dependencyStatus: string
}

export interface InternalQuoteActivity {
  id: string
  action: string
  title: string
  detail: string
  actor: string
  department: string
  createdAt: string
}

export interface InternalQuoteComment {
  id: string
  author: string
  department: string
  content: string
  createdAt: string
}

export interface InternalQuoteViewRecord {
  id: string
  viewer: string
  department: string
  device: string
  ipAddress: string
  viewedAt: string
}

export interface InternalQuoteExportRecord {
  id: string
  fileName: string
  templateName: string
  exportedBy: string
  exportedAt: string
  sha256: string
  status: 'current' | 'superseded'
  releaseStage: string
}

export interface InternalQuoteAttachmentRecord {
  id: string
  fileName: string
  contentType: string
  sizeBytes: number
  sha256: string
  uploadedBy: string
  uploadedAt: string
}

export interface InternalQuoteShippingScenario {
  name: string
  totalCartons: number
  freightHkd: number
  liftHkd: number
  afterSettlementHkd: number
  totalUsd: number
}

export interface InternalQuote {
  id: string
  quoteNo: string
  productName: string
  customer: string
  versionLabel: string
  factoryId: string
  factoryName: string
  workshopCode: string
  workshopName: string
  initiatorDepartment: InternalQuoteInitiatorDepartment
  initiatorName: string
  businessOwnerId: string
  businessOwner: string
  quantity: number
  targetDate: string
  remark: string
  createdAt: string
  updatedAt: string
  status: InternalQuoteStatus
  fxRmbHkd: number
  fxHkdUsd: number
  fxRmbUsd: number
  referenceSnapshotId: string
  formulaVersion: string
  headerRevision: number
  finalReleaseStatus: string
  factoryPriceHkd: number
  summaryComponents: Record<string, number>
  summaryWarnings: string[]
  shippingScenarios: InternalQuoteShippingScenario[]
  finalSubmittedBy?: string
  finalApprovedBy?: string
  finalApprovedAt?: string
  sections: InternalQuoteSection[]
  activities: InternalQuoteActivity[]
  comments: InternalQuoteComment[]
  viewRecords: InternalQuoteViewRecord[]
  exports: InternalQuoteExportRecord[]
}

export interface InternalQuoteCreatePayload {
  quoteNo: string
  productName: string
  customer: string
  versionLabel: string
  initiatorDepartment: InternalQuoteInitiatorDepartment
  businessOwnerId: string
  businessOwner: string
  quantity: number
  targetDate: string
  remark: string
}

export interface InternalQuoteBusinessOwner {
  id: string
  username: string
  displayName: string
}
