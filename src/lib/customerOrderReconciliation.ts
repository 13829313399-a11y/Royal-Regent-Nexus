import type { CustomerOrderLedgerLine } from '@/api/customerOrderLedger'
import type { CustomerOrderImportPreview, CustomerOrderManualOverride } from '@/types/customerOrder'

export interface OrderReconciliationSelection {
  enabled: boolean
  lineId: string
  expectedRevision: number
  reason: string
}

// This only enables the save request. The ledger service checks its own target,
// permissions and revision; ordinary schedule export never uses this exception.
export function quantityReconciliationRowId(
  preview: CustomerOrderImportPreview | null,
  sourceKind: string,
  selection: OrderReconciliationSelection,
  target: CustomerOrderLedgerLine | null | undefined,
  overrides: CustomerOrderManualOverride[],
): string | null {
  const details = preview?.rows.filter(row => row.row_role !== 'parent') ?? []
  const row = details[0]
  if (!preview || !row || details.length !== 1 || sourceKind !== 'formal' || !selection.enabled
    || !row.issues.some(issue => issue.severity === 'blocked' && issue.code === 'existing_quantity_conflict')
    || !target || target.id !== selection.lineId || target.status !== 'active'
    || target.revision !== selection.expectedRevision || selection.expectedRevision < 1
    || selection.reason.trim().length < 4 || selection.reason.trim().length > 500
    || target.factory_id !== preview.factory_id || target.customer_code !== preview.customer_code) return null
  const effective = (field: string, original: string) => overrides.find(value => value.row_id === row.id && value.field === field)?.value ?? original
  const key = (value: string) => value.trim().toLocaleLowerCase()
  const reference = effective('reference_no', row.reference_no || '')
    || effective('contract_no', row.contract_no || '') || effective('po_no', row.po_no || '')
  const product = effective('product_no', row.product_no)
  const quantity = Number(effective('quantity', row.quantity).replaceAll(',', ''))
  if (!key(reference) || !key(product) || key(reference) !== key(target.reference_no)
    || key(product) !== key(target.product_no) || !Number.isFinite(quantity) || quantity <= 0) return null
  return row.id
}
