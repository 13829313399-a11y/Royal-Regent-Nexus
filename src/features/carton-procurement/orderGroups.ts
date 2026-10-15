import type { CartonOrderCreateRequest, CartonOrderResponse } from '@/api/cartonProcurement'
import { http } from '@/lib/http'

export interface GroupPaper {
  id: string; packaging_type: string; paper_quality: string; specification: string; dimension_unit: string
  unit: string; required_quantity: string; usage_quantity: string; unit_price: string
}
export interface GroupStyle {
  id: string; customer_po: string; contract_no: string; item_no: string; product_name: string
  source: string; quantity: string; customer_due_date: string; lines: GroupPaper[]
}
export interface OrderGroupDraft {
  id: string; name: string; customer_code: string; order_date: string; rows: GroupStyle[]
  submitted?: CartonOrderResponse[]; pending?: GroupSubmission
}
export interface GroupSubmission {
  factory_id: string; request_id: string; name: string
  rows: { row_id: string; source: string; order: CartonOrderCreateRequest }[]
}
export const newGroupPaper = (unit: string): GroupPaper => ({ id: crypto.randomUUID(), packaging_type: '', paper_quality: '', specification: '', dimension_unit: unit, unit: '个', required_quantity: '', usage_quantity: '', unit_price: '' })
export const newGroupStyle = (unit: string): GroupStyle => ({ id: crypto.randomUUID(), customer_po: '', contract_no: '', item_no: '', product_name: '', source: '', quantity: '', customer_due_date: '', lines: [newGroupPaper(unit)] })
export function newOrderGroup(unit: string): OrderGroupDraft {
  return { id: crypto.randomUUID(), name: '合单草稿', customer_code: '', order_date: new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }), rows: [newGroupStyle(unit)] }
}
export const groupStorageKey = (user: string, epoch: number, factory: string) => `carton-order-groups:v1:${encodeURIComponent(user)}:${epoch}:${encodeURIComponent(factory)}`
export function readGroups(storage: Pick<Storage, 'getItem'>, key: string): OrderGroupDraft[] {
  const raw = storage.getItem(key)
  if (!raw) return []
  if (raw.length > 1024 * 1024) throw new Error('合单草稿超过容量，请联系维护人员核对本机草稿')
  const value: unknown = JSON.parse(raw)
  const strings = (value: unknown, keys: string[]) => !!value && typeof value === 'object' && keys.every(key => typeof (value as Record<string, unknown>)[key] === 'string')
  if (!Array.isArray(value) || value.length > 30 || !value.every(group => strings(group, ['id', 'name', 'customer_code', 'order_date'])
    && Array.isArray(group.rows) && group.rows.length > 0 && group.rows.length <= 50
    && group.rows.every((row: GroupStyle) => strings(row, ['id', 'customer_po', 'contract_no', 'item_no', 'product_name', 'source', 'quantity', 'customer_due_date'])
      && Array.isArray(row.lines) && row.lines.length > 0 && row.lines.length <= 50 && row.lines.every(line => strings(line, ['id', 'packaging_type', 'paper_quality', 'specification', 'dimension_unit', 'unit', 'required_quantity', 'usage_quantity', 'unit_price']))))) throw new Error('本机合单草稿格式无法识别，已保留原数据，请勿覆盖')
  return value
}
export function saveGroups(storage: Pick<Storage, 'setItem'>, key: string, groups: OrderGroupDraft[]) {
  const raw = JSON.stringify(groups)
  if (raw.length > 1024 * 1024) throw new Error('本机合单草稿容量已满，请处理已完成的草稿组')
  storage.setItem(key, raw)
}
export function groupSubmission(group: OrderGroupDraft, factory: string, customerName: string): GroupSubmission {
  if (!group.customer_code || !customerName || !group.name.trim() || !group.order_date) throw new Error('请明确组名、客户和下单日期')
  const positive = (value: string) => value.trim() !== '' && Number.isFinite(Number(value)) && Number(value) > 0
  for (const [index, row] of group.rows.entries()) {
    if (![row.customer_po, row.contract_no, row.item_no, row.customer_due_date].every(value => value.trim())) throw new Error(`第 ${index + 1} 款的 PO、合同号、货号或客户交期未齐，仍保留草稿`)
    if (row.quantity && !positive(row.quantity)) throw new Error(`第 ${index + 1} 款产品数量必须大于 0`)
    for (const line of row.lines) {
      if (![line.packaging_type, line.paper_quality, line.specification, line.dimension_unit, line.unit].every(value => value.trim()) || !positive(line.required_quantity)) throw new Error(`第 ${index + 1} 款请补齐各条纸品的资料、尺寸单位和明确需求数量`)
      if (line.usage_quantity && !positive(line.usage_quantity)) throw new Error(`第 ${index + 1} 款每箱装产品数必须大于 0`)
      if (line.unit_price && (!Number.isFinite(Number(line.unit_price)) || Number(line.unit_price) < 0)) throw new Error(`第 ${index + 1} 款单价无效`)
    }
  }
  return { factory_id: factory, request_id: group.id, name: group.name.trim(), rows: group.rows.map(row => ({ row_id: row.id, source: row.source, order: {
    factory_id: factory, customer_code: group.customer_code, customer_name: customerName, customer_po: row.customer_po.trim(), contract_no: row.contract_no.trim(), item_no: row.item_no.trim(), product_name: row.product_name,
    quantity_basis: 'EXPLICIT', product_order_quantity: row.quantity ? Number(row.quantity) : null, order_date: group.order_date, customer_due_date: row.customer_due_date, due_date: row.customer_due_date, status: 'CONFIRMED', note: `合单草稿组：${group.name}`,
    lines: row.lines.map(line => ({ packaging_type: line.packaging_type.trim(), paper_quality: line.paper_quality.trim(), specification: line.specification.trim(), dimension_unit: line.dimension_unit, unit: line.unit, required_quantity: Number(line.required_quantity), usage_quantity: line.usage_quantity ? Number(line.usage_quantity) : null, unit_price: Number(line.unit_price || 0), currency: 'CNY' })),
  } })) }
}
export async function convertOrderGroup(payload: GroupSubmission) {
  return (await http.post<CartonOrderResponse[]>('/carton-procurement/order-groups/convert', payload)).data
}
