import type { AIBusinessResult, AICustomerOrderCustomerCapability, AICustomerOrderExportAuditSummary } from '../types'
import { productionFactoryContextIds } from '@/data/enterpriseMock'
import { boundedInteger, boundedText, bool, hasExactKeys, localId, record, safeLinks, text } from './contracts'


export function isCustomerOrderResultCandidate(source: Record<string, unknown>) {
  const resultType = typeof source.result_type === 'string' ? source.result_type : ''
  const schemaVersion = typeof source.schema_version === 'string' ? source.schema_version : ''
  return resultType === 'customer_order'
    || resultType.startsWith('customer_order.')
    || schemaVersion === 'customer-order'
    || schemaVersion.startsWith('customer-order-')
}

function verifiedCustomerOrderFactory(source: Record<string, unknown>) {
  const factoryId = boundedText(source.factory_id, 1, 64)
  return factoryId
    && productionFactoryContextIds.includes(factoryId as (typeof productionFactoryContextIds)[number])
    ? factoryId
    : null
}

function extractCustomerOrderCapabilities(
  source: Record<string, unknown>,
): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version', 'result_type', 'source_type', 'factory_id', 'as_of',
    'authoritative_order_ledger', 'official_order_total_available',
    'supported_operations', 'customers',
  ])) return null
  if (
    source.schema_version !== 'customer-order-capabilities-v1'
    || source.result_type !== 'customer_order.capabilities'
    || source.source_type !== 'FORMAL'
    || source.authoritative_order_ledger !== false
    || source.official_order_total_available !== false
  ) return null
  const factoryId = verifiedCustomerOrderFactory(source)
  const asOf = boundedText(source.as_of, 1, 40)
  const operations = Array.isArray(source.supported_operations)
    ? source.supported_operations
    : null
  const rawCustomers = Array.isArray(source.customers) ? source.customers : null
  if (
    !factoryId
    || !asOf
    || !operations
    || operations.length !== 3
    || operations.join('|') !== 'PREVIEW|CONTROLLED_EXPORT|EXPORT_AUDIT'
    || !rawCustomers
    || rawCustomers.length > 20
  ) return null
  const customers: AICustomerOrderCustomerCapability[] = []
  const codes = new Set<string>()
  for (const rawCustomer of rawCustomers) {
    const customer = record(rawCustomer)
    if (!customer || !hasExactKeys(customer, [
      'customer_code', 'customer_name', 'batch_preview_available',
      'controlled_export_available',
    ])) return null
    const customerCode = boundedText(customer.customer_code, 1, 64)
    const customerName = boundedText(customer.customer_name, 1, 128)
    if (
      !customerCode
      || !/^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/.test(customerCode)
      || !customerName
      || customer.batch_preview_available !== true
      || customer.controlled_export_available !== true
      || codes.has(customerCode)
    ) return null
    codes.add(customerCode)
    customers.push({
      customerCode,
      customerName,
      batchPreviewAvailable: true,
      controlledExportAvailable: true,
    })
  }
  return {
    id: localId('result'),
    kind: 'customer_order_capabilities',
    title: '客户订单能力边界',
    summary: '当前支持受控预览、导出与导出审计；尚无权威订单总台账，不能提供官方订单总数。',
    sourceType: 'FORMAL',
    factoryId,
    asOf,
    links: [],
    customerOrderCapabilities: {
      authoritativeOrderLedger: false,
      officialOrderTotalAvailable: false,
      supportedOperations: operations as Array<'PREVIEW' | 'CONTROLLED_EXPORT' | 'EXPORT_AUDIT'>,
      customers,
    },
  }
}

function extractCustomerOrderExportAudits(
  source: Record<string, unknown>,
): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version', 'result_type', 'source_type', 'factory_id', 'as_of',
    'limit', 'offset', 'returned', 'truncated', 'audits',
  ])) return null
  if (
    source.schema_version !== 'customer-order-export-audit-summary-v1'
    || source.result_type !== 'customer_order.export_audit_summary_list'
    || source.source_type !== 'FORMAL'
  ) return null
  const factoryId = verifiedCustomerOrderFactory(source)
  const asOf = boundedText(source.as_of, 1, 40)
  const limit = boundedInteger(source.limit, 1, 20)
  const offset = boundedInteger(source.offset, 0, 10_000)
  const returned = boundedInteger(source.returned, 0, 20)
  const rawAudits = Array.isArray(source.audits) ? source.audits : null
  if (
    !factoryId
    || !asOf
    || limit === null
    || offset === null
    || returned === null
    || !rawAudits
    || rawAudits.length > 20
    || rawAudits.length !== returned
    || typeof source.truncated !== 'boolean'
  ) return null
  const audits: AICustomerOrderExportAuditSummary[] = []
  for (const rawAudit of rawAudits) {
    const audit = record(rawAudit)
    if (!audit || !hasExactKeys(audit, [
      'audit_id', 'customer_code', 'received_date', 'preview_schema_version',
      'output_file_name', 'output_template', 'confirmed_issue_count',
      'manual_override_count', 'created_at',
    ])) return null
    const auditId = boundedText(audit.audit_id, 1, 96)
    const customerCode = boundedText(audit.customer_code, 1, 64)
    const receivedDate = boundedText(audit.received_date, 0, 32)
    const previewSchemaVersion = boundedText(audit.preview_schema_version, 0, 96)
    const outputFileName = boundedText(audit.output_file_name, 0, 255)
    const outputTemplate = boundedText(audit.output_template, 0, 128)
    const confirmedIssueCount = boundedInteger(audit.confirmed_issue_count, 0, Number.MAX_SAFE_INTEGER)
    const manualOverrideCount = boundedInteger(audit.manual_override_count, 0, Number.MAX_SAFE_INTEGER)
    const createdAt = boundedText(audit.created_at, 0, 32)
    if (
      !auditId
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(auditId)
      || !customerCode
      || !/^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/.test(customerCode)
      || receivedDate === null
      || previewSchemaVersion === null
      || outputFileName === null
      || outputTemplate === null
      || confirmedIssueCount === null
      || manualOverrideCount === null
      || createdAt === null
    ) return null
    audits.push({
      auditId, customerCode, receivedDate, previewSchemaVersion, outputFileName,
      outputTemplate, confirmedIssueCount, manualOverrideCount, createdAt,
    })
  }
  return {
    id: localId('result'),
    kind: 'customer_order_export_audit_list',
    title: '客户订单导出审计摘要',
    summary: `本次返回 ${returned} 条导出审计；该数量不是订单总数。`,
    sourceType: 'FORMAL',
    factoryId,
    asOf,
    truncated: source.truncated,
    links: [],
    customerOrderExportAudits: { returned, limit, offset, audits },
  }
}

export function extractCustomerOrderResult(source: Record<string, unknown>) {
  if (source.result_type === 'customer_order.capabilities') {
    return extractCustomerOrderCapabilities(source)
  }
  if (source.result_type === 'customer_order.export_audit_summary_list') {
    return extractCustomerOrderExportAudits(source)
  }
  return null
}
