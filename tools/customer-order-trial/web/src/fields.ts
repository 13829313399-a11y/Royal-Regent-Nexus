export const fieldLabels: Record<string, string> = {
  po_no: '客户 PO', contract_no: '合同号', reference_no: '参考号', customer_name: '客户名称', customer_country: '客户 / 国家', country: '国家',
  product_no: '完整货号', parent_product_no: '母货号', source_product_no: '原件货号', shipping_item: '出货货号', product_name_zh: '中文名称', product_name_en: '英文名称', product_version: '版本备注',
  quantity: '订单数量', units_per_carton: '装箱数', carton_count: '箱数', unit_price_hkd: '港币单价', amount_hkd: '港币金额', unit_price_usd: '美元单价', amount_usd: '美元金额',
  shipped_quantity: '已走货', remaining_quantity: '未走货', requested_ship_date: '客户要求交期', received_date: '来单日期', source_order_date: '原件订单日期',
  packaging: '包装', standard: '规格', line_q: '行要求', customer_q: '客户要求', date_code: '日期码', production_no: '生产编号', order_type: '订单类型',
  customer_release_no: '客户 Release 单号', customer_label: '客户标签', price_basis: '价格依据', price_details_text: '价格明细',
  source_po_file_name: '来源 PO 文件', input_template: '原件格式', target_template: '排期格式', item_sheet_name: 'ITEM 分类页', edu_reservation_row: '预留排期行',
  customer_po: '客户 PO', note: '备注', remark: '备注', status: '订单状态', change_reason: '变更原因', version: '版本',
  label: '标签要求', carton_mark: '箱唛', fabric_label: '布标', barcode: '条码', port: '目的港', printing_requirement: '印刷要求', contact: '联系人', merchandiser: '跟单员',
  history_cutoff_date: '历史截止日期', recheck_notice: '核对提醒', manual: '人工说明',
}
export function businessFields(data: Record<string, unknown>) {
  return Object.entries(data).flatMap(([key, value]) => fieldLabels[key] && value !== null && value !== undefined && value !== ''
    ? [{ key, label: fieldLabels[key]!, value: typeof value === 'object' ? JSON.stringify(value) : String(value) }] : [])
}
