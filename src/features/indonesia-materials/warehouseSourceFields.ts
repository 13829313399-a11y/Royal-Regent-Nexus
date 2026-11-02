import type { Field } from './forms'

const numeric = (key: string, label: string): Field => ({ key, label, type: 'number', min: '0', step: 'any' })
export const receiptSourceFields: Field[] = [
  { key: 'actual_date', label: '实收日期（年-月-日）' }, { key: 'warehouse', label: '仓库' },
  { key: 'material_name', label: '正式报关中文名称' }, { key: 'specification', label: '规格' }, { key: 'unit', label: '数量单位' },
  numeric('normal_quantity', '正常实收数量'), numeric('spare_quantity', '备品数量'),
]
export const receiptOtherFields: Field[] = [
  { key: 'receipt_no', label: '收料单号（选填）' }, { key: 'receipt_line', label: '原单行号' }, { key: 'material_code', label: '物料编码' },
  numeric('quantity', '原单实收合计（含备品，选填）'), { key: 'contract_no', label: '原单合同号' },
  { key: 'po_no', label: '原单客户 PO' }, { key: 'item_no', label: '原单货号' }, { key: 'batch', label: '历史合同批次' },
  { key: 'purchase_no', label: '采购单号' }, { key: 'purchase_line', label: '采购行号' }, { key: 'purchase_date', label: '采购日期', type: 'date' },
  numeric('purchase_quantity', '采购总量'), { key: 'supplier', label: '供应商' }, numeric('price', '采购单价'), { key: 'currency', label: '币种' },
  { key: 'package_label', label: '箱号／包装组' }, numeric('cartons', '箱数'), numeric('length_cm', '箱长（cm）'),
  numeric('width_cm', '箱宽（cm）'), numeric('height_cm', '箱高（cm）'), numeric('carton_weight_kg', '每箱纸箱重量（kg）'),
]
export const receiptSourceKeys = [...receiptSourceFields, ...receiptOtherFields].map(field => field.key)
