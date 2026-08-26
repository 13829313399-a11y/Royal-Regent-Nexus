import { defineStore } from 'pinia'
import {
  internalQuoteApi,
  type ApiInternalQuote,
  type ApiInternalQuoteAttachment,
  type ApiInternalQuoteAudit,
  type ApiInternalQuoteBatchProduct,
  type ApiInternalQuoteCustomer,
  type ApiInternalQuoteDashboard,
  type ApiInternalQuoteExport,
  type ApiInternalQuoteImportPreview,
  type ApiInternalQuotePricingBaseline,
  type ApiInternalQuoteReferenceSet,
  type ApiInternalQuoteSection,
  type ApiInternalQuoteSectionPreview,
  type ApiInternalQuoteSummary,
  type ApiInternalQuoteTimeline,
  type ApiInternalQuoteVersionCandidate,
  type ApiInternalQuoteVersionComparison,
  type InternalQuoteDashboardPeriod,
  type InternalQuoteHeaderUpdateRequest,
  type InternalQuotePricingBaselineUpdateRequest,
} from '@/api/internalQuote'
import { internalQuoteSectionDefinitions } from '@/data/internalQuoteDeskConfig'
import { getApiErrorMessage } from '@/lib/http'
import { defaultSalesMiscRatio, normalizeInternalQuotePayload, salesMiscRatioForSettlementDivisor, salesSettlementDivisorForMiscRatio } from '@/lib/internalQuoteSectionPayload'
import { useAppStore } from '@/stores/app'
import type {
  InternalQuote,
  InternalQuoteActivity,
  InternalQuoteBusinessOwner,
  InternalQuoteBatchProduct,
  InternalQuoteCostLine,
  InternalQuoteCreatePayload,
  InternalQuoteExportRecord,
  InternalQuoteRr2CostSummary,
  InternalQuoteSection,
  InternalQuoteSectionCode,
  InternalQuoteSectionStatus,
  InternalQuoteStatus,
  InternalQuoteViewRecord,
} from '@/types/internalQuoteDesk'

const actionTitles: Record<string, string> = {
  create: '创建内部报价', clone: '复制内部报价', edit_header: '修改报价单头', save: '保存分段草稿',
  submit: '提交分段审核', withdraw: '提交人返回修改', approve: '分段审核通过', reject: '分段审核退回', request_na: '申请分段不适用',
  approve_na: '批准分段不适用', reopen: '合法重开分段', import_preview: '预览导入文件',
  import_confirm: '确认导入文件', upload_attachment: '上传分段附件', download_attachment: '下载分段附件',
  delete_import_attachment: '删除导入附件并清除关联数据',
  reference_sync: '同步参考快照', reference_fx_update: '调整报价汇率', reference_recalculated: '按新参考重算',
  final_submit: '提交最终放行', final_approve: '最终放行通过',
  final_reject: '最终放行退回', export: '生成受控导出', download_export: '下载受控导出', archive: '归档报价',
  dependency_invalidated: '下游依赖失效', final_release_invalidated: '最终放行失效',
  participation_added: '添加参与部门',
  whole_review_lock_section: '整单提交锁定部门内容', whole_review_submit: '提交整单审核',
  whole_review_approve_section: '整单审核通过部门内容', whole_review_reject_section: '整单审核退回部门内容',
  whole_review_approve: '整单审核通过', whole_review_reject: '整单审核退回',
  batch_copy_baseline: '复制基准款整份报价', batch_copy_section: '复制基准款部门内容',
  upload_product_image: '更新产品主图',
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

const internalQuoteSectionOrder = new Map(
  internalQuoteSectionDefinitions.map((definition, index) => [definition.code, index]),
)

export interface InternalQuoteWholeProductDraft {
  sectionCode: InternalQuoteSectionCode
  revision: number
  payload: Record<string, unknown>
  baselinePayload: Record<string, unknown>
}

function stablePayloadValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stablePayloadValue)
  if (!value || typeof value !== 'object') return value
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, nested]) => [key, stablePayloadValue(nested)]),
  )
}

function payloadFingerprint(value: Record<string, unknown>) {
  return JSON.stringify(stablePayloadValue(value))
}

function sectionPayloadFingerprint(sectionCode: InternalQuoteSectionCode, value: Record<string, unknown>) {
  return payloadFingerprint(normalizeInternalQuotePayload(sectionCode, value))
}

function orderedApiSections(sections: ApiInternalQuoteSection[]) {
  return [...sections].sort((left, right) => (
    (internalQuoteSectionOrder.get(left.department as InternalQuoteSectionCode) ?? Number.MAX_SAFE_INTEGER)
    - (internalQuoteSectionOrder.get(right.department as InternalQuoteSectionCode) ?? Number.MAX_SAFE_INTEGER)
  ))
}

