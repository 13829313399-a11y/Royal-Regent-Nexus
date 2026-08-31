import { http } from '@/lib/http'
import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

export interface InternalQuoteHttpClient {
  get<T = unknown>(url: string, config?: unknown): Promise<{ data: T; headers?: Record<string, unknown> }>
  post<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T; headers?: Record<string, unknown> }>
  put<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T; headers?: Record<string, unknown> }>
  patch<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T; headers?: Record<string, unknown> }>
  delete<T = unknown>(url: string, config?: unknown): Promise<{ data: T; headers?: Record<string, unknown> }>
}

export interface ApiInternalQuoteSection {
  id: string
  department: string
  department_name: string
  status: string
  payload: Record<string, unknown>
  calculation: Record<string, unknown>
  calculation_status: string
  calculation_hash: string
  calculation_formula_version: string
  calculation_reference_snapshot_id: string
  calculated_at: string
  dependency_hash: string
  dependency_status: string
  revision: number
  is_required: boolean
  filled_by: string
  filled_at: string
  submitted_by: string
  submitted_by_id: string
  submitted_at: string
  reviewed_by: string
  reviewed_at: string
  review_comment: string
  updated_at: string
}

export interface ApiInternalQuote {
  id: string
  factory_id: string
  workshop_code: string
  workshop_name: string
  quote_no: string
  product_name: string
  quote_type: 'single' | 'series' | 'multi_region'
  batch_id: string
  batch_quote_no: string
  batch_position: number
  batch_size: number
  baseline_quote_id: string
  region_code: '' | 'mainland' | 'indonesia'
  customer: string
  qty: number
  version_label: string
  status: string
  initiator_department: string
  business_owner_id: string
  business_owner_name: string
  target_customer_price?: string
  target_date: string
  remark: string
  module_version: string
  reference_snapshot_id: string
  formula_version: string
  header_revision: number
  cloned_from_quote_id: string
  archived_by: string
  archived_at: string
  archive_reason: string
  final_release_status: string
  final_submission_revision: number
  final_submission_manifest: Record<string, unknown>
  final_submitted_by: string
  final_submitted_by_name: string
  final_submitted_at: string
  final_reviewed_by: string
  final_reviewed_by_name: string
  final_reviewed_at: string
  final_review_comment: string
  final_release_revision: number
  final_release_invalidated_at: string
  final_release_invalidation_reason: string
  created_by: string
  created_by_name: string
  created_at: string
  updated_at: string
  sections: ApiInternalQuoteSection[]
}

export function internalQuoteAttachmentPreviewUrl(quoteId: string, attachmentId: string) {
  const baseUrl = String(import.meta.env?.VITE_API_BASE_URL ?? '/api').replace(/\/+$/, '')
  return `${baseUrl}/internal-quotes/${encodeURIComponent(quoteId)}/attachments/${encodeURIComponent(attachmentId)}/preview`
}

export interface ApiInternalQuotePage {
  items: ApiInternalQuote[]
  total: number
  page: number
  page_size: number
  total_pages: number
  customers: string[]
}

export interface ApiInternalQuoteAudit {
  id: string
  department: string
  actor_id: string
  actor_name: string
  action: string
  detail: string
  old_revision: number | null
  new_revision: number | null
  reason: string
  created_at: string
}

export interface ApiInternalQuoteTimeline {
  business_events: ApiInternalQuoteAudit[]
  view_records: ApiInternalQuoteAudit[]
}

export interface ApiInternalQuoteReferenceSet {
  id: string
  quote_id: string
  factory_id: string
  version_label: string
  formula_version: string
  source_type: string
  source_revision: number
  snapshot: Record<string, unknown>
  sha256: string
  is_current: boolean
  created_by: string
  created_by_name: string
  created_at: string
  superseded_at: string
}

