import type { Data } from '@/api/indonesiaMaterials'
export interface Field {
  key: string; label: string; type?: 'text' | 'number' | 'date' | 'textarea' | 'select'; required?: boolean
  options?: { value: string; label: string }[]; min?: string; step?: string; nullable?: boolean; readonly?: boolean
}
const text = (key: string, label: string, required = false): Field => ({ key, label, required })
const number = (key: string, label: string, required = false, nullable = false): Field => ({ key, label, type: 'number', min: '0', step: 'any', required, nullable })
const date = (key: string, label: string, required = true): Field => ({ key, label, type: 'date', required, nullable: !required })
export const recipient: Field = { key: 'recipient', label: '印尼接收方', type: 'select', required: true, options: [{ value: 'RRI', label: 'RRI' }, { value: 'RRM', label: 'RRM' }] }
export const customerDefaults: Data = { name: '', status: 'active', notes: '' }
export const customerFields: Field[] = [text('name', '固定客人名称', true), { key: 'status', label: '使用状态', type: 'select', options: [{ value: 'active', label: '启用' }, { value: 'inactive', label: '停用' }] }, { key: 'notes', label: '备注', type: 'textarea' }]
const billing: Field = { key: 'billing_basis', label: '计费方式', type: 'select', required: true, options: [{ value: 'quantity', label: '按数量' }, { value: 'weight', label: '按重量' }] }
export const materialFields: Field[] = [
  text('code', '物料编码', true), text('name', '物料名称', true), text('english_name', '英文名称'), text('specification', '规格'), text('category', '类别'),
  text('unit', '数量单位', true), text('customs_unit', '报关单位', true), number('net_weight_kg', '单个净重（kg）', false, true),
  billing, number('billing_weight_kg', '单件计费重量（kg）', false, true), text('billing_unit', '计费单位', true), number('billing_factor', '计费换算系数', true), number('price', '单价', true), text('currency', '币种', true),
  { ...number('procurement_days', '采购备料自然日', false, true), step: '1' }, text('supplier', '供应商'), text('usage', '用途'), text('department', '使用部门'), text('export_company', '出口公司'),
]
export const materialDefaults: Data = { code: '', name: '', english_name: '', specification: '', category: '', unit: '', customs_unit: 'KGM', net_weight_kg: null, billing_weight_kg: null, billing_basis: 'quantity', billing_unit: 'PCS', billing_factor: '1', price: '0', currency: 'USD', procurement_days: null, supplier: '', usage: '', department: '', export_company: '', image_data: '' }
export const productFields: Field[] = [text('code', '成品货号', true), text('customer', '客户', true), text('name', '成品名称'), text('unit', '成品单位', true), number('daily_capacity', '日产能', false, true), { ...number('transport_days', '运输自然日', true), step: '1' }]
export const productDefaults: Data = { code: '', customer: '', name: '', unit: 'PCS', daily_capacity: null, transport_days: 25, materials: [] }
export const orderFields: Field[] = [text('customer', '客户', true), recipient, text('contract_no', '客户合同号', true), text('po_no', '客户 PO'), text('item_no', '成品货号', true), text('batch', '交付批次', true), number('quantity', '本批成品数量', true), text('unit', '成品单位', true), date('delivery_date', '印尼成品走货期'), text('reason', '变更原因（修改时填写）')]
export const orderDefaults: Data = { customer: '', recipient: 'RRI', contract_no: '', po_no: '', item_no: '', batch: '', quantity: '', unit: 'PCS', delivery_date: '', reason: '' }
export const supplyFields: Field[] = [text('purchase_no', '采购单号', true), text('purchase_line', '采购行号', true), date('purchase_date', '采购日期'), text('supplier', '供应商', true), number('purchase_quantity', '采购总量', true), number('normal_quantity', '正常量', true), number('spare_quantity', '免费备品量', true), text('batch', '回料批次', true), number('price', '采购单价', true), text('currency', '币种', true), billing, number('billing_factor', '计费换算系数', true), date('promised_date', '供应商回复回料期', false)]
export const supplyDefaults: Data = { material_id: '', purchase_no: '', purchase_line: '', purchase_date: '', supplier: '', purchase_quantity: '', normal_quantity: '', spare_quantity: '0', batch: '', price: '0', currency: 'USD', billing_basis: 'quantity', billing_factor: '1', promised_date: null }
export const packageFields: Field[] = [text('label', '包装组名称／箱号', true), { ...number('cartons', '箱数', true), min: '1', step: '1' }, number('length_cm', '长（cm）', true), number('width_cm', '宽（cm）', true), number('height_cm', '高（cm）', true), number('carton_weight_kg', '每箱纸箱重量（kg）', true), text('pallet', '卡板标记（不计重／体积）')]
export function clone<T>(value: T): T { return JSON.parse(JSON.stringify(value)) }
// Vue's v-model on number inputs casts to binary floating point. Keep decimal text for the ledger API.
export function setNumberText(model: Data, key: string, event: Event) {
  model[key] = (event.target as HTMLInputElement).value
}
/** Preserve every input field, including hidden images, but never submit server snapshots/state. */
export function inputData(defaults: Data, saved?: Data): Data {
  return Object.fromEntries(Object.entries(defaults).map(([key, value]) => [key, clone(saved?.[key] ?? value)]))
}
export const statuses: Record<string, string> = { missing_master: '待补基础资料', missing_parameters: '待补计划参数', shortage: '尚未齐料', complete: '河源已齐料', ready: '计划参数齐全', draft: '草稿', confirmed: '已确认', partial: '部分已导入，可继续补选', pending: '待船务确认', received: '已确认入库', late_received: '已回料，实际晚于要求', expected: '预计供应', imported: '已导入', preview: '待核对', late: '回复延期', missing: '待回复', awaiting_reply: '待供应商回复或补足绑定', on_time: '回复未超要求日' }
export const showStatus = (value: unknown) => statuses[String(value)] ?? String(value ?? '待处理')