function orderedParticipatingSections(sections: InternalQuoteSectionCode[]) {
  const selected = new Set(sections)
  return internalQuoteSectionDefinitions
    .map((definition) => definition.code)
    .filter((code) => selected.has(code))
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
    isImportSource: item.is_import_source,
    importBatchId: item.import_batch_id,
    importType: item.import_type,
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
    submittedById: section.submitted_by_id || undefined,
    reviewer: section.reviewed_by || undefined,
    reviewedAt: section.reviewed_at || undefined,
    notApplicableReason: ['na_pending', 'not_applicable'].includes(section.status) ? section.review_comment || undefined : undefined,
    warnings,
    lines: calculationLines(section),
    attachments: attachments.filter((item) => item.department === section.department).map(toAttachment),
    payload: section.payload,
    calculation: section.calculation,
    calculationStatus: section.calculation_status,
    dependencyStatus: section.dependency_status,
    filledAt: section.filled_at,
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

const rr2T1Fields = [
  ['base_price', '货价'], ['material', '料价', undefined, true],
  ['imp_mat', '进口料', undefined, false], ['dom_mat', '国内料', undefined, false], ['blow', '吹气'],
  ['slush', '搪胶'], ['sewing_hair', '车发'], ['sewing_cloth', '车衣'], ['hardware', '五金'],
  ['electronic', '电子'], ['motor', '马达'], ['suction', '吸塑'], ['glue_bag', '胶袋'],
] as const
const rr2T2Fields = [
  ['color_box', '彩盒/内咭'], ['code_before', '未减税前码数'], ['code_after', '减税后码数'],
  ['battery', '电池'], ['libao', '利宝'], ['plating', '电镀'], ['other_buy', '其他外购'],
  ['carton', '纸箱'], ['freight', '运费'], ['cabinet', '吊柜费'], ['misc', '杂项'],
] as const
const rr2T3Fields = [
  ['injection_labor', '啤工', undefined], ['painting_labor', '喷油工', undefined],
  ['paint_material', '油漆', undefined], ['assembly_labor', '装配工', undefined],
  ['no_labor_cost', '不含人工成本', undefined], ['labor_ratio', '人工比例', 'percent'],
  ['gross', '毛利', undefined], ['gross_ratio', '毛利率', 'percent'],
  ['profit', '利润', undefined], ['profit_ratio', '利润率', 'percent'],
  ['total_cost', '总成本', undefined],
] as const
const rr2T4Fields = [
  ['tax13', '含税13%类成本', null], ['labor13', '人工类13%', null], ['carton', '纸箱类', null],
  ['tax1', '含税1%', .99], ['slush3', '搪胶类3%', 3], ['sewhair13', '车发类13%', 11.5],
  ['sewcloth13', '车衣物料退税（仅华康C/D）', null], ['suction6', '吸塑类6%', 6], ['freight9', '运费类9%', 8.26],
  ['tax13b', '含税13%类', 11.5],
] as const

function rr2CostSummary(summary?: ApiInternalQuoteSummary): InternalQuoteRr2CostSummary {
  const source = summary?.rr2_cost_summary
  const shipping = source?.shipping_pricing
  const miscRatioSource = shipping?.misc_ratio
  const miscRatioValue = Number(miscRatioSource)
  const hasMiscRatio = miscRatioSource != null && miscRatioSource !== ''
    && Number.isFinite(miscRatioValue) && miscRatioValue >= 0 && miscRatioValue < 1
  const settlementSource = shipping?.settlement
  const settlementValue = Number(settlementSource)
  const hasLegacySettlement = settlementSource != null && settlementSource !== ''
    && Number.isFinite(settlementValue) && settlementValue > 0 && settlementValue <= 1
  const miscRatio = hasMiscRatio
    ? miscRatioValue
    : (hasLegacySettlement
        ? salesMiscRatioForSettlementDivisor(settlementValue)
        : defaultSalesMiscRatio)
  // The miscellaneous rate is authoritative. A stale settlement returned by
  // an older service must not override the current `1 - misc_ratio` rule.
  const settlement = hasMiscRatio
    ? salesSettlementDivisorForMiscRatio(miscRatio)
    : (hasLegacySettlement ? settlementValue : salesSettlementDivisorForMiscRatio(miscRatio))
  const fixedValues = (
    rows: Array<{ key: string; label: string; value: string; format?: string; display?: boolean }> | undefined,
    fields: readonly (readonly [string, string, string?, boolean?])[],
  ) => {
    const rowsByKey = new Map((rows ?? []).map((row) => [row.key, row]))
    return fields.map(([key, label, format, forcedDisplay]) => {
      const row = rowsByKey.get(key)
      return {
        key,
        label,
        value: numberValue(row?.value),
        format,
        display: forcedDisplay ?? row?.display ?? true,
      }
    })
  }
  const sourceT1 = source?.t1 ?? []
  const importedMaterialHkd = numberValue(sourceT1.find((row) => row.key === 'imp_mat')?.value)
  const domesticMaterialHkd = numberValue(sourceT1.find((row) => row.key === 'dom_mat')?.value)
  const materialRow = sourceT1.find((row) => row.key === 'material')
  const materialHkd = materialRow
    ? numberValue(materialRow.value)
    : importedMaterialHkd + domesticMaterialHkd
  const normalizedT1 = materialRow
    ? sourceT1
    : [
        ...sourceT1,
        {
          key: 'material',
          label: '料价',
          value: String(materialHkd),
          display: true,
        },
      ]
  const taxRowsByKey = new Map((source?.t4 ?? []).map((row) => [row.key, row]))
  return {
    currency: source?.currency || 'HKD',
    indonesiaFreightHkd: numberValue(source?.indonesia_freight_hkd),
    t1: fixedValues(normalizedT1, rr2T1Fields),
    t2: fixedValues(source?.t2, rr2T2Fields),
    t3: fixedValues(source?.t3, rr2T3Fields),
    moldingMaterialBreakdown: {
      totalHkd: numberValue(source?.molding_material_breakdown?.total_hkd, materialHkd),
      importedHkd: numberValue(source?.molding_material_breakdown?.imported_hkd, importedMaterialHkd),
      domesticHkd: numberValue(source?.molding_material_breakdown?.domestic_hkd, domesticMaterialHkd),
    },
    t4: rr2T4Fields.map(([key, label, defaultRate]) => {
      const row = taxRowsByKey.get(key)
      // An authoritative null means that this tax category does not apply to
      // the current quote.  Do not replace it with a browser-side default.
      const ratePercent = row
        ? (row.rate_percent == null ? null : numberValue(row.rate_percent))
        : defaultRate
      return {
        key,
        label,
        amountHkd: numberValue(row?.amount_hkd),
        ratePercent,
        deductionHkd: row
          ? (row.deduction_hkd == null ? null : numberValue(row.deduction_hkd))
          : (ratePercent == null ? null : 0),
      }
    }),
    rmbPurchaseCostHkd: numberValue(source?.totals.rmb_purchase_cost_hkd),
    totalDeductionHkd: numberValue(source?.totals.total_deduction_hkd),
    afterDeductionCostHkd: numberValue(source?.totals.after_deduction_cost_hkd),
    shippingPricing: {
      enabled: shipping?.enabled ?? false,
      freightEnabled: shipping?.freight_enabled ?? shipping?.enabled ?? false,
      liftingEnabled: shipping?.lifting_enabled ?? shipping?.enabled ?? false,
      freightSharePercent: numberValue(shipping?.freight_share_percent),
      liftSharePercent: numberValue(shipping?.lift_share_percent),
      markup: numberValue(shipping?.markup),
      activeMarkupMoq: numberValue(shipping?.active_markup_moq),
      markupTiers: (shipping?.markup_tiers ?? []).map((tier) => ({
        moq: numberValue(tier.moq),
        markup: numberValue(tier.markup),
        isActive: Boolean(tier.is_active),
        includeInOutput: tier.include_in_output !== false,
      })),
      miscRatio,
      settlement,
      factoryPriceHkd: numberValue(shipping?.factory_price_hkd),
      additionalTaxHkd: numberValue(shipping?.additional_tax_hkd),
      shippingFloorHkd: numberValue(shipping?.shipping_floor_hkd),
      hkdUsd: numberValue(shipping?.hkd_usd, 7.8),
      moldAmortizationUsd: numberValue(shipping?.mold_amortization_usd),
      pricingMode: shipping?.pricing_mode === 'component' ? 'component' : 'standard',
      pricingGroups: (shipping?.pricing_groups ?? []).map((item) => ({
        id: String(item.id ?? ''),
        name: String(item.name ?? '分项'),
        costHkd: numberValue(item.cost_hkd),
        pricingBaseHkd: numberValue(item.pricing_base_hkd),
        markup: numberValue(item.markup),
        settlement: numberValue(item.settlement),
        quotedHkd: numberValue(item.quoted_hkd),
        inheritsMainMarkup: String(item.inherits_main_markup) === 'true',
      })),
      rows: (shipping?.rows ?? []).map((item) => ({
        name: String(item.name ?? '出货场景'),
        totalCartons: numberValue(item.total_cartons),
        shippingFloorHkd: numberValue(item.shipping_floor_hkd),
        freightHkd: numberValue(item.freight_hkd),
        liftHkd: numberValue(item.lift_hkd),
        withFreightHkd: numberValue(item.with_freight_hkd),
        afterMarkupHkd: numberValue(item.after_markup_hkd),
        afterSettlementHkd: numberValue(item.after_settlement_hkd),
        totalHkd: numberValue(item.total_hkd),
        totalUsd: numberValue(item.total_usd),
        moldAmortizationUsd: numberValue(item.mold_amortization_usd),
        totalWithMoldUsd: numberValue(item.total_with_mold_usd),
      })),
    },
  }
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
    quoteType: source.quote_type ?? 'single',
    batchId: source.batch_id || source.id,
    batchQuoteNo: source.batch_quote_no || source.quote_no,
    batchPosition: source.batch_position || 1,
    batchSize: source.batch_size || 1,
    baselineQuoteId: source.baseline_quote_id || source.id,
    regionCode: source.region_code ?? '',
    customer: source.customer,
    versionLabel: source.version_label,
    factoryId: source.factory_id,
    factoryName: source.workshop_name || source.factory_id,
    workshopCode: source.workshop_code,
    workshopName: source.workshop_name,
    initiatorDepartment: source.initiator_department === 'engineering' ? 'engineering' : 'sales-business',
    createdById: source.created_by,
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
    referenceSnapshot: extras.reference?.snapshot ?? {},
    formulaVersion: source.formula_version,
    moduleVersion: source.module_version,
    headerRevision: source.header_revision,
    finalReleaseStatus: source.final_release_status,
    factoryPriceHkd: numberValue(extras.summary?.factory_price_hkd),
    summaryComponents: Object.fromEntries(Object.entries(extras.summary?.components_hkd ?? {}).map(([key, value]) => [key, numberValue(value)])),
    summaryWarnings: summaryWarnings(extras.summary),
    shippingScenarios: shippingScenarios(source),
    rr2CostSummary: rr2CostSummary(extras.summary),
    finalSubmittedBy: source.final_submitted_by_name || undefined,
    finalSubmittedById: source.final_submitted_by || undefined,
    finalApprovedBy: source.final_reviewed_by_name || undefined,
    finalApprovedAt: source.final_reviewed_at || undefined,
    finalReviewComment: source.final_review_comment || undefined,
    sections: orderedApiSections(source.sections).map((section) => toSection(section, attachments)),
    activities: (extras.timeline?.business_events ?? []).map(toActivity),
    comments: [],
    viewRecords: (extras.timeline?.view_records ?? []).map(toViewRecord),
    exports: (extras.exports ?? []).map(toExport),
  }
}