export interface ApiInternalQuoteSummary {
  quote_id: string
  status: string
  formula_version: string
  reference_snapshot_id: string
  factory_price_hkd: string
  mold_amortization_usd: string
  components_hkd: Record<string, string>
  rr2_cost_summary?: {
    currency: string
    indonesia_freight_hkd: string
    t1: Array<{ key: string; label: string; value: string; format?: string; display?: boolean }>
    t2: Array<{ key: string; label: string; value: string; format?: string; display?: boolean }>
    t3: Array<{ key: string; label: string; value: string; format?: string; display?: boolean }>
    molding_material_breakdown?: { total_hkd: string; imported_hkd: string; domestic_hkd: string }
    t4: Array<{ key: string; label: string; amount_hkd: string; rate_percent: string | null; deduction_hkd: string | null }>
    totals: { rmb_purchase_cost_hkd: string; total_deduction_hkd: string; after_deduction_cost_hkd: string }
    shipping_pricing: {
      enabled: boolean
      freight_enabled?: boolean
      lifting_enabled?: boolean
      freight_share_percent: string
      lift_share_percent: string
      markup: string
      active_markup_moq?: string
      markup_tiers?: Array<{ moq: string; markup: string; is_active: boolean; include_in_output?: boolean }>
      misc_ratio: string
      settlement: string
      factory_price_hkd: string
      additional_tax_hkd: string
      shipping_floor_hkd: string
      hkd_usd: string
      mold_amortization_usd: string
      pricing_mode?: 'standard' | 'component'
      pricing_groups?: Array<Record<string, string>>
      rows: Array<Record<string, unknown>>
    }
  }
  sections: Array<Record<string, unknown>>
  warnings: Array<Record<string, unknown>>
}

export interface ApiInternalQuoteAttachment {
  id: string
  quote_id: string
  department: string
  file_name: string
  content_type: string
  size_bytes: number
  sha256: string
  uploaded_by: string
  uploaded_by_name: string
  uploaded_at: string
  is_import_source: boolean
  import_batch_id: string
  import_type: string
}

export interface ApiInternalQuoteExport {
  id: string
  quote_id: string
  file_name: string
  content_type: string
  size_bytes: number
  sha256: string
  section_revisions: Record<string, number>
  status: string
  template_version: string
  formula_version: string
  reference_snapshot_id: string
  header_revision: number
  release_stage: string
  export_manifest: Record<string, unknown>
  exported_by: string
  exported_by_name: string
  exported_at: string
  superseded_at: string
}

export interface ApiInternalQuoteImportPreview {
  batch_id: string
  quote_id: string
  import_type: 'mold' | 'hardware' | 'electronic' | 'molding' | 'painting' | 'slush' | 'sewing' | 'hair' | 'assembly'
  target_department: string
  source_file_name: string
  source_sha256: string
  source_size_bytes: number
  preview_schema_version: string
  target_revision: number
  sheet_name: string
  header_row: number
  row_count: number
  payload_fragment: Record<string, unknown>
  diff_summary: Record<string, unknown>
  warnings: string[]
  status: string
  created_by_name: string
  created_at: string
  confirm_mode: string
  confirmed_revision: number
  confirmed_by_name: string
  confirmed_at: string
}

export interface ApiInternalQuoteImportConfirm {
  batch: ApiInternalQuoteImportPreview
  section: ApiInternalQuoteSection
}

export interface ApiInternalQuoteFinalRelease {
  quote: ApiInternalQuote
  review?: Record<string, unknown> | null
  export?: ApiInternalQuoteExport | null
}

export interface ApiInternalQuoteVersionCandidate {
  id: string
  quote_no: string
  version_label: string
  product_name: string
  customer: string
  status: string
  final_release_status: string
  final_release_revision: number
  updated_at: string
}

export interface ApiInternalQuoteFieldChange {
  path: string
  before: unknown
  after: unknown
}

