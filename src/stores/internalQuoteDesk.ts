import { defineStore } from 'pinia'
import {
  internalQuoteApi,
  type ApiInternalQuote,
  type ApiInternalQuoteAttachment,
  type ApiInternalQuoteAudit,
  type ApiInternalQuoteExport,
  type ApiInternalQuoteImportPreview,
  type ApiInternalQuotePricingBaseline,
  type ApiInternalQuoteReferenceSet,
  type ApiInternalQuoteSection,
  type ApiInternalQuoteSummary,
  type ApiInternalQuoteTimeline,
  type ApiInternalQuoteVersionCandidate,
  type ApiInternalQuoteVersionComparison,
  type InternalQuotePricingBaselineUpdateRequest,
} from '@/api/internalQuote'
import { internalQuoteSectionDefinitions } from '@/data/internalQuoteDeskConfig'
import { getApiErrorMessage } from '@/lib/http'
import { useAppStore } from '@/stores/app'
import type {
  InternalQuote,
  InternalQuoteActivity,
  InternalQuoteBusinessOwner,
  InternalQuoteCostLine,
  InternalQuoteCreatePayload,
  InternalQuoteExportRecord,
  InternalQuoteSection,
  InternalQuoteSectionCode,
  InternalQuoteSectionStatus,
  InternalQuoteStatus,
  InternalQuoteViewRecord,
} from '@/types/internalQuoteDesk'

const actionTitles: Record<string, string> = {
  create: '创建内部报价', clone: '复制内部报价', edit_header: '修改报价单头', save: '保存分段草稿',
  submit: '提交分段审核', approve: '分段审核通过', reject: '分段审核退回', request_na: '申请分段不适用',
  approve_na: '批准分段不适用', reopen: '合法重开分段', import_preview: '预览导入文件',
  import_confirm: '确认导入文件', upload_attachment: '上传分段附件', download_attachment: '下载分段附件',
  reference_sync: '同步参考快照', reference_fx_update: '调整报价汇率', reference_recalculated: '按新参考重算',
  final_submit: '提交最终放行', final_approve: '最终放行通过',
  final_reject: '最终放行退回', export: '生成受控导出', download_export: '下载受控导出', archive: '归档报价',
  dependency_invalidated: '下游依赖失效', final_release_invalidated: '最终放行失效',
  participation_added: '添加参与部门',
}