function emptyQuote(): InternalQuote {
  return {
    id: '', quoteNo: '', productName: '正在读取内部报价…', quoteType: 'single', batchId: '', batchQuoteNo: '', batchPosition: 1, batchSize: 1, baselineQuoteId: '', regionCode: '', customer: '', versionLabel: '', factoryId: '', factoryName: '',
    workshopCode: '', workshopName: '', initiatorDepartment: 'sales-business', createdById: '', initiatorName: '', businessOwnerId: '',
    businessOwner: '', targetCustomerPrice: '无', quantity: 1, targetDate: '', remark: '', createdAt: '', updatedAt: '', status: 'drafting',
    fxRmbHkd: 0.85, fxHkdUsd: 7.8, fxRmbUsd: 7.75, referenceSnapshotId: '', referenceSnapshot: {}, formulaVersion: '', moduleVersion: 'v2', headerRevision: 1,
    finalReleaseStatus: '', factoryPriceHkd: 0, summaryComponents: {}, summaryWarnings: [], shippingScenarios: [], rr2CostSummary: rr2CostSummary(),
    sections: internalQuoteSectionDefinitions.map((definition) => ({
      ...definition, status: 'draft', isRequired: true, revision: 1, totalHkd: 0, updatedAt: '', warnings: [], lines: [],
      attachments: [], payload: {}, calculation: {}, calculationStatus: 'pending', dependencyStatus: 'current', filledAt: '',
    })),
    activities: [], comments: [], viewRecords: [], exports: [],
  }
}