export interface ApiInternalQuoteSectionComparison {
  section_code: string
  section_name: string
  before_status: string
  after_status: string
  before_revision: number
  after_revision: number
  before_total_hkd: string
  after_total_hkd: string
  delta_hkd: string
  payload_changes: ApiInternalQuoteFieldChange[]
}

export interface ApiInternalQuoteVersionComparison {
  base: ApiInternalQuoteVersionCandidate
  target: ApiInternalQuoteVersionCandidate
  header_changes: ApiInternalQuoteFieldChange[]
  sections: ApiInternalQuoteSectionComparison[]
  total_before_hkd: string
  total_after_hkd: string
  total_delta_hkd: string
}

export interface ApiInternalQuoteBusinessOwner {
  id: string
  username: string
  display_name: string
}

export interface ApiInternalQuoteCustomer {
  id: string
  factory_id: string
  name: string
  revision: number
  created_by: string
  created_by_name: string
  created_at: string
  updated_by: string
  updated_by_name: string
  updated_at: string
}

export interface ApiInternalQuoteSectionPreview {
  quote_id: string
  section_code: InternalQuoteSectionCode
  section_revision: number
  calculation_status: string
  calculation: Record<string, unknown>
  warnings: Array<Record<string, unknown>>
  saved_factory_price_hkd: string
  preview_factory_price_hkd: string
  delta_hkd: string
  components_hkd: Record<string, string>
  formula_version: string
  reference_snapshot_id: string
  generated_at: string
}

export type InternalQuoteDashboardPeriod = 'week' | 'month' | 'year'

export interface ApiInternalQuoteDashboard {
  factory_id: string
  period: InternalQuoteDashboardPeriod
  period_label: string
  period_start: string
  period_end: string
  totals: {
    total: number
    in_progress: number
    completed: number
    canceled: number
  }
  status_distribution: Array<{
    key: 'in_progress' | 'completed' | 'canceled'
    label: string
    count: number
    percentage: number
  }>
  customer_quote_counts: Array<{
    customer: string
    count: number
    percentage: number
  }>
  progress_items: Array<{
    quote_id: string
    quote_no: string
    product_name: string
    customer: string
    status: string
    approved_sections: number
    required_sections: number
    percentage: number
    updated_at: string
  }>
  customer_speed: Array<{
    customer: string
    completed_count: number
    average_hours: number
    average_days: number
    fastest_hours: number
    slowest_hours: number
  }>
}

export interface ApiInternalQuoteMaterialBaselineRow {
  material: string
  grade: string
  price_hkd_lb: string
}

export interface ApiInternalQuoteMachineBaselineRow {
  machine_range: string
  machine: string
  shift_price_hkd: string
}

export interface ApiInternalQuoteFreightBaselineRow {
  route_key: string
  route_name: string
  capacity_key: string
  freight_hkd: string
  lifting_hkd: string
}

export interface ApiInternalQuotePricingBaseline {
  factory_id: string
  workshop_code: string
  workshop_name: string
  revision: number
  source_type: 'default' | 'custom'
  material_prices: ApiInternalQuoteMaterialBaselineRow[]
  machine_prices: ApiInternalQuoteMachineBaselineRow[]
  freight_routes: ApiInternalQuoteFreightBaselineRow[]
  updated_by: string
  updated_by_name: string
  updated_at: string
}

export interface InternalQuotePricingBaselineUpdateRequest {
  revision: number
  workshop_name: string
  material_prices: ApiInternalQuoteMaterialBaselineRow[]
  machine_prices: ApiInternalQuoteMachineBaselineRow[]
  freight_routes: ApiInternalQuoteFreightBaselineRow[]
}

export interface InternalQuoteReferenceMaterialsUpdateRequest {
  revision: number
  material_prices: ApiInternalQuoteMaterialBaselineRow[]
}

