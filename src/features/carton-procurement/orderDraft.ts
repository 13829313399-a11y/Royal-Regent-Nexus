import type { PaperQuantityRule } from './paperQuantity'
import type { CartonImportPreviewRow } from '@/api/cartonProcurement'
import type { OrderSubmission } from './orderSubmission'
import { isSupplierOrderSource, type SupplierOrderSource } from './supplierOrderSource'

export interface OrderDraftContext {
  userId: string
  employmentEpoch: number
  factoryId: string
}

export interface OrderDraftMaterial {
  id: string
  packagingType: string
  paperQuality: string
  specification: string
  unitsPerCarton: number | ''
  quantityRule?: PaperQuantityRule | null
  requiredQuantity?: number | ''
  netWeight?: number | ''
  grossWeight?: number | ''
  unit: string
  dimensionUnit: string
  unitPrice: number
  currency: string
  priceSource: string
  note: string
}

export interface OrderDraftForm {
  customerPo: string
  quantityBasis: 'CALCULATED' | 'EXPLICIT'
  customerCode: string
  supplierId: string
  contractNo: string
  itemNo: string
  productName: string
  orderQuantity: number | ''
  orderDate: string
  customerDueDate: string
  dueDate: string
  planDateManual?: boolean
  rush?: boolean
  rushReason?: string
  note: string
  materials: OrderDraftMaterial[]
}

export interface OrderDraft {
  supplierDelivery?: SupplierOrderSource | null
  submission?: OrderSubmission
  form: OrderDraftForm
  customerSearchText?: string
  copiedOrderNo: string
  master: { id: string; revision: number; code: string; factory_id: string } | null
  history: { item_no: string; latest_order_no: string } | null
  schedule: { batchId: string; filename: string; row: CartonImportPreviewRow } | null
}

const MAX_DRAFT_BYTES = 128 * 1024
const formStrings = ['customerPo', 'customerCode', 'supplierId', 'contractNo', 'itemNo', 'productName', 'orderDate', 'customerDueDate', 'dueDate', 'note'] as const
const materialStrings = ['id', 'packagingType', 'paperQuality', 'specification', 'unit', 'dimensionUnit', 'currency', 'priceSource', 'note'] as const
const optionalNumbers = ['requiredQuantity', 'netWeight', 'grossWeight'] as const
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value)
const textValue = (value: unknown): value is string => typeof value === 'string' && value.length <= 20_000
const numberValue = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const numberInput = (value: unknown) => value === '' || numberValue(value)
function validQuantityRule(value: unknown) {
  if (value == null) return true
  return record(value) && ['PACKING', 'PER_CARTON'].includes(String(value.mode))
    && (value.carton_line_no == null || numberValue(value.carton_line_no))
    && ['per_carton_quantity', 'manual_quantity'].every(key => value[key] == null || numberValue(value[key]) || typeof value[key] === 'string' && String(value[key]).length < 60)
}

export function orderDraftKey(context: OrderDraftContext) {
  return `carton-order-draft:v1:${encodeURIComponent(context.userId)}:${context.employmentEpoch}:${encodeURIComponent(context.factoryId)}`
}

/** Ignore row IDs when deciding whether the user has changed the blank form. */
export function orderDraftFormFingerprint(form: OrderDraftForm) {
  return JSON.stringify({ ...form, materials: form.materials.map(({ id: _id, ...line }) => line) })
}

function validDraft(value: unknown, context: OrderDraftContext): value is OrderDraft {
  if (!record(value) || !record(value.form) || !textValue(value.copiedOrderNo)) return false
  if (value.customerSearchText !== undefined && !textValue(value.customerSearchText)) return false
  if (value.supplierDelivery != null && (!isSupplierOrderSource(value.supplierDelivery)
    || value.supplierDelivery.factoryId !== context.factoryId)) return false
  if (value.submission !== undefined && (!record(value.submission)
    || typeof value.submission.requestId !== 'string' || !/^[A-Za-z0-9_-]{16,96}$/.test(value.submission.requestId)
    || typeof value.submission.payloadFingerprint !== 'string' || value.submission.payloadFingerprint.length > MAX_DRAFT_BYTES)) return false
  const form = value.form
  if (form.planDateManual !== undefined && typeof form.planDateManual !== 'boolean') return false
  if (!formStrings.every(key => textValue(form[key])) || !['CALCULATED', 'EXPLICIT'].includes(String(form.quantityBasis))
    || !numberInput(form.orderQuantity) || !Array.isArray(form.materials) || form.materials.length < 1 || form.materials.length > 100) return false
  if (!form.materials.every(line => record(line) && materialStrings.every(key => textValue(line[key]))
    && numberInput(line.unitsPerCarton) && numberValue(line.unitPrice) && validQuantityRule(line.quantityRule)
    && optionalNumbers.every(key => line[key] === undefined || numberInput(line[key])))) return false
  if (value.master !== null && (!record(value.master) || !['id', 'code', 'factory_id'].every(key => textValue(value.master && (value.master as Record<string, unknown>)[key]))
    || value.master.factory_id !== context.factoryId || !numberValue(value.master.revision) || value.master.revision < 1)) return false
  if (value.history !== null && (!record(value.history) || !textValue(value.history.item_no) || !textValue(value.history.latest_order_no))) return false
  if (value.schedule !== null && (!record(value.schedule) || !textValue(value.schedule.batchId) || !textValue(value.schedule.filename)
    || !record(value.schedule.row) || !textValue(value.schedule.row.source_sheet) || !numberValue(value.schedule.row.source_row))) return false
  return true
}

export function readOrderDraft(storage: Pick<Storage, 'getItem'>, context: OrderDraftContext): OrderDraft | null {
  try {
    const raw = storage.getItem(orderDraftKey(context))
    if (!raw || raw.length > MAX_DRAFT_BYTES) return null
    const parsed: unknown = JSON.parse(raw)
    if (!record(parsed) || parsed.version !== 1 || !record(parsed.context)
      || parsed.context.userId !== context.userId || parsed.context.employmentEpoch !== context.employmentEpoch
      || parsed.context.factoryId !== context.factoryId || !validDraft(parsed.draft, context)) return null
    return parsed.draft
  } catch { return null }
}

export function writeOrderDraft(storage: Pick<Storage, 'setItem'>, context: OrderDraftContext, draft: OrderDraft) {
  const raw = JSON.stringify({ version: 1, context, draft })
  if (raw.length > MAX_DRAFT_BYTES) throw new Error('草稿内容过大，请减少备注或纸品行数后重试')
  storage.setItem(orderDraftKey(context), raw)
}

export function removeOrderDraft(storage: Pick<Storage, 'removeItem'>, context: OrderDraftContext) {
  storage.removeItem(orderDraftKey(context))
}