function toBatchProduct(source: ApiInternalQuoteBatchProduct): InternalQuoteBatchProduct {
  return {
    quoteId: source.quote_id,
    quoteNo: source.quote_no,
    productName: source.product_name,
    quantity: source.qty,
    position: source.position,
    batchSize: source.batch_size,
    quoteType: source.quote_type,
    regionCode: source.region_code,
    status: uiStatus(source.status),
    headerRevision: source.header_revision,
    isBaseline: source.is_baseline,
    differsFromBaseline: source.differs_from_baseline,
    differentHeaderFields: source.different_header_fields ?? [],
    differentSections: source.different_sections ?? [],
    differentSectionDetails: source.different_section_details ?? {},
    mainImage: source.main_image ? {
      id: source.main_image.id,
      fileName: source.main_image.file_name,
      contentType: source.main_image.content_type,
      sizeBytes: source.main_image.size_bytes,
      uploadedByName: source.main_image.uploaded_by_name,
      uploadedAt: source.main_image.uploaded_at,
    } : null,
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

function mutationError(error: unknown) {
  const wrapped = new Error(mutationMessage(error)) as Error & { status?: number }
  wrapped.status = responseStatus(error)
  return wrapped
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
    batchProductsByQuoteId: {} as Record<string, InternalQuoteBatchProduct[]>,
    quoteListTotal: 0,
    quoteListPage: 1,
    quoteListPageSize: 10,
    quoteListTotalPages: 1,
    quoteListCustomers: [] as string[],
    factoryCustomers: [] as ApiInternalQuoteCustomer[],
    businessOwners: [] as InternalQuoteBusinessOwner[],
    pricingBaseline: null as ApiInternalQuotePricingBaseline | null,
    dashboard: null as ApiInternalQuoteDashboard | null,
    liveCostPreview: null as ApiInternalQuoteSectionPreview | null,
    placeholderQuote: emptyQuote(),
    listLoading: false,
    dashboardLoading: false,
    livePreviewLoading: false,
    detailLoading: false,
    ownerLoading: false,
    customerLoading: false,
    customerSaving: false,
    baselineLoading: false,
    baselineSaving: false,
    submitting: false,
    fileBusy: false,
    errorMessage: '',
    customerErrorMessage: '',
    dashboardErrorMessage: '',
    livePreviewErrorMessage: '',
    conflictMessage: '',
    currentFactoryId: '',
    businessOwnerFactoryId: '',
    customerFactoryId: '',
    factoryContextFactoryId: '',
    factoryContextGeneration: 0,
    quoteListRequestSequence: 0,
    dashboardRequestSequence: 0,
    livePreviewRequestSequence: 0,
    livePreviewQuoteId: '',
    livePreviewSectionCode: '' as InternalQuoteSectionCode | '',
    dashboardFactoryId: '',
    dashboardPeriod: 'month' as InternalQuoteDashboardPeriod,
    businessOwnerRequestSequence: 0,
    customerLoadRequestSequence: 0,
    customerMutationRequestSequence: 0,
    pricingBaselineFactoryId: '',
    pricingBaselineWorkshopCode: '',
    baselineLoadRequestSequence: 0,
    baselineUpdateRequestSequence: 0,
    quoteMutationRequestSequence: 0,
    quoteDetailRequestSequence: 0,
    sectionEditingEnabled: true,
    versionCandidates: {} as Record<string, ApiInternalQuoteVersionCandidate[]>,
    versionComparisons: {} as Record<string, ApiInternalQuoteVersionComparison>,
    frontendNotice: 'L2 已接通九段专用表单、revision 状态流、Excel 预览确认、附件、最终放行和受控导出；正式金额仍以服务端计算快照为准。',
  }),
  getters: {
    getQuoteById: (state) => (quoteId: string) => state.quotes.find((quote) => quote.id === quoteId),
  },
  actions: {
    activateFactoryContext(factoryId: string) {
      if (this.factoryContextFactoryId === factoryId) {
        return this.factoryContextGeneration
      }

      this.factoryContextFactoryId = factoryId
      this.factoryContextGeneration += 1
      this.currentFactoryId = factoryId
      this.quotes = []
      this.batchProductsByQuoteId = {}
      this.quoteListTotal = 0
      this.quoteListPage = 1
      this.quoteListPageSize = 10
      this.quoteListTotalPages = 1
      this.quoteListCustomers = []
      this.factoryCustomers = []
      this.businessOwners = []
      this.dashboard = null
      this.dashboardFactoryId = ''
      this.pricingBaseline = null
      this.pricingBaselineFactoryId = ''
      this.pricingBaselineWorkshopCode = ''
      this.listLoading = false
      this.ownerLoading = false
      this.customerLoading = false
      this.customerSaving = false
      this.customerErrorMessage = ''
      this.customerFactoryId = ''
      this.baselineLoading = false
      this.baselineSaving = false
      this.submitting = false
      this.quoteListRequestSequence += 1
      this.businessOwnerRequestSequence += 1
      this.customerLoadRequestSequence += 1
      this.customerMutationRequestSequence += 1
      this.dashboardRequestSequence += 1
      this.baselineLoadRequestSequence += 1
      this.baselineUpdateRequestSequence += 1
      this.quoteMutationRequestSequence += 1
      this.quoteDetailRequestSequence += 1
      return this.factoryContextGeneration
    },
    ensureFactoryContext(factoryId: string) {
      if (!this.factoryContextFactoryId) {
        return this.activateFactoryContext(factoryId)
      }
      return this.factoryContextGeneration
    },
    isFactoryContextCurrent(factoryId: string, generation: number) {
      return this.factoryContextFactoryId === factoryId
        && this.factoryContextGeneration === generation
    },
    clearPricingBaseline() {
      this.baselineLoadRequestSequence += 1
      this.baselineUpdateRequestSequence += 1
      this.pricingBaseline = null
      this.pricingBaselineFactoryId = ''
      this.pricingBaselineWorkshopCode = ''
      this.baselineLoading = false
      this.baselineSaving = false
    },
    upsertQuote(quote: InternalQuote) {
      const index = this.quotes.findIndex((item) => item.id === quote.id)
      if (index >= 0) this.quotes.splice(index, 1, quote)
      else this.quotes.unshift(quote)
    },
    async loadQuotes(factoryId: string, options: { status?: string; keyword?: string; customer?: string; page?: number; pageSize?: number } = {}) {
      const factoryContextGeneration = this.activateFactoryContext(factoryId)
      const requestSequence = ++this.quoteListRequestSequence
      this.listLoading = true
      this.errorMessage = ''
      this.currentFactoryId = factoryId
      try {
        const response = Object.keys(options).length
          ? await internalQuoteApi.list(factoryId, options)
          : await internalQuoteApi.list(factoryId)
        if (
          requestSequence !== this.quoteListRequestSequence
          || !this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) return
        if (Array.isArray(response)) {
          // Compatibility with a backend process that still returns the former
          // unpaged array response. Keep the page controls functional instead of
          // reporting "1 / 1" for a list that contains more than one page.
          const legacyRows = options.customer
            ? response.filter((item) => item.customer === options.customer)
            : response
          const pageSize = Math.max(1, Math.trunc(options.pageSize ?? 10))
          const totalPages = Math.max(1, Math.ceil(legacyRows.length / pageSize))
          const page = Math.min(Math.max(1, Math.trunc(options.page ?? 1)), totalPages)
          const pageStart = (page - 1) * pageSize
          this.quotes = legacyRows.slice(pageStart, pageStart + pageSize).map((item) => toQuote(item))
          this.quoteListTotal = legacyRows.length
          this.quoteListPage = page
          this.quoteListPageSize = pageSize
          this.quoteListTotalPages = totalPages
          this.quoteListCustomers = [...new Set(response.map((item) => item.customer))].filter(Boolean).sort()
        } else {
          this.quotes = response.items.map((item) => toQuote(item))
          this.quoteListTotal = response.total
          this.quoteListPage = response.page
          this.quoteListPageSize = response.page_size
          this.quoteListTotalPages = response.total_pages
          this.quoteListCustomers = response.customers
        }
      } catch (error) {
        if (
          requestSequence !== this.quoteListRequestSequence
          || !this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) return
        this.errorMessage = getApiErrorMessage(error)
        this.quotes = []
        this.quoteListTotal = 0
        this.quoteListPage = 1
        this.quoteListTotalPages = 1
      } finally {
        if (
          requestSequence === this.quoteListRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) {
          this.listLoading = false
        }
      }
    },
    async loadDashboard(factoryId: string, period: InternalQuoteDashboardPeriod) {
      const requestSequence = ++this.dashboardRequestSequence
      if (this.dashboardFactoryId !== factoryId || this.dashboardPeriod !== period) this.dashboard = null
      this.dashboardLoading = true
      this.dashboardErrorMessage = ''
      this.dashboardFactoryId = factoryId
      this.dashboardPeriod = period
      try {
        const dashboard = await internalQuoteApi.getDashboard(factoryId, period)
        if (
          requestSequence !== this.dashboardRequestSequence
          || this.dashboardFactoryId !== factoryId
          || this.dashboardPeriod !== period
        ) return
        this.dashboard = dashboard
      } catch (error) {
        if (
          requestSequence !== this.dashboardRequestSequence
          || this.dashboardFactoryId !== factoryId
          || this.dashboardPeriod !== period
        ) return
        this.dashboard = null
        this.dashboardErrorMessage = getApiErrorMessage(error)
      } finally {
        if (
          requestSequence === this.dashboardRequestSequence
          && this.dashboardFactoryId === factoryId
          && this.dashboardPeriod === period
        ) this.dashboardLoading = false
      }
    },
    async loadBusinessOwners(factoryId: string) {
      const requestSequence = ++this.businessOwnerRequestSequence
      if (this.businessOwnerFactoryId !== factoryId) this.businessOwners = []
      this.ownerLoading = true
      this.businessOwnerFactoryId = factoryId
      try {
        const businessOwners = (await internalQuoteApi.listBusinessOwners(factoryId)).map((item) => ({ id: item.id, username: item.username, displayName: item.display_name }))
        if (requestSequence !== this.businessOwnerRequestSequence || this.businessOwnerFactoryId !== factoryId) return
        this.businessOwners = businessOwners
      } catch (error) {
        if (requestSequence !== this.businessOwnerRequestSequence || this.businessOwnerFactoryId !== factoryId) return
        this.businessOwners = []
        this.errorMessage = getApiErrorMessage(error)
      } finally {
        if (requestSequence === this.businessOwnerRequestSequence && this.businessOwnerFactoryId === factoryId) {
          this.ownerLoading = false
        }
      }
    },
    async loadCustomers(factoryId: string) {
      const factoryContextGeneration = this.ensureFactoryContext(factoryId)
      if (!this.isFactoryContextCurrent(factoryId, factoryContextGeneration)) return []
      const requestSequence = ++this.customerLoadRequestSequence
      if (this.customerFactoryId !== factoryId) this.factoryCustomers = []
      this.customerLoading = true
      this.customerErrorMessage = ''
      this.customerFactoryId = factoryId
      try {
        const customers = await internalQuoteApi.listCustomers(factoryId)
        if (
          requestSequence !== this.customerLoadRequestSequence
          || !this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) return []
        this.factoryCustomers = customers
        return customers
      } catch (error) {
        if (
          requestSequence === this.customerLoadRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) {
          this.factoryCustomers = []
          this.customerErrorMessage = getApiErrorMessage(error)
        }
        return []
      } finally {
        if (
          requestSequence === this.customerLoadRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) this.customerLoading = false
      }
    },
    async createCustomer(factoryId: string, name: string) {
      return this.executeCustomerMutation(factoryId, async () => (
        internalQuoteApi.createCustomer(factoryId, name)
      ), 'create')
    },
    async updateCustomer(factoryId: string, customerId: string, name: string, revision: number) {
      return this.executeCustomerMutation(factoryId, async () => (
        internalQuoteApi.updateCustomer(customerId, name, revision)
      ), 'update')
    },
    async deleteCustomer(factoryId: string, customerId: string, revision: number) {
      return this.executeCustomerMutation(factoryId, async () => {
        await internalQuoteApi.deleteCustomer(customerId, revision)
        return { id: customerId } as ApiInternalQuoteCustomer
      }, 'delete')
    },
    async executeCustomerMutation(
      factoryId: string,
      operation: () => Promise<ApiInternalQuoteCustomer>,
      action: 'create' | 'update' | 'delete',
    ) {
      const factoryContextGeneration = this.ensureFactoryContext(factoryId)
      if (!this.isFactoryContextCurrent(factoryId, factoryContextGeneration)) {
        throw new Error('厂区已切换，请在当前厂区重新维护客户资料。')
      }
      const requestSequence = ++this.customerMutationRequestSequence
      this.customerSaving = true
      this.customerErrorMessage = ''
      try {
        const customer = await operation()
        if (
          requestSequence !== this.customerMutationRequestSequence
          || !this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) return undefined
        if (action === 'delete') {
          this.factoryCustomers = this.factoryCustomers.filter((item) => item.id !== customer.id)
        } else {
          const index = this.factoryCustomers.findIndex((item) => item.id === customer.id)
          if (index >= 0) this.factoryCustomers.splice(index, 1, customer)
          else this.factoryCustomers.push(customer)
          this.factoryCustomers.sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))
        }
        return customer
      } catch (error) {
        const message = mutationMessage(error)
        if (
          requestSequence === this.customerMutationRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) this.customerErrorMessage = message
        throw new Error(message)
      } finally {
        if (
          requestSequence === this.customerMutationRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) this.customerSaving = false
      }
    },
    clearLiveCostPreview(quoteId = '', sectionCode: InternalQuoteSectionCode | '' = '') {
      if (quoteId && this.livePreviewQuoteId && this.livePreviewQuoteId !== quoteId) return
      if (sectionCode && this.livePreviewSectionCode && this.livePreviewSectionCode !== sectionCode) return
      this.livePreviewRequestSequence += 1
      this.liveCostPreview = null
      this.livePreviewLoading = false
      this.livePreviewErrorMessage = ''
      this.livePreviewQuoteId = ''
      this.livePreviewSectionCode = ''
    },
    async previewSectionCost(
      quoteId: string,
      sectionCode: InternalQuoteSectionCode,
      revision: number,
      payload: Record<string, unknown>,
    ) {
      const requestSequence = ++this.livePreviewRequestSequence
      const contextChanged = this.livePreviewQuoteId !== quoteId || this.livePreviewSectionCode !== sectionCode
      if (contextChanged) this.liveCostPreview = null
      this.livePreviewQuoteId = quoteId
      this.livePreviewSectionCode = sectionCode
      this.livePreviewLoading = true
      this.livePreviewErrorMessage = ''
      try {
        const preview = await internalQuoteApi.previewSection(quoteId, sectionCode, revision, payload)
        if (requestSequence !== this.livePreviewRequestSequence) return undefined
        this.liveCostPreview = preview
        return preview
      } catch (error) {
        if (requestSequence !== this.livePreviewRequestSequence) return undefined
        this.livePreviewErrorMessage = getApiErrorMessage(error)
        return undefined
      } finally {
        if (requestSequence === this.livePreviewRequestSequence) this.livePreviewLoading = false
      }
    },
    async loadPricingBaseline(factoryId: string, workshopCode = 'huaxing-workshop') {
      const factoryContextGeneration = this.ensureFactoryContext(factoryId)
      if (!this.isFactoryContextCurrent(factoryId, factoryContextGeneration)) {
        throw new Error('厂区已切换，请在当前厂区重新读取报价基数。')
      }
      const requestSequence = ++this.baselineLoadRequestSequence
      this.baselineLoading = true
      this.errorMessage = ''
      try {
        const pricingBaseline = await internalQuoteApi.getPricingBaseline(factoryId, workshopCode)
        if (
          requestSequence === this.baselineLoadRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) {
          this.pricingBaseline = pricingBaseline
          this.pricingBaselineFactoryId = factoryId
          this.pricingBaselineWorkshopCode = workshopCode
        }
        return pricingBaseline
      } catch (error) {
        if (
          requestSequence === this.baselineLoadRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) {
          this.pricingBaseline = null
          this.pricingBaselineFactoryId = ''
          this.pricingBaselineWorkshopCode = ''
          this.errorMessage = getApiErrorMessage(error)
        }
        throw error
      } finally {
        if (
          requestSequence === this.baselineLoadRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) {
          this.baselineLoading = false
        }
      }
    },
    async updatePricingBaseline(
      factoryId: string,
      workshopCode: string,
      payload: InternalQuotePricingBaselineUpdateRequest,
    ) {
      const factoryContextGeneration = this.ensureFactoryContext(factoryId)
      if (!this.isFactoryContextCurrent(factoryId, factoryContextGeneration)) {
        throw new Error('厂区已切换，不能提交旧厂区的报价基数。')
      }
      const requestSequence = ++this.baselineUpdateRequestSequence
      this.baselineSaving = true
      this.errorMessage = ''
      try {
        const pricingBaseline = await internalQuoteApi.updatePricingBaseline(factoryId, workshopCode, payload)
        if (
          requestSequence === this.baselineUpdateRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) {
          this.pricingBaseline = pricingBaseline
          this.pricingBaselineFactoryId = factoryId
          this.pricingBaselineWorkshopCode = workshopCode
        }
        return pricingBaseline
      } catch (error) {
        const message = mutationMessage(error)
        if (
          requestSequence === this.baselineUpdateRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) {
          this.errorMessage = message
        }
        throw new Error(message)
      } finally {
        if (
          requestSequence === this.baselineUpdateRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) {
          this.baselineSaving = false
        }
      }
    },
    async loadQuote(quoteId: string) {
      if (!quoteId) return undefined
      const requestSequence = ++this.quoteDetailRequestSequence
      this.detailLoading = true
      this.errorMessage = ''
      try {
        const detail = await internalQuoteApi.get(quoteId)
        if (requestSequence !== this.quoteDetailRequestSequence) return undefined
        const [timelineResult, referenceResult, summaryResult, attachmentsResult, exportsResult] = await Promise.allSettled([
          internalQuoteApi.getTimeline(quoteId),
          internalQuoteApi.getReferenceSnapshot(quoteId),
          internalQuoteApi.getSummary(quoteId),
          internalQuoteApi.listAttachments(quoteId),
          internalQuoteApi.listExports(quoteId),
        ])
        if (requestSequence !== this.quoteDetailRequestSequence) return undefined
        const criticalErrors = [referenceResult, summaryResult]
          .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
          .map((result) => getApiErrorMessage(result.reason))
        if (criticalErrors.length) {
          throw new Error(`报价权威汇总读取不完整：${criticalErrors.join('；')}`)
        }
        const existing = this.getQuoteById(quoteId)
        const timeline = timelineResult.status === 'fulfilled' ? timelineResult.value : undefined
        const reference = referenceResult.status === 'fulfilled' ? referenceResult.value : undefined
        const summary = summaryResult.status === 'fulfilled' ? summaryResult.value : undefined
        const attachments = attachmentsResult.status === 'fulfilled' ? attachmentsResult.value : undefined
        const exports = exportsResult.status === 'fulfilled' ? exportsResult.value : undefined
        const quote = toQuote(detail, { timeline, reference, summary, attachments, exports })
        const degradedErrors: string[] = []
        if (timelineResult.status === 'rejected') {
          degradedErrors.push(`时间线读取失败：${getApiErrorMessage(timelineResult.reason)}`)
          if (existing) {
            quote.activities = existing.activities
            quote.viewRecords = existing.viewRecords
          }
        }
        if (attachmentsResult.status === 'rejected') {
          degradedErrors.push(`附件读取失败：${getApiErrorMessage(attachmentsResult.reason)}`)
          if (existing) {
            const oldSections = new Map(existing.sections.map((section) => [section.code, section]))
            quote.sections.forEach((section) => { section.attachments = oldSections.get(section.code)?.attachments ?? [] })
          }
        }
        if (exportsResult.status === 'rejected') {
          degradedErrors.push(`导出历史读取失败：${getApiErrorMessage(exportsResult.reason)}`)
          if (existing) quote.exports = existing.exports
        }
        if (requestSequence !== this.quoteDetailRequestSequence) return undefined
        this.upsertQuote(quote)
        if (degradedErrors.length) this.errorMessage = degradedErrors.join('；')
        return quote
      } catch (error) {
        if (requestSequence !== this.quoteDetailRequestSequence) return undefined
        this.errorMessage = getApiErrorMessage(error)
        return undefined
      } finally {
        if (requestSequence === this.quoteDetailRequestSequence) this.detailLoading = false
      }
    },
    async loadQuoteForComparison(quoteId: string) {
      if (!quoteId) throw new Error('缺少待对比报价编号。')
      const detail = await internalQuoteApi.get(quoteId)
      return toQuote(detail)
    },
    async executeMutation(quoteId: string, operation: () => Promise<unknown>, refreshQuote = true) {
      this.clearLiveCostPreview(quoteId)
      this.submitting = true
      this.errorMessage = ''
      this.conflictMessage = ''
      try {
        const result = await operation()
        if (refreshQuote) {
          const refreshed = await this.loadQuote(quoteId)
          if (!refreshed) {
            throw new Error(`操作已在服务端成功，但页面未能读取最新报价。${this.errorMessage || '请重新读取最新 revision 后继续。'}`)
          }
        }
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
    async createQuote(payload: InternalQuoteCreatePayload, contextFactoryId?: string) {
      if (!payload.businessOwnerId || !payload.businessOwner.trim()) throw new Error('新建内部报价必须指定业务负责人。')
      const appStore = useAppStore()
      const activeFactory = appStore.activeFactory.id === 'group'
        ? appStore.activeProductionFactory
        : appStore.activeFactory
      const factoryId = contextFactoryId ?? activeFactory?.id ?? 'huaxing'
      const factoryName = factoryId === activeFactory?.id ? activeFactory.name : factoryId
      const factoryContextGeneration = this.ensureFactoryContext(factoryId)
      if (!this.isFactoryContextCurrent(factoryId, factoryContextGeneration)) {
        throw new Error('厂区已切换，请在当前厂区重新新建内部报价。')
      }
      const requestSequence = ++this.quoteMutationRequestSequence
      this.submitting = true
      try {
        const products = payload.products?.length
          ? payload.products
          : [{ productName: payload.productName, quantity: payload.quantity, regionCode: '' as const, imageFile: null, documentFiles: [] }]
        const created = await internalQuoteApi.create({
          factory_id: factoryId, workshop_code: `${factoryId}-workshop`, workshop_name: factoryName,
          quote_no: payload.quoteNo.trim(), product_name: products[0]!.productName.trim(), customer: payload.customer.trim(),
          qty: products[0]!.quantity, version_label: payload.versionLabel.trim(), initiator_department: payload.initiatorDepartment,
          business_owner_id: payload.businessOwnerId, business_owner_name: payload.businessOwner.trim(),
          target_customer_price: payload.targetCustomerPrice.trim(), target_date: payload.targetDate,
          remark: payload.remark, participating_sections: orderedParticipatingSections(payload.participatingSections),
          workflow_mode: 'whole_quote_review',
          quote_type: payload.quoteType ?? 'single',
          products: products.map((product) => ({
            product_name: product.productName.trim(),
            qty: Number(product.quantity),
            region_code: product.regionCode,
          })),
          pricing_components: payload.pricingComponents ?? [],
        })
        const quote = toQuote(created)
        let batchProducts = products.length > 1
          ? (await internalQuoteApi.listBatchProducts(created.id)).map(toBatchProduct)
          : []
        const assetErrors: string[] = []
        for (const [index, product] of products.entries()) {
          const targetQuoteId = batchProducts[index]?.quoteId ?? (index === 0 ? created.id : '')
          if (!targetQuoteId) continue
          if (product.imageFile) {
            try {
              await internalQuoteApi.uploadProductImage(targetQuoteId, product.imageFile)
            } catch (error) {
              assetErrors.push(`${product.productName}主图：${getApiErrorMessage(error)}`)
            }
          }
          for (const document of product.documentFiles ?? []) {
            try {
              await internalQuoteApi.uploadAttachment(targetQuoteId, document.department, document.file)
            } catch (error) {
              assetErrors.push(`${product.productName}资料“${document.file.name}”：${getApiErrorMessage(error)}`)
            }
          }
        }
        if (products.some((product) => product.imageFile)) {
          batchProducts = (await internalQuoteApi.listBatchProducts(created.id)).map(toBatchProduct)
        }
        for (const item of batchProducts) this.batchProductsByQuoteId[item.quoteId] = batchProducts
        if (assetErrors.length) this.errorMessage = `报价已创建，但部分产品资料上传失败：${assetErrors.join('；')}`
        if (
          quote.factoryId === factoryId
          && requestSequence === this.quoteMutationRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) {
          this.upsertQuote(quote)
        }
        return quote
      } finally {
        if (
          requestSequence === this.quoteMutationRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) {
          this.submitting = false
        }
      }
    },
    async loadBatchProducts(quoteId: string) {
      if (!quoteId) return [] as InternalQuoteBatchProduct[]
      try {
        const products = (await internalQuoteApi.listBatchProducts(quoteId)).map(toBatchProduct)
        for (const item of products) this.batchProductsByQuoteId[item.quoteId] = products
        this.batchProductsByQuoteId[quoteId] = products
        return products
      } catch (error) {
        this.errorMessage = getApiErrorMessage(error)
        return [] as InternalQuoteBatchProduct[]
      }
    },
    async copyBatchBaseline(quoteId: string, targetQuoteId: string, revision: number) {
      await this.executeMutation(
        targetQuoteId,
        () => internalQuoteApi.copyBatchBaseline(quoteId, targetQuoteId, revision),
      )
      return this.loadBatchProducts(targetQuoteId)
    },
    async uploadProductImage(quoteId: string, file: File) {
      this.fileBusy = true
      try {
        const result = await internalQuoteApi.uploadProductImage(quoteId, file)
        await this.loadBatchProducts(quoteId)
        return result
      } catch (error) {
        const message = mutationMessage(error)
        this.errorMessage = message
        throw new Error(message)
      } finally {
        this.fileBusy = false
      }
    },
    async cloneQuote(sourceQuoteId: string, payload: InternalQuoteCreatePayload, contextFactoryId?: string) {
      if (!payload.businessOwnerId || !payload.businessOwner.trim()) throw new Error('复制内部报价必须指定业务负责人。')
      const appStore = useAppStore()
      const activeFactory = appStore.activeFactory.id === 'group'
        ? appStore.activeProductionFactory
        : appStore.activeFactory
      const factoryId = contextFactoryId ?? activeFactory?.id ?? 'huaxing'
      const factoryContextGeneration = this.ensureFactoryContext(factoryId)
      if (!this.isFactoryContextCurrent(factoryId, factoryContextGeneration)) {
        throw new Error('厂区已切换，请在当前厂区重新复制内部报价。')
      }
      const requestSequence = ++this.quoteMutationRequestSequence
      this.submitting = true
      try {
        const cloned = await internalQuoteApi.clone(sourceQuoteId, {
          quote_no: payload.quoteNo.trim(), version_label: payload.versionLabel.trim(), business_owner_id: payload.businessOwnerId,
          business_owner_name: payload.businessOwner.trim(), target_customer_price: payload.targetCustomerPrice.trim(),
          target_date: payload.targetDate, remark: payload.remark,
          participating_sections: orderedParticipatingSections(payload.participatingSections),
          workflow_mode: 'whole_quote_review',
        })
        const quote = toQuote(cloned)
        if (
          quote.factoryId === factoryId
          && requestSequence === this.quoteMutationRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) {
          this.upsertQuote(quote)
        }
        return quote
      } finally {
        if (
          requestSequence === this.quoteMutationRequestSequence
          && this.isFactoryContextCurrent(factoryId, factoryContextGeneration)
        ) {
          this.submitting = false
        }
      }
    },
    async saveSection(quoteId: string, sectionCode: InternalQuoteSectionCode, revision: number, payload: Record<string, unknown>, reason = '', refreshQuote = true) {
      const result = await this.executeMutation(
        quoteId,
        () => internalQuoteApi.saveSection(quoteId, sectionCode, revision, payload, reason),
        refreshQuote,
      ) as ApiInternalQuoteSection
      if (sectionCode === 'sales') {
        const quote = this.getQuoteById(quoteId)
        const shipping = result.payload.shipping && typeof result.payload.shipping === 'object' && !Array.isArray(result.payload.shipping)
          ? result.payload.shipping as Record<string, unknown>
          : {}
        if (quote && Object.prototype.hasOwnProperty.call(shipping, 'misc_ratio')) {
          const miscRatio = Number(shipping.misc_ratio)
          if (Number.isFinite(miscRatio) && miscRatio >= 0 && miscRatio < 1) {
            quote.rr2CostSummary.shippingPricing.miscRatio = miscRatio
            const divisor = Number(shipping.divisor)
            quote.rr2CostSummary.shippingPricing.settlement = Number.isFinite(divisor) && divisor > 0
              ? divisor
              : salesSettlementDivisorForMiscRatio(miscRatio)
          }
        }
        const tierRows = Array.isArray(shipping.markup_tiers) ? shipping.markup_tiers : []
        const tiers = tierRows.flatMap((value) => {
          if (!value || typeof value !== 'object' || Array.isArray(value)) return []
          const row = value as Record<string, unknown>
          const moq = Number(row.moq)
          const markup = Number(row.markup_x)
          return Number.isFinite(moq) && moq > 0 && Number.isFinite(markup) && markup > 0
            ? [{ moq, markup, includeInOutput: row.include_in_output !== false }]
            : []
        })
        const selectedMoq = Number(shipping.selected_markup_moq)
        if (quote && tiers.length && tiers.some((tier) => tier.moq === selectedMoq)) {
          quote.rr2CostSummary.shippingPricing.activeMarkupMoq = selectedMoq
          quote.rr2CostSummary.shippingPricing.markupTiers = tiers.map((tier) => ({
            ...tier,
            isActive: tier.moq === selectedMoq,
          }))
          quote.rr2CostSummary.shippingPricing.markup = tiers.find((tier) => tier.moq === selectedMoq)!.markup
        }
      }
      return result
    },
    async saveWholeProductSections(quoteId: string, drafts: InternalQuoteWholeProductDraft[]) {
      if (!drafts.length) throw new Error('当前没有需要保存的部门修改。')
      const draftByCode = new Map(drafts.map((draft) => [draft.sectionCode, draft]))
      if (draftByCode.size !== drafts.length) throw new Error('整单保存包含重复部门，请重新读取页面后再试。')
      const orderedDrafts = orderedParticipatingSections([...draftByCode.keys()])
        .map((sectionCode) => draftByCode.get(sectionCode)!)
      const currentRevisions = new Map(orderedDrafts.map((draft) => [draft.sectionCode, draft.revision]))
      const savedSections: ApiInternalQuoteSection[] = []
      this.clearLiveCostPreview(quoteId)
      this.submitting = true
      this.errorMessage = ''
      this.conflictMessage = ''
      try {
        const latestBeforeSave = await internalQuoteApi.get(quoteId)
        const alreadyPersisted = new Set<InternalQuoteSectionCode>()
        for (const draft of orderedDrafts) {
          const latestSection = latestBeforeSave.sections.find((section) => section.department === draft.sectionCode)
          if (!latestSection) throw new Error(`${definitionFor(draft.sectionCode).label}已不在当前报价中，请重新读取页面后再试。`)
          if (latestSection.revision === draft.revision) continue
          const latestFingerprint = sectionPayloadFingerprint(draft.sectionCode, latestSection.payload)
          if (latestFingerprint === sectionPayloadFingerprint(draft.sectionCode, draft.payload)) {
            currentRevisions.set(draft.sectionCode, latestSection.revision)
            alreadyPersisted.add(draft.sectionCode)
            savedSections.push(latestSection)
            continue
          }
          if (latestFingerprint === sectionPayloadFingerprint(draft.sectionCode, draft.baselinePayload)) {
            currentRevisions.set(draft.sectionCode, latestSection.revision)
            continue
          }
          throw new Error(`${definitionFor(draft.sectionCode).label}内容已被其他用户修改；本页输入仍已保留，请重新读取后核对。`)
        }

        for (let index = 0; index < orderedDrafts.length; index += 1) {
          const draft = orderedDrafts[index]!
          if (alreadyPersisted.has(draft.sectionCode)) continue
          const result = await internalQuoteApi.saveSection(
            quoteId,
            draft.sectionCode,
            currentRevisions.get(draft.sectionCode) ?? draft.revision,
            draft.payload,
            '在连续报价页统一保存当前产品',
          )
          savedSections.push(result)
          currentRevisions.set(draft.sectionCode, result.revision)

          const pendingMoldingDraft = draft.sectionCode === 'engineering'
            ? orderedDrafts.slice(index + 1).find((item) => item.sectionCode === 'molding')
            : undefined
          if (pendingMoldingDraft) {
            const latestQuote = await internalQuoteApi.get(quoteId)
            const latestMolding = latestQuote.sections.find((section) => section.department === 'molding')
            if (!latestMolding) throw new Error('工程部保存后未能读取啤机部最新 revision，请重新读取页面后再试。')
            const latestFingerprint = sectionPayloadFingerprint('molding', latestMolding.payload)
            if (
              latestMolding.revision !== pendingMoldingDraft.revision
              && latestFingerprint !== sectionPayloadFingerprint('molding', pendingMoldingDraft.baselinePayload)
              && latestFingerprint !== sectionPayloadFingerprint('molding', pendingMoldingDraft.payload)
            ) {
              throw new Error('啤机部内容已被其他用户修改；本页输入仍已保留，请重新读取后核对。')
            }
            currentRevisions.set('molding', latestMolding.revision)
          }
        }

        const refreshed = await this.loadQuote(quoteId)
        if (!refreshed) {
          throw new Error(`全部部门已写入服务器，但页面未能读取最新报价。${this.errorMessage || '请重新读取最新 revision 后继续。'}`)
        }
        return { quote: refreshed, sections: savedSections }
      } catch (error) {
        const message = mutationMessage(error)
        if (responseStatus(error) === 409) this.conflictMessage = message
        this.errorMessage = message
        throw new Error(message)
      } finally {
        this.submitting = false
      }
    },
    submitSection(quoteId: string, sectionCode: InternalQuoteSectionCode, revision: number) {
      return this.executeMutation(quoteId, () => internalQuoteApi.submitSection(quoteId, sectionCode, revision))
    },
    withdrawSection(quoteId: string, sectionCode: InternalQuoteSectionCode, revision: number) {
      return this.executeMutation(quoteId, () => internalQuoteApi.withdrawSection(quoteId, sectionCode, revision))
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
    removeParticipation(quoteId: string, revision: number, sectionCodes: InternalQuoteSectionCode[]) {
      return this.executeMutation(quoteId, () => internalQuoteApi.removeParticipation(quoteId, revision, sectionCodes))
    },
    updateHeader(quoteId: string, payload: InternalQuoteHeaderUpdateRequest) {
      return this.executeMutation(quoteId, () => internalQuoteApi.updateHeader(quoteId, payload))
    },
    archiveQuote(quoteId: string, revision: number, reason: string) {
      return this.executeMutation(quoteId, () => internalQuoteApi.archiveQuote(quoteId, revision, reason))
    },
    syncReferenceSnapshot(quoteId: string, revision: number, reason: string) {
      return this.executeMutation(quoteId, () => internalQuoteApi.syncReferenceSnapshot(quoteId, revision, reason))
    },
    updateReferenceFx(quoteId: string, revision: number, rmbHkd: string, hkdUsd: string) {
      return this.executeMutation(quoteId, () => internalQuoteApi.updateReferenceFx(quoteId, revision, rmbHkd, hkdUsd))
    },
    updateReferenceMaterials(
      quoteId: string,
      revision: number,
      materialPrices: Array<{ material: string; grade: string; price_hkd_lb: string }>,
    ) {
      return this.executeMutation(quoteId, () => internalQuoteApi.updateReferenceMaterials(quoteId, {
        revision,
        material_prices: materialPrices,
      }))
    },
    async previewImport(quoteId: string, importType: ApiInternalQuoteImportPreview['import_type'], file: File) {
      this.fileBusy = true
      this.errorMessage = ''
      try {
        return await internalQuoteApi.previewImport(quoteId, importType, file)
      } catch (error) {
        const wrapped = mutationError(error)
        this.errorMessage = wrapped.message
        throw wrapped
      } finally {
        this.fileBusy = false
      }
    },
    async downloadImportTemplate(
      quoteId: string,
      importType: ApiInternalQuoteImportPreview['import_type'],
      fileName: string,
    ) {
      this.fileBusy = true
      this.errorMessage = ''
      try {
        triggerDownload(await internalQuoteApi.downloadImportTemplate(quoteId, importType), fileName)
      } catch (error) {
        const message = mutationMessage(error)
        this.errorMessage = message
        throw new Error(message)
      } finally {
        this.fileBusy = false
      }
    },
    confirmImport(quoteId: string, batchId: string, revision: number) {
      return this.executeMutation(quoteId, () => internalQuoteApi.confirmImport(quoteId, batchId, revision))
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
    deleteImportAttachment(quoteId: string, attachmentId: string, revision: number) {
      return this.executeMutation(
        quoteId,
        () => internalQuoteApi.deleteImportAttachment(quoteId, attachmentId, revision),
      )
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
    async downloadEngineeringWorkbook(quoteId: string, fileName: string) {
      this.fileBusy = true
      try {
        triggerDownload(
          await internalQuoteApi.downloadEngineeringWorkbook(quoteId),
          fileName,
        )
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