export interface InternalQuoteCreateRequest {
  factory_id: string
  workshop_code: string
  workshop_name: string
  quote_no: string
  product_name: string
  customer: string
  qty: number
  version_label: string
  initiator_department: 'sales-business' | 'engineering'
  business_owner_id: string
  business_owner_name: string
  target_customer_price: string
  target_date: string
  remark: string
  participating_sections: InternalQuoteSectionCode[]
  workflow_mode: 'section_review' | 'whole_quote_review'
  quote_type: 'single' | 'series' | 'multi_region'
  products: Array<{
    product_name: string
    qty: number
    region_code: '' | 'mainland' | 'indonesia'
  }>
  pricing_components?: string[]
}

export interface ApiInternalQuoteAttachmentPreviewSheet {
  name: string
  rows: unknown[][]
  total_rows: number
  total_columns: number
  truncated: boolean
}

export interface ApiInternalQuoteAttachmentContentPreview {
  file_name: string
  kind: 'excel' | 'word'
  sheets: ApiInternalQuoteAttachmentPreviewSheet[]
  paragraphs: string[]
  warnings: string[]
}

export interface ApiInternalQuoteBatchProduct {
  quote_id: string
  quote_no: string
  product_name: string
  qty: number
  position: number
  batch_size: number
  quote_type: 'single' | 'series' | 'multi_region'
  region_code: '' | 'mainland' | 'indonesia'
  status: string
  header_revision: number
  is_baseline: boolean
  differs_from_baseline: boolean
  different_header_fields: string[]
  different_sections: InternalQuoteSectionCode[]
  different_section_details: Partial<Record<InternalQuoteSectionCode, string[]>>
  main_image: null | {
    id: string
    file_name: string
    content_type: string
    size_bytes: number
    uploaded_by_name: string
    uploaded_at: string
  }
}

export interface InternalQuoteCloneRequest {
  quote_no: string
  version_label: string
  business_owner_id: string
  business_owner_name: string
  target_customer_price?: string
  target_date: string
  remark?: string
  participating_sections?: InternalQuoteSectionCode[]
  workflow_mode?: 'section_review' | 'whole_quote_review'
}

export interface InternalQuoteHeaderUpdateRequest {
  revision: number
  product_name: string
  customer: string
  qty: number
  business_owner_id: string
  business_owner_name: string
  target_customer_price: string
  target_date: string
  remark: string
}

const quoteStatusQueryMap: Record<string, string> = {
  pending_review: 'section_reviewing',
  fully_approved: 'ready_for_final_review',
  final_pending: 'final_reviewing',
  released: 'fully_approved',
}

function backendQuoteStatus(status: string | undefined) {
  return status ? (quoteStatusQueryMap[status] ?? status) : ''
}

