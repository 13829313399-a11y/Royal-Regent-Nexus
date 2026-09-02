export type InternalQuoteSectionCode =
  | 'sales'
  | 'engineering'
  | 'electronic'
  | 'molding'
  | 'painting'
  | 'slush'
  | 'sewing'
  | 'hair'
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
export type InternalQuoteWorkflowMode = 'section_review' | 'whole_quote_review'

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
  submittedById?: string
  reviewer?: string
  reviewedAt?: string
  notApplicableReason?: string
  formulaHint: string
  dependencies: string[]
  warnings: string[]
  lines: InternalQuoteCostLine[]
  attachments: InternalQuoteAttachmentRecord[]
  payload: Record<string, unknown>
  calculation: Record<string, unknown>
  calculationStatus: string
  dependencyStatus: string
  filledAt: string
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
  isImportSource: boolean
  importBatchId: string
  importType: string
}

export interface InternalQuoteShippingScenario {
  name: string
  totalCartons: number
  freightHkd: number
  liftHkd: number
  afterSettlementHkd: number
  totalUsd: number
}

export interface InternalQuoteRr2SummaryValue {
  key: string
  label: string
  value: number
  format?: string
  display?: boolean
}

export interface InternalQuoteTaxSummaryValue {
  key: string
  label: string
  amountHkd: number
  ratePercent: number | null
  deductionHkd: number | null
}

export interface InternalQuoteShippingPriceRow {
  name: string
  totalCartons: number
  shippingFloorHkd: number
  freightHkd: number
  liftHkd: number
  withFreightHkd: number
  afterMarkupHkd: number
  afterSettlementHkd: number
  totalHkd: number
  totalUsd: number
  moldAmortizationUsd: number
  totalWithMoldUsd: number
}

export interface InternalQuoteMarkupTier {
  moq: number
  markup: number
  isActive: boolean
  includeInOutput: boolean
}

export interface InternalQuotePricingGroup {
  id: string
  name: string
  costHkd: number
  pricingBaseHkd: number
  markup: number
  settlement: number
  quotedHkd: number
  inheritsMainMarkup: boolean
}

export interface InternalQuoteGlobalPricing {
  costHkd: number
  pricingBaseHkd: number
  markup: number
  settlement: number
  quotedHkd: number
}

export interface InternalQuoteRr2CostSummary {
  currency: string
  indonesiaFreightHkd: number
  t1: InternalQuoteRr2SummaryValue[]
  t2: InternalQuoteRr2SummaryValue[]
  t3: InternalQuoteRr2SummaryValue[]
  moldingMaterialBreakdown?: { totalHkd: number; importedHkd: number; domesticHkd: number }
  t4: InternalQuoteTaxSummaryValue[]
  rmbPurchaseCostHkd: number
  totalDeductionHkd: number
  afterDeductionCostHkd: number
  shippingPricing: {
    enabled: boolean
    freightEnabled: boolean
    liftingEnabled: boolean
    freightSharePercent: number
    liftSharePercent: number
    markup: number
    activeMarkupMoq: number
    markupTiers: InternalQuoteMarkupTier[]
    miscRatio: number
    settlement: number
    factoryPriceHkd: number
    additionalTaxHkd: number
    shippingFloorHkd: number
    hkdUsd: number
    moldAmortizationUsd: number
    pricingMode: 'standard' | 'component'
    pricingGroups: InternalQuotePricingGroup[]
    globalPricing: InternalQuoteGlobalPricing
    rows: InternalQuoteShippingPriceRow[]
  }
}

export interface InternalQuote {
  id: string
  quoteNo: string
  productName: string
  quoteType: 'single' | 'series' | 'multi_region'
  batchId: string
  batchQuoteNo: string
  batchPosition: number
  batchSize: number
  baselineQuoteId: string
  regionCode: '' | 'mainland' | 'indonesia'
  customer: string
  versionLabel: string
  factoryId: string
  factoryName: string
  workshopCode: string
  workshopName: string
  initiatorDepartment: InternalQuoteInitiatorDepartment
  createdById: string
  initiatorName: string
  businessOwnerId: string
  businessOwner: string
  targetCustomerPrice: string
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
  referenceSnapshot: Record<string, unknown>
  formulaVersion: string
  currentFormulaVersion: string
  moduleVersion: string
  headerRevision: number
  finalReleaseStatus: string
  factoryPriceHkd: number
  summaryComponents: Record<string, number>
  summaryWarnings: string[]
  shippingScenarios: InternalQuoteShippingScenario[]
  rr2CostSummary: InternalQuoteRr2CostSummary
  finalSubmittedBy?: string
  finalSubmittedById?: string
  finalApprovedBy?: string
  finalApprovedAt?: string
  finalReviewComment?: string
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
  targetCustomerPrice: string
  quantity: number
  targetDate: string
  remark: string
  participatingSections: InternalQuoteSectionCode[]
  quoteType?: 'single' | 'series' | 'multi_region'
  products?: InternalQuoteCreateProduct[]
  pricingComponents?: string[]
}

export interface InternalQuoteCreateProduct {
  productName: string
  quantity: number
  regionCode: '' | 'mainland' | 'indonesia'
  imageFile?: File | null
  documentFiles?: InternalQuoteCreateDocument[]
  pricingComponents?: string[]
}

export interface InternalQuoteCreateDocument {
  file: File
  department: InternalQuoteSectionCode
}

export interface InternalQuoteBatchProduct {
  quoteId: string
  quoteNo: string
  productName: string
  quantity: number
  position: number
  batchSize: number
  quoteType: 'single' | 'series' | 'multi_region'
  regionCode: '' | 'mainland' | 'indonesia'
  status: InternalQuoteStatus
  headerRevision: number
  isBaseline: boolean
  differsFromBaseline: boolean
  differentHeaderFields: string[]
  differentSections: InternalQuoteSectionCode[]
  differentSectionDetails: Partial<Record<InternalQuoteSectionCode, string[]>>
  mainImage: null | {
    id: string
    fileName: string
    contentType: string
    sizeBytes: number
    uploadedByName: string
    uploadedAt: string
  }
}

export interface InternalQuoteBusinessOwner {
  id: string
  username: string
  displayName: string
}
