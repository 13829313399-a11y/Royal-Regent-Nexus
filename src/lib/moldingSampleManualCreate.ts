import type { MoldingSampleCreateRequest } from '../api/moldingSample.js'
import { createDefaultMoldingSampleOrder } from './moldingSampleBusiness.js'
import type {
  MoldingSampleOrderType,
  MoldingSampleSendTo,
  MoldingSampleStage,
  MoldingSampleWorkshop,
  MoldPresenceStatus,
} from '../types/moldingSample.js'

export type ManualMoldingSampleSendTo = '内部' | MoldingSampleSendTo

export interface ManualMoldingSampleLineDraft {
  customer_mold_id: string
  mold_name: string
  mold_dimensions: string
  mold_presence_status: '' | MoldPresenceStatus
  mold_return_time: string
  material: string
  color: string
  pms: string
  pigment_no: string
  quantity: string
  shoot_qty: string
  required_material_kg: string
  required_date: string
  notes: string
}

export interface ManualMoldingSampleOrderDraft {
  id: string
  factory_id: string
  product_no: string
  client_name: string
  product_name: string
  order_date: string
  stage: MoldingSampleStage
  order_type: MoldingSampleOrderType
  workshop: string
  send_to: string
  supervisor: string
  eng_name: string
  reason: string
  items: ManualMoldingSampleLineDraft[]
}

export interface ManualMoldingSampleBuildResult {
  payload: MoldingSampleCreateRequest | null
  errors: string[]
}

export interface ManualMoldingSampleDraftOptions {
  id?: string
  factory_id?: string
  product_no?: string
  client_name?: string
  product_name?: string
  order_date?: string
  stage?: MoldingSampleStage
  order_type?: MoldingSampleOrderType
  workshop?: string
  send_to?: string
  supervisor?: string
  eng_name?: string
  reason?: string
  items?: ManualMoldingSampleLineDraft[]
}

const manualLineKeys: Array<keyof ManualMoldingSampleLineDraft> = [
  'customer_mold_id',
  'mold_name',
  'mold_dimensions', 'mold_presence_status', 'mold_return_time',
  'material',
  'color',
  'pms',
  'pigment_no',
  'quantity',
  'shoot_qty',
  'required_material_kg',
  'required_date',
  'notes',
]

function trimText(value: string | undefined) {
  return (value ?? '').trim()
}

export function deriveManualMoldingSampleOrderId(productNo: string) {
  const normalizedProductNo = trimText(productNo)

  return normalizedProductNo ? `BP-${normalizedProductNo}` : ''
}

export function createManualMoldingSampleLineDraft(
  input: Partial<ManualMoldingSampleLineDraft> = {},
): ManualMoldingSampleLineDraft {
  return {
    customer_mold_id: input.customer_mold_id ?? '',
    mold_name: input.mold_name ?? '',
    mold_dimensions: input.mold_dimensions ?? '',
    mold_presence_status: input.mold_presence_status ?? '',
    mold_return_time: input.mold_return_time ?? '',
    material: input.material ?? '',
    color: input.color ?? '',
    pms: input.pms ?? '',
    pigment_no: input.pigment_no ?? '',
    quantity: input.quantity ?? '',
    shoot_qty: input.shoot_qty ?? '',
    required_material_kg: input.required_material_kg ?? '',
    required_date: input.required_date ?? '',
    notes: input.notes ?? '',
  }
}

export function createManualMoldingSampleOrderDraft(
  input: ManualMoldingSampleDraftOptions = {},
): ManualMoldingSampleOrderDraft {
  return {
    id: input.id ?? '',
    factory_id: input.factory_id ?? 'huakang-a',
    product_no: input.product_no ?? '',
    client_name: input.client_name ?? '',
    product_name: input.product_name ?? '',
    order_date: input.order_date ?? '',
    stage: input.stage ?? 'T0',
    order_type: input.order_type ?? '啤办',
    workshop: input.workshop ?? 'A车间',
    send_to: input.send_to ?? '内部',
    supervisor: input.supervisor ?? '',
    eng_name: input.eng_name ?? '',
    reason: input.reason ?? '',
    items: input.items ?? [createManualMoldingSampleLineDraft()],
  }
}

function isBlankManualLine(line: ManualMoldingSampleLineDraft) {
  return manualLineKeys.every((key) => trimText(line[key]) === '')
}

function normalizePms(value: string) {
  const normalized = trimText(value).replace(/^PMS\s*/i, '').trim()

  return normalized ? `PMS ${normalized}` : ''
}

export function formatManualColorPms(color: string, pms: string) {
  const trimmedColor = trimText(color)
  const normalizedPms = normalizePms(pms)

  return [trimmedColor, normalizedPms].filter(Boolean).join(' / ')
}