export function createInternalQuoteApi(client: InternalQuoteHttpClient = http) {
  return {
    async list(factoryId: string, options: { status?: string; keyword?: string; customer?: string; page?: number; pageSize?: number } = {}) {
      const response = await client.get<ApiInternalQuotePage>('/internal-quotes', {
        params: {
          factory_id: factoryId,
          include_sections: true,
          page: options.page ?? 1,
          page_size: options.pageSize ?? 10,
          ...(options.status ? { status: backendQuoteStatus(options.status) } : {}),
          ...(options.keyword ? { keyword: options.keyword } : {}),
          ...(options.customer ? { customer: options.customer } : {}),
        },
      })
      return response.data
    },
    async getDashboard(factoryId: string, period: InternalQuoteDashboardPeriod) {
      const response = await client.get<ApiInternalQuoteDashboard>('/internal-quotes/dashboard', {
        params: { factory_id: factoryId, period },
      })
      return response.data
    },
    async get(quoteId: string) {
      const response = await client.get<ApiInternalQuote>(`/internal-quotes/${quoteId}`)
      return response.data
    },
    async listBatchProducts(quoteId: string) {
      const response = await client.get<ApiInternalQuoteBatchProduct[]>(`/internal-quotes/${quoteId}/batch-products`)
      return response.data
    },
    async copyBatchBaseline(quoteId: string, targetQuoteId: string, revision: number) {
      const response = await client.post<ApiInternalQuote>(
        `/internal-quotes/${quoteId}/batch-products/${targetQuoteId}/copy-baseline`,
        { revision },
      )
      return response.data
    },
    async create(payload: InternalQuoteCreateRequest) {
      const response = await client.post<ApiInternalQuote>('/internal-quotes', payload)
      return response.data
    },
    async clone(quoteId: string, payload: InternalQuoteCloneRequest) {
      const response = await client.post<ApiInternalQuote>(`/internal-quotes/${quoteId}/clone`, payload)
      return response.data
    },
    async deleteQuote(quoteId: string, revision: number) {
      await client.delete(`/internal-quotes/${quoteId}`, {
        params: { revision },
      })
    },
    async updateHeader(quoteId: string, payload: InternalQuoteHeaderUpdateRequest) {
      const response = await client.patch<ApiInternalQuote>(`/internal-quotes/${quoteId}`, payload)
      return response.data
    },
    async archiveQuote(quoteId: string, revision: number, reason: string) {
      const response = await client.post<ApiInternalQuote>(`/internal-quotes/${quoteId}/archive`, { revision, reason })
      return response.data
    },
    async addParticipation(quoteId: string, revision: number, addSections: InternalQuoteSectionCode[]) {
      const response = await client.post<ApiInternalQuote>(`/internal-quotes/${quoteId}/participation`, {
        revision,
        add_sections: addSections,
      })
      return response.data
    },
    async removeParticipation(quoteId: string, revision: number, removeSections: InternalQuoteSectionCode[]) {
      const response = await client.post<ApiInternalQuote>(`/internal-quotes/${quoteId}/participation/remove`, {
        revision,
        remove_sections: removeSections,
      })
      return response.data
    },
    async listBusinessOwners(factoryId: string) {
      const response = await client.get<ApiInternalQuoteBusinessOwner[]>('/internal-quotes/business-owners', {
        params: { factory_id: factoryId },
      })
      return response.data
    },
    async listCustomers(factoryId: string) {
      const response = await client.get<ApiInternalQuoteCustomer[]>('/internal-quotes/customers', {
        params: { factory_id: factoryId },
      })
      return response.data
    },
    async createCustomer(factoryId: string, name: string) {
      const response = await client.post<ApiInternalQuoteCustomer>(
        '/internal-quotes/customers',
        { name },
        { params: { factory_id: factoryId } },
      )
      return response.data
    },
    async updateCustomer(customerId: string, name: string, revision: number) {
      const response = await client.put<ApiInternalQuoteCustomer>(
        `/internal-quotes/customers/${customerId}`,
        { name, revision },
      )
      return response.data
    },
    async deleteCustomer(customerId: string, revision: number) {
      await client.delete(`/internal-quotes/customers/${customerId}`, {
        params: { revision },
      })
    },
    async getPricingBaseline(factoryId: string, workshopCode = 'huaxing-workshop') {
      const response = await client.get<ApiInternalQuotePricingBaseline>('/internal-quotes/pricing-baseline', {
        params: { factory_id: factoryId, workshop_code: workshopCode },
      })
      return response.data
    },
    async updatePricingBaseline(
      factoryId: string,
      workshopCode: string,
      payload: InternalQuotePricingBaselineUpdateRequest,
    ) {
      const response = await client.put<ApiInternalQuotePricingBaseline>('/internal-quotes/pricing-baseline', payload, {
        params: { factory_id: factoryId, workshop_code: workshopCode },
      })
      return response.data
    },
    async getTimeline(quoteId: string) {
      const response = await client.get<ApiInternalQuoteTimeline>(`/internal-quotes/${quoteId}/timeline`)
      return response.data
    },
    async getReferenceSnapshot(quoteId: string) {
      const response = await client.get<ApiInternalQuoteReferenceSet>(`/internal-quotes/${quoteId}/reference-snapshot`)
      return response.data
    },
    async getSummary(quoteId: string) {
      const response = await client.get<ApiInternalQuoteSummary>(`/internal-quotes/${quoteId}/summary`)
      return response.data
    },
    async listAttachments(quoteId: string) {
      const response = await client.get<ApiInternalQuoteAttachment[]>(`/internal-quotes/${quoteId}/attachments`)
      return response.data
    },
    async listExports(quoteId: string) {
      const response = await client.get<ApiInternalQuoteExport[]>(`/internal-quotes/${quoteId}/exports`)
      return response.data
    },
    async saveSection(quoteId: string, sectionCode: string, revision: number, payload: Record<string, unknown>, reason = '') {
      const response = await client.put<ApiInternalQuoteSection>(`/internal-quotes/${quoteId}/sections/${sectionCode}`, {
        revision,
        payload,
        reason,
      })
      return response.data
    },
    async previewSection(
      quoteId: string,
      sectionCode: InternalQuoteSectionCode,
      revision: number,
      payload: Record<string, unknown>,
    ) {
      const response = await client.post<ApiInternalQuoteSectionPreview>(`/internal-quotes/${quoteId}/sections/${sectionCode}/preview`, {
        revision,
        payload,
      })
      return response.data
    },
    async submitSection(quoteId: string, sectionCode: string, revision: number) {
      const response = await client.post<ApiInternalQuoteSection>(`/internal-quotes/${quoteId}/sections/${sectionCode}/submit`, { revision })
      return response.data
    },
    async withdrawSection(quoteId: string, sectionCode: string, revision: number) {
      const response = await client.post<ApiInternalQuoteSection>(`/internal-quotes/${quoteId}/sections/${sectionCode}/withdraw`, { revision })
      return response.data
    },
    async reviewSection(quoteId: string, sectionCode: string, revision: number, decision: 'approve' | 'reject', reason = '') {
      const response = await client.post<ApiInternalQuoteSection>(`/internal-quotes/${quoteId}/sections/${sectionCode}/review`, {
        revision,
        decision,
        reason,
      })
      return response.data
    },
    async requestSectionNa(quoteId: string, sectionCode: string, revision: number, reason: string) {
      const response = await client.post<ApiInternalQuoteSection>(`/internal-quotes/${quoteId}/sections/${sectionCode}/request-na`, { revision, reason })
      return response.data
    },
    async reopenSection(quoteId: string, sectionCode: string, revision: number, reason: string) {
      const response = await client.post<ApiInternalQuoteSection>(`/internal-quotes/${quoteId}/sections/${sectionCode}/reopen`, { revision, reason })
      return response.data
    },
    async syncReferenceSnapshot(quoteId: string, revision: number, reason: string) {
      const response = await client.post<ApiInternalQuote>(`/internal-quotes/${quoteId}/reference-snapshot/sync`, { revision, reason })
      return response.data
    },
    async updateReferenceFx(quoteId: string, revision: number, rmbHkd: string, hkdUsd: string) {
      const response = await client.put<ApiInternalQuote>(`/internal-quotes/${quoteId}/reference-snapshot/fx`, {
        revision,
        rmb_hkd: rmbHkd,
        hkd_usd: hkdUsd,
      })
      return response.data
    },
    async previewImport(quoteId: string, importType: ApiInternalQuoteImportPreview['import_type'], file: File) {
      const form = new FormData()
      form.append('file', file)
      const response = await client.post<ApiInternalQuoteImportPreview>(
        `/internal-quotes/${quoteId}/imports/${importType}/preview`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      return response.data
    },
    async downloadImportTemplate(quoteId: string, importType: ApiInternalQuoteImportPreview['import_type']) {
      const response = await client.get<Blob>(
        `/internal-quotes/${quoteId}/imports/${importType}/template`,
        { responseType: 'blob', timeout: 60_000 },
      )
      return response.data
    },
    async confirmImport(quoteId: string, batchId: string, revision: number) {
      const response = await client.post<ApiInternalQuoteImportConfirm>(`/internal-quotes/${quoteId}/imports/${batchId}/confirm`, { revision })
      return response.data
    },
    async uploadAttachment(quoteId: string, department: string, file: File) {
      const form = new FormData()
      form.append('department', department)
      form.append('file', file)
      const response = await client.post<ApiInternalQuoteAttachment>(
        `/internal-quotes/${quoteId}/attachments`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      return response.data
    },
    async updateReferenceMaterials(
      quoteId: string,
      payload: InternalQuoteReferenceMaterialsUpdateRequest,
    ) {
      const response = await client.put<ApiInternalQuote>(
        `/internal-quotes/${quoteId}/reference-snapshot/materials`,
        payload,
      )
      return response.data
    },
    async uploadProductImage(quoteId: string, file: File) {
      const form = new FormData()
      form.append('file', file)
      const response = await client.post<ApiInternalQuoteAttachment>(
        `/internal-quotes/${quoteId}/product-image`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      return response.data
    },
    async downloadAttachment(quoteId: string, attachmentId: string) {
      const response = await client.get<Blob>(`/internal-quotes/${quoteId}/attachments/${attachmentId}/download`, { responseType: 'blob' })
      return response.data
    },
    async previewAttachment(quoteId: string, attachmentId: string) {
      const response = await client.get<Blob>(`/internal-quotes/${quoteId}/attachments/${attachmentId}/preview`, { responseType: 'blob' })
      return response.data
    },
    async previewAttachmentContent(quoteId: string, attachmentId: string) {
      const response = await client.get<ApiInternalQuoteAttachmentContentPreview>(`/internal-quotes/${quoteId}/attachments/${attachmentId}/content-preview`)
      return response.data
    },
    async deleteImportAttachment(quoteId: string, attachmentId: string, revision: number) {
      await client.delete(`/internal-quotes/${quoteId}/attachments/${attachmentId}`, {
        params: { revision },
      })
    },
    async createExport(quoteId: string) {
      const response = await client.post<ApiInternalQuoteExport>(`/internal-quotes/${quoteId}/exports`)
      return response.data
    },
    async downloadExport(quoteId: string, exportId: string) {
      const response = await client.get<Blob>(`/internal-quotes/${quoteId}/exports/${exportId}/download`, { responseType: 'blob' })
      return response.data
    },
    async downloadEngineeringWorkbook(quoteId: string) {
      const response = await client.post<Blob>(
        `/internal-quotes/${quoteId}/engineering-data/export`,
        undefined,
        { responseType: 'blob' },
      )
      return response.data
    },
    async submitFinal(quoteId: string, revision: number) {
      const response = await client.post<ApiInternalQuoteFinalRelease>(`/internal-quotes/${quoteId}/final-submit`, { revision })
      return response.data
    },
    async withdrawFinal(quoteId: string, revision: number, reason: string) {
      const response = await client.post<ApiInternalQuoteFinalRelease>(`/internal-quotes/${quoteId}/final-withdraw`, { revision, reason })
      return response.data
    },
    async reviewFinal(quoteId: string, revision: number, decision: 'approve' | 'reject', reason = '') {
      const response = await client.post<ApiInternalQuoteFinalRelease>(`/internal-quotes/${quoteId}/final-review`, { revision, decision, reason })
      return response.data
    },
    async listVersionCandidates(quoteId: string) {
      const response = await client.get<ApiInternalQuoteVersionCandidate[]>(`/internal-quotes/${quoteId}/version-candidates`)
      return response.data
    },
    async compareVersion(quoteId: string, baseQuoteId: string) {
      const response = await client.get<ApiInternalQuoteVersionComparison>(`/internal-quotes/${quoteId}/compare/${baseQuoteId}`)
      return response.data
    },
  }
}

export const internalQuoteApi = createInternalQuoteApi()