function numberValue(value: unknown, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function uiStatus(status: string): InternalQuoteStatus {
  if (status === 'ready_for_final_review') return 'fully_approved'
  if (status === 'final_reviewing') return 'final_pending'
  if (status === 'fully_approved') return 'released'
  if (status === 'section_reviewing') return 'pending_review'
  if (['drafting', 'pending_review', 'rejected', 'exported', 'archived'].includes(status)) return status as InternalQuoteStatus
  return 'drafting'
}

function sectionStatus(status: string): InternalQuoteSectionStatus {
  return ['draft', 'pending_review', 'approved', 'rejected', 'na_pending', 'not_applicable'].includes(status)
    ? status as InternalQuoteSectionStatus
    : 'draft'
}

function lineAmount(row: Record<string, unknown>) {
  for (const key of ['amount_hkd', 'line_hkd', 'amount_hkd_pcs', 'per_piece_hkd', 'after_settlement_hkd']) {
    if (row[key] !== null && row[key] !== undefined) return numberValue(row[key])
  }
  return 0
}

function calculationLines(section: ApiInternalQuoteSection): InternalQuoteCostLine[] {
  const rows = Array.isArray(section.calculation.line_breakdown)
    ? section.calculation.line_breakdown.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object')
    : []
  return rows.map((row, index) => {
    const amount = lineAmount(row)
    return {
      id: `${section.id}-calculation-${index}`,
      item: String(row.item ?? row.group ?? row.name ?? row.kind ?? `计算明细 ${index + 1}`),
      specification: row.reference_only
        ? `${String(row.kind ?? '后端计算快照')}（备选参考）`
        : String(row.kind ?? '后端计算快照'),
      quantity: 1,
      unit: '项',
      unitPrice: amount,
      currency: 'HKD',
      formula: String(row.formula ?? '服务端权威计算结果'),
      amountHkd: amount,
    }
  })
}

function definitionFor(code: string) {
  return internalQuoteSectionDefinitions.find((item) => item.code === code) ?? internalQuoteSectionDefinitions[0]
}

function toAttachment(item: ApiInternalQuoteAttachment) {
  return {
    id: item.id,
    fileName: item.file_name,
    contentType: item.content_type,
    sizeBytes: item.size_bytes,
    sha256: item.sha256,
    uploadedBy: item.uploaded_by_name || item.uploaded_by,
    uploadedAt: item.uploaded_at,
  }
}

function toSection(section: ApiInternalQuoteSection, attachments: ApiInternalQuoteAttachment[]): InternalQuoteSection {
  const definition = definitionFor(section.department)
  const totals = objectValue(section.calculation.totals)
  const warningRows = Array.isArray(section.calculation.warnings) ? section.calculation.warnings : []
  const warnings = warningRows
    .map((row) => row && typeof row === 'object' && 'message' in row ? String(row.message) : '')
    .filter(Boolean)
  if (section.review_comment && section.status === 'rejected') warnings.unshift(`主管退回：${section.review_comment}`)
  if (section.dependency_status === 'stale') warnings.unshift('依赖 revision 已变化，请重新保存并核价。')
  return {
    ...definition,
    code: section.department as InternalQuoteSectionCode,
    label: section.department_name || definition.label,
    status: sectionStatus(section.status),
    isRequired: section.is_required,
    revision: section.revision,
    totalHkd: numberValue(totals.total_hkd ?? totals.shipping_floor_hkd),
    updatedAt: section.updated_at,
    submittedBy: section.submitted_by || undefined,
    reviewer: section.reviewed_by || undefined,
    reviewedAt: section.reviewed_at || undefined,
    notApplicableReason: ['na_pending', 'not_applicable'].includes(section.status) ? section.review_comment || undefined : undefined,
    warnings,
    lines: calculationLines(section),
    attachments: attachments.filter((item) => item.department === section.department).map(toAttachment),
    payload: section.payload,
    calculationStatus: section.calculation_status,
    dependencyStatus: section.dependency_status,
  }
}

function toActivity(item: ApiInternalQuoteAudit): InternalQuoteActivity {
  const revision = item.new_revision ? `revision ${item.new_revision}` : ''
  const detail = [item.reason, item.detail, revision].filter(Boolean).join('；')
  return {
    id: item.id,
    action: item.action,
    title: actionTitles[item.action] ?? item.action,
    detail: detail || '服务端已记录本次业务操作。',
    actor: item.actor_name || item.actor_id,
    department: item.department || '整单',
    createdAt: item.created_at,
  }
}

function toViewRecord(item: ApiInternalQuoteAudit): InternalQuoteViewRecord {
  return {
    id: item.id,
    viewer: item.actor_name || item.actor_id,
    department: item.department || '当前授权部门',
    device: item.detail || '服务端访问记录',
    ipAddress: 'IP 已由服务端审计留存',
    viewedAt: item.created_at,
  }
}

function toExport(item: ApiInternalQuoteExport): InternalQuoteExportRecord {
  return {
    id: item.id,
    fileName: item.file_name,
    templateName: `${item.template_version} · ${item.release_stage}`,
    exportedBy: item.exported_by_name || item.exported_by,
    exportedAt: item.exported_at,
    sha256: item.sha256,
    status: item.status === 'current' ? 'current' : 'superseded',
    releaseStage: item.release_stage,
  }
}

function snapshotFx(reference?: ApiInternalQuoteReferenceSet) {
  const values = objectValue(reference?.snapshot.fx)
  return {
    rmbHkd: numberValue(values.rmb_hkd, 0.85),
    hkdUsd: numberValue(values.hkd_usd, 7.8),
    rmbUsd: numberValue(values.rmb_usd, 7.75),
  }
}

function shippingScenarios(source: ApiInternalQuote) {
  const sales = source.sections.find((section) => section.department === 'sales')
  const scenarios = objectValue(sales?.calculation.totals).scenarios
  return (Array.isArray(scenarios) ? scenarios : []).map((item) => {
    const row = objectValue(item)
    return {
      name: String(row.name ?? '出货场景'),
      totalCartons: numberValue(row.total_cartons),
      freightHkd: numberValue(row.freight_hkd),
      liftHkd: numberValue(row.lift_hkd),
      afterSettlementHkd: numberValue(row.after_settlement_hkd),
      totalUsd: numberValue(row.total_usd),
    }
  })
}

function summaryWarnings(summary?: ApiInternalQuoteSummary) {
  return (summary?.warnings ?? []).map((item) => String(item.message ?? '')).filter(Boolean)
}

function toQuote(
  source: ApiInternalQuote,
  extras: { timeline?: ApiInternalQuoteTimeline; reference?: ApiInternalQuoteReferenceSet; attachments?: ApiInternalQuoteAttachment[]; exports?: ApiInternalQuoteExport[]; summary?: ApiInternalQuoteSummary } = {},
): InternalQuote {
  const fx = snapshotFx(extras.reference)
  const attachments = extras.attachments ?? []
  return {
    id: source.id,
    quoteNo: source.quote_no,
    productName: source.product_name,
    customer: source.customer,
    versionLabel: source.version_label,
    factoryId: source.factory_id,
    factoryName: source.workshop_name || source.factory_id,
    workshopCode: source.workshop_code,
    workshopName: source.workshop_name,
    initiatorDepartment: source.initiator_department === 'engineering' ? 'engineering' : 'sales-business',
    initiatorName: source.created_by_name || source.created_by,
    businessOwnerId: source.business_owner_id,
    businessOwner: source.business_owner_name,
    targetCustomerPrice: source.target_customer_price?.trim() || '无',
    quantity: source.qty,
    targetDate: source.target_date,
    remark: source.remark,
    createdAt: source.created_at,
    updatedAt: source.updated_at,
    status: uiStatus(source.status),
    fxRmbHkd: fx.rmbHkd,
    fxHkdUsd: fx.hkdUsd,
    fxRmbUsd: fx.rmbUsd,
    referenceSnapshotId: source.reference_snapshot_id,
    formulaVersion: source.formula_version,
    headerRevision: source.header_revision,
    finalReleaseStatus: source.final_release_status,
    factoryPriceHkd: numberValue(extras.summary?.factory_price_hkd),
    summaryComponents: Object.fromEntries(Object.entries(extras.summary?.components_hkd ?? {}).map(([key, value]) => [key, numberValue(value)])),
    summaryWarnings: summaryWarnings(extras.summary),
    shippingScenarios: shippingScenarios(source),
    finalSubmittedBy: source.final_submitted_by_name || undefined,
    finalApprovedBy: source.final_reviewed_by_name || undefined,
    finalApprovedAt: source.final_reviewed_at || undefined,
    sections: source.sections.map((section) => toSection(section, attachments)),
    activities: (extras.timeline?.business_events ?? []).map(toActivity),
    comments: [],
    viewRecords: (extras.timeline?.view_records ?? []).map(toViewRecord),
    exports: (extras.exports ?? []).map(toExport),
  }
}

function emptyQuote(): InternalQuote {
  return {
    id: '', quoteNo: '', productName: '正在读取内部报价…', customer: '', versionLabel: '', factoryId: '', factoryName: '',
    workshopCode: '', workshopName: '', initiatorDepartment: 'sales-business', initiatorName: '', businessOwnerId: '',
    businessOwner: '', targetCustomerPrice: '无', quantity: 1, targetDate: '', remark: '', createdAt: '', updatedAt: '', status: 'drafting',
    fxRmbHkd: 0.85, fxHkdUsd: 7.8, fxRmbUsd: 7.75, referenceSnapshotId: '', formulaVersion: '', headerRevision: 1,
    finalReleaseStatus: '', factoryPriceHkd: 0, summaryComponents: {}, summaryWarnings: [], shippingScenarios: [],
    sections: internalQuoteSectionDefinitions.map((definition) => ({
      ...definition, status: 'draft', isRequired: true, revision: 1, totalHkd: 0, updatedAt: '', warnings: [], lines: [],
      attachments: [], payload: {}, calculationStatus: 'pending', dependencyStatus: 'current',
    })),
    activities: [], comments: [], viewRecords: [], exports: [],
  }
}

function responseStatus(error: unknown) {
  if (!error || typeof error !== 'object' || !('response' in error)) return undefined
  const response = (error as { response?: { status?: unknown } }).response
  return typeof response?.status === 'number' ? response.status : undefined
}

function responseCurrentRevision(error: unknown) {
  if (!error || typeof error !== 'object' || !('response' in error)) return undefined
  const detail = (error as { response?: { data?: { detail?: { current_revision?: unknown } } } }).response?.data?.detail
  return typeof detail?.current_revision === 'number' ? detail.current_revision : undefined
}

function mutationMessage(error: unknown) {
  const message = getApiErrorMessage(error)
  if (responseStatus(error) !== 409) return message
  const current = responseCurrentRevision(error)
  return `${message}${current ? `（服务端当前 revision ${current}）` : ''}。当前表单内容未覆盖他人修改，请重新读取后再提交。`
}

function triggerDownload(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export const useInternalQuoteDeskStore = defineStore('internal-quote-desk', {
  state: () => ({
    quotes: [] as InternalQuote[],
    businessOwners: [] as InternalQuoteBusinessOwner[],
    pricingBaseline: null as ApiInternalQuotePricingBaseline | null,
    placeholderQuote: emptyQuote(),
    listLoading: false,
    detailLoading: false,
    ownerLoading: false,
    baselineLoading: false,
    baselineSaving: false,
    submitting: false,
    fileBusy: false,
    errorMessage: '',
    conflictMessage: '',
    currentFactoryId: '',
    sectionEditingEnabled: true,
    versionCandidates: {} as Record<string, ApiInternalQuoteVersionCandidate[]>,
    versionComparisons: {} as Record<string, ApiInternalQuoteVersionComparison>,
    frontendNotice: 'L2 已接通八段专用表单、revision 状态流、五类 Excel 预览确认、附件、最终放行和受控导出；正式金额仍以服务端计算快照为准。',
  }),
  getters: {
    getQuoteById: (state) => (quoteId: string) => state.quotes.find((quote) => quote.id === quoteId),
  },
  actions: {
    upsertQuote(quote: InternalQuote) {
      const index = this.quotes.findIndex((item) => item.id === quote.id)
      if (index >= 0) this.quotes.splice(index, 1, quote)
      else this.quotes.unshift(quote)
    },
    async loadQuotes(factoryId: string) {
      this.listLoading = true
      this.errorMessage = ''
      this.currentFactoryId = factoryId
      try {
        this.quotes = (await internalQuoteApi.list(factoryId)).map((item) => toQuote(item))
      } catch (error) {
        this.errorMessage = getApiErrorMessage(error)
        this.quotes = []
      } finally {
        this.listLoading = false
      }
    },
    async loadBusinessOwners(factoryId: string) {
      this.ownerLoading = true
      try {
        this.businessOwners = (await internalQuoteApi.listBusinessOwners(factoryId)).map((item) => ({ id: item.id, username: item.username, displayName: item.display_name }))
      } catch (error) {
        this.businessOwners = []
        this.errorMessage = getApiErrorMessage(error)
      } finally {
        this.ownerLoading = false
      }
    },
    async loadPricingBaseline(factoryId: string, workshopCode = 'huaxing-workshop') {
      this.baselineLoading = true
      this.errorMessage = ''
      try {
        this.pricingBaseline = await internalQuoteApi.getPricingBaseline(factoryId, workshopCode)
        return this.pricingBaseline
      } catch (error) {
        this.pricingBaseline = null
        this.errorMessage = getApiErrorMessage(error)
        throw error
      } finally {
        this.baselineLoading = false
      }
    },
    async updatePricingBaseline(
      factoryId: string,
      workshopCode: string,
      payload: InternalQuotePricingBaselineUpdateRequest,
    ) {
      this.baselineSaving = true
      this.errorMessage = ''
      try {
        this.pricingBaseline = await internalQuoteApi.updatePricingBaseline(factoryId, workshopCode, payload)
        return this.pricingBaseline
      } catch (error) {
        const message = mutationMessage(error)
        this.errorMessage = message
        throw new Error(message)
      } finally {
        this.baselineSaving = false
      }
    },
    async loadQuote(quoteId: string) {
      if (!quoteId) return undefined
      this.detailLoading = true
      this.errorMessage = ''
      try {
        const detail = await internalQuoteApi.get(quoteId)
        const [timeline, reference, summary, attachments, exports] = await Promise.all([
          internalQuoteApi.getTimeline(quoteId).catch(() => undefined),
          internalQuoteApi.getReferenceSnapshot(quoteId).catch(() => undefined),
          internalQuoteApi.getSummary(quoteId).catch(() => undefined),
          internalQuoteApi.listAttachments(quoteId).catch(() => []),
          internalQuoteApi.listExports(quoteId).catch(() => []),
        ])
        const quote = toQuote(detail, { timeline, reference, summary, attachments, exports })
        this.upsertQuote(quote)
        return quote
      } catch (error) {
        this.errorMessage = getApiErrorMessage(error)
        return undefined
      } finally {
        this.detailLoading = false
      }
    },
    async executeMutation(quoteId: string, operation: () => Promise<unknown>) {
      this.submitting = true
      this.errorMessage = ''
      this.conflictMessage = ''
      try {
        const result = await operation()
        await this.loadQuote(quoteId)
        return result
      } catch (error) {
        const message = mutationMessage(error)
        if (responseStatus(error) === 409) this.conflictMessage = message
        this.errorMessage = message
        throw new Error(message)
      } finally {
        this.submitting = false
      }
    },
    async createQuote(payload: InternalQuoteCreatePayload) {
      if (!payload.businessOwnerId || !payload.businessOwner.trim()) throw new Error('新建内部报价必须指定业务负责人。')
      const appStore = useAppStore()
      const factoryId = appStore.activeProductionFactory?.id ?? 'huaxing'
      const factoryName = appStore.activeProductionFactory?.name ?? '华兴'
      this.submitting = true
      try {
        const created = await internalQuoteApi.create({
          factory_id: factoryId, workshop_code: `${factoryId}-workshop`, workshop_name: factoryName,
          quote_no: payload.quoteNo.trim(), product_name: payload.productName.trim(), customer: payload.customer.trim(),
          qty: payload.quantity, version_label: payload.versionLabel.trim(), initiator_department: payload.initiatorDepartment,
          business_owner_id: payload.businessOwnerId, business_owner_name: payload.businessOwner.trim(),
          target_customer_price: payload.targetCustomerPrice.trim(), target_date: payload.targetDate,
          remark: payload.remark, participating_sections: payload.participatingSections,
        })
        const quote = toQuote(created)
        this.upsertQuote(quote)
        return quote
      } finally {
        this.submitting = false
      }
    },
    async cloneQuote(sourceQuoteId: string, payload: InternalQuoteCreatePayload) {
      if (!payload.businessOwnerId || !payload.businessOwner.trim()) throw new Error('复制内部报价必须指定业务负责人。')
      this.submitting = true
      try {
        const cloned = await internalQuoteApi.clone(sourceQuoteId, {
          quote_no: payload.quoteNo.trim(), version_label: payload.versionLabel.trim(), business_owner_id: payload.businessOwnerId,
          business_owner_name: payload.businessOwner.trim(), target_customer_price: payload.targetCustomerPrice.trim(),
          target_date: payload.targetDate, remark: payload.remark,
          participating_sections: payload.participatingSections,
        })
        const quote = toQuote(cloned)
        this.upsertQuote(quote)
        return quote
      } finally {
        this.submitting = false
      }
    },
    saveSection(quoteId: string, sectionCode: InternalQuoteSectionCode, revision: number, payload: Record<string, unknown>, reason = '') {
      return this.executeMutation(quoteId, () => internalQuoteApi.saveSection(quoteId, sectionCode, revision, payload, reason))
    },
    submitSection(quoteId: string, sectionCode: InternalQuoteSectionCode, revision: number) {
      return this.executeMutation(quoteId, () => internalQuoteApi.submitSection(quoteId, sectionCode, revision))
    },
    reviewSection(quoteId: string, sectionCode: InternalQuoteSectionCode, revision: number, decision: 'approve' | 'reject', reason = '') {
      return this.executeMutation(quoteId, () => internalQuoteApi.reviewSection(quoteId, sectionCode, revision, decision, reason))
    },
    requestSectionNa(quoteId: string, sectionCode: InternalQuoteSectionCode, revision: number, reason: string) {
      return this.executeMutation(quoteId, () => internalQuoteApi.requestSectionNa(quoteId, sectionCode, revision, reason))
    },
    reopenSection(quoteId: string, sectionCode: InternalQuoteSectionCode, revision: number, reason: string) {
      return this.executeMutation(quoteId, () => internalQuoteApi.reopenSection(quoteId, sectionCode, revision, reason))
    },
    addParticipation(quoteId: string, revision: number, sectionCodes: InternalQuoteSectionCode[]) {
      return this.executeMutation(quoteId, () => internalQuoteApi.addParticipation(quoteId, revision, sectionCodes))
    },
    syncReferenceSnapshot(quoteId: string, revision: number, reason: string) {
      return this.executeMutation(quoteId, () => internalQuoteApi.syncReferenceSnapshot(quoteId, revision, reason))
    },
    updateReferenceFx(quoteId: string, revision: number, rmbHkd: string, hkdUsd: string) {
      return this.executeMutation(quoteId, () => internalQuoteApi.updateReferenceFx(quoteId, revision, rmbHkd, hkdUsd))
    },
    async previewImport(quoteId: string, importType: ApiInternalQuoteImportPreview['import_type'], file: File) {
      this.fileBusy = true
      this.errorMessage = ''
      try {
        return await internalQuoteApi.previewImport(quoteId, importType, file)
      } catch (error) {
        const message = mutationMessage(error)
        this.errorMessage = message
        throw new Error(message)
      } finally {
        this.fileBusy = false
      }
    },
    confirmImport(quoteId: string, batchId: string, revision: number, mode: 'append' | 'replace') {
      return this.executeMutation(quoteId, () => internalQuoteApi.confirmImport(quoteId, batchId, revision, mode))
    },
    uploadAttachment(quoteId: string, sectionCode: InternalQuoteSectionCode, file: File) {
      return this.executeMutation(quoteId, () => internalQuoteApi.uploadAttachment(quoteId, sectionCode, file))
    },
    async downloadAttachment(quoteId: string, attachmentId: string, fileName: string) {
      this.fileBusy = true
      try {
        triggerDownload(await internalQuoteApi.downloadAttachment(quoteId, attachmentId), fileName)
      } finally {
        this.fileBusy = false
      }
    },
    createExport(quoteId: string) {
      return this.executeMutation(quoteId, () => internalQuoteApi.createExport(quoteId))
    },
    async downloadExport(quoteId: string, exportId: string, fileName: string) {
      this.fileBusy = true
      try {
        triggerDownload(await internalQuoteApi.downloadExport(quoteId, exportId), fileName)
      } finally {
        this.fileBusy = false
      }
    },
    submitFinal(quoteId: string, revision: number) {
      return this.executeMutation(quoteId, () => internalQuoteApi.submitFinal(quoteId, revision))
    },
    reviewFinal(quoteId: string, revision: number, decision: 'approve' | 'reject', reason = '') {
      return this.executeMutation(quoteId, () => internalQuoteApi.reviewFinal(quoteId, revision, decision, reason))
    },
    async loadVersionCandidates(quoteId: string) {
      this.versionCandidates[quoteId] = await internalQuoteApi.listVersionCandidates(quoteId)
      return this.versionCandidates[quoteId]
    },
    async compareVersion(quoteId: string, baseQuoteId: string) {
      const comparison = await internalQuoteApi.compareVersion(quoteId, baseQuoteId)
      this.versionComparisons[`${quoteId}:${baseQuoteId}`] = comparison
      return comparison
    },
    addComment(_quoteId?: string, _content?: string) {
      throw new Error('当前后端尚未提供协作评论接口；请使用业务操作原因和审核意见留痕。')
    },
  },
})