function parseShootQty(value: string) {
  const parsed = Number(trimText(value))

  return Number.isFinite(parsed) ? parsed : 0
}

function parseOptionalNumber(value: string) {
  const trimmed = trimText(value)
  if (!trimmed) {
    return null
  }

  const parsed = Number(trimmed)

  return Number.isFinite(parsed) ? parsed : null
}

function requireField(value: string, label: string, errors: string[]) {
  if (!trimText(value)) {
    errors.push(`请填写${label}`)
  }
}

export function buildManualMoldingSampleCreateRequest(
  draft: ManualMoldingSampleOrderDraft,
  factoryId = draft.factory_id,
): ManualMoldingSampleBuildResult {
  const errors: string[] = []
  const productNo = trimText(draft.product_no)
  const orderId = trimText(draft.id) || deriveManualMoldingSampleOrderId(productNo)
  const clientName = trimText(draft.client_name)
  const productName = trimText(draft.product_name)
  const orderDate = trimText(draft.order_date)
  const supervisor = trimText(draft.supervisor)
  const engineer = trimText(draft.eng_name)

  requireField(productNo, '产品编号', errors)
  requireField(clientName, '客户名称', errors)
  requireField(productName, '产品名称', errors)
  requireField(orderDate, '落单日期', errors)
  requireField(supervisor, '主管', errors)
  requireField(engineer, '落单人', errors)

  const candidateLines = draft.items
    .map((line, index) => ({ line, sourceIndex: index + 1 }))
    .filter(({ line }) => !isBlankManualLine(line))

  if (!candidateLines.length) {
    errors.push('至少填写一条明细')
  }

  candidateLines.forEach(({ line, sourceIndex }) => {
    requireField(line.customer_mold_id, `第 ${sourceIndex} 行模具编号`, errors)
    requireField(line.mold_name, `第 ${sourceIndex} 行模具名称`, errors)
    requireField(line.material, `第 ${sourceIndex} 行所需用料`, errors)
    requireField(line.color, `第 ${sourceIndex} 行所需颜色`, errors)
    requireField(line.quantity, `第 ${sourceIndex} 行啤/套`, errors)
    requireField(line.required_date, `第 ${sourceIndex} 行需办日期`, errors)

    if (parseShootQty(line.shoot_qty) <= 0) {
      errors.push(`请填写第 ${sourceIndex} 行啤数，且必须大于 0`)
    }
    if (trimText(line.required_material_kg) && parseOptionalNumber(line.required_material_kg) === null) {
      errors.push(`第 ${sourceIndex} 行所需用量必须为数字`)
    }
  })

  if (errors.length) {
    return { payload: null, errors }
  }

  const timestamp = `${orderDate} 09:00`
  const sendTo = draft.send_to === '内部' ? '' : draft.send_to
  const order = createDefaultMoldingSampleOrder({
    id: orderId,
    factory_id: factoryId,
    order_number: productNo,
    doc_number: '',
    product_name: productName,
    client_name: clientName,
    date: orderDate,
    stage: draft.stage,
    order_type: draft.order_type,
    workshop: draft.workshop as MoldingSampleWorkshop,
    send_to: sendTo as MoldingSampleSendTo,
    supervisor,
    eng_name: engineer,
    reason: trimText(draft.reason),
    status: '待审核',
    created_at: timestamp,
    updated_at: timestamp,
  })

  return {
    payload: {
      order,
      items: candidateLines.map(({ line }, index) => ({
        id: `${orderId}-${String(index + 1).padStart(3, '0')}`,
        order_id: orderId,
        sort_order: index + 1,
        mold_id: trimText(line.customer_mold_id),
        mold_name: trimText(line.mold_name),
        machine_type: '',
        mold_dimensions: trimText(line.mold_dimensions),
        mold_presence_status: line.mold_presence_status || 'unknown',
        production_machine: '',
        material: trimText(line.material),
        color: formatManualColorPms(line.color, line.pms),
        pigment_no: trimText(line.pigment_no),
        quantity: trimText(line.quantity),
        shoot_qty: parseShootQty(line.shoot_qty),
        gross_weight_g: null,
        required_material_kg: parseOptionalNumber(line.required_material_kg),
        mold_return_time: trimText(line.mold_return_time),
        completion_time: trimText(line.required_date),
        notes: trimText(line.notes),
        receipt_no: '',
        collected_weight_kg: null,
        actual_weight_kg: null,
        actual_amount_hkd: null,
        injection_cost: null,
        injection_cost_hkd: null,
        exchange_rate_at_save: null,
      })),
    },
    errors,
  }
}
