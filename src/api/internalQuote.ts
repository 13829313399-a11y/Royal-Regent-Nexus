import { http } from '@/lib/http'

export interface InternalQuoteHttpClient {
  get<T = unknown>(url: string, config?: unknown): Promise<{ data: T; headers?: Record<string, unknown> }>
  post<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T; headers?: Record<string, unknown> }>
  put<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T; headers?: Record<string, unknown> }>
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
  customer: string
  qty: number
  version_label: string
  status: string
  initiator_department: string
  business_owner_id: string
  business_owner_name: string
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
  import_type: 'mold' | 'electronic' | 'painting' | 'sewing' | 'assembly'
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
  target_date: string
  remark: string
}

export interface InternalQuoteCloneRequest {
  quote_no: string
  version_label: string
  business_owner_id: string
  business_owner_name: string
  target_date: string
  remark?: string
}

export function createInternalQuoteApi(client: InternalQuoteHttpClient = http) {
  return {
    async list(factoryId: string, options: { status?: string; keyword?: string } = {}) {
      const response = await client.get<ApiInternalQuote[]>('/internal-quotes', {
        params: {
          factory_id: factoryId,
          include_sections: true,
          ...(options.status ? { status: options.status } : {}),
          ...(options.keyword ? { keyword: options.keyword } : {}),
        },
      })
      return response.data
    },
    async get(quoteId: string) {
      const response = await client.get<ApiInternalQuote>(`/internal-quotes/${quoteId}`)
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
    async listBusinessOwners(factoryId: string) {
      const response = await client.get<ApiInternalQuoteBusinessOwner[]>('/internal-quotes/business-owners', {
        params: { factory_id: factoryId },
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
    async submitSection(quoteId: string, sectionCode: string, revision: number) {
      const response = await client.post<ApiInternalQuoteSection>(`/internal-quotes/${quoteId}/sections/${sectionCode}/submit`, { revision })
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
    async confirmImport(quoteId: string, batchId: string, revision: number, mode: 'append' | 'replace') {
      const response = await client.post<ApiInternalQuoteImportConfirm>(`/internal-quotes/${quoteId}/imports/${batchId}/confirm`, { revision, mode })
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
    async downloadAttachment(quoteId: string, attachmentId: string) {
      const response = await client.get<Blob>(`/internal-quotes/${quoteId}/attachments/${attachmentId}/download`, { responseType: 'blob' })
      return response.data
    },
    async createExport(quoteId: string) {
      const response = await client.post<ApiInternalQuoteExport>(`/internal-quotes/${quoteId}/exports`)
      return response.data
    },
    async downloadExport(quoteId: string, exportId: string) {
      const response = await client.get<Blob>(`/internal-quotes/${quoteId}/exports/${exportId}/download`, { responseType: 'blob' })
      return response.data
    },
    async submitFinal(quoteId: string, revision: number) {
      const response = await client.post<ApiInternalQuoteFinalRelease>(`/internal-quotes/${quoteId}/final-submit`, { revision })
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
