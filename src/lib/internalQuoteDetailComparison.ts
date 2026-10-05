import type { ApiInternalQuote, ApiInternalQuoteVersionComparison } from '@/api/internalQuote'

type RecordValue = Record<string, unknown>
export interface CompareItem { name: string; fields: Record<string, string> }
export interface CompareRow { before?: CompareItem; after?: CompareItem; changed: boolean; status: string }
export interface CompareGroup { name: string; rows: CompareRow[] }

// Display only business inputs. Calculation caches, import metadata and IDs never become UI text.
const labels: Record<string, string> = {
  specification: '规格', quantity: '用量', unit: '单位', unit_price_rmb: '单价 RMB', unit_price_hkd: '单价 HKD',
  loss_rate: '损耗系数', tax_rate_percent: '税点 %', remark: '备注', material: '材料', grade: '料型', color: '颜色',
  supplier: '供应商', purpose: '用途', surface_treatment: '表面处理', markup_override: '独立倍率',
  mold_no: '模号', mold_size: '模具尺寸', mold_specification: '模具规格', mold_base_type: '模胚类型',
  mold_base_material: '模胚材料', structure: '结构', process: '工艺', cavity: '穴数', cost_rmb: '费用 RMB',
  net_weight_g: '净重 g', unit_net_weight_g: '单件净重 g', cycle_time_seconds: '周期 秒', output_count: '出模数',
  machine_code: '机台编号', machine_name: '机台', sets: '套数', target_output: '目标产量',
  loss_rate_percent: '损耗 %', estimated_weight_g: '估计重量 g', weight_g: '重量 g', daily_output_24h: '日产量',
  labor_hkd: '人工 HKD', labor_rmb: '人工 RMB', burr_hkd: '除边 HKD', profit_multiplier: '利润倍率',
  mold_price_rmb: '模具价格 RMB', daily_capacity: '日产量', production_qty: '生产量', teams: '小组数',
  total_persons: '人数', persons: '人数', labor_base_hkd: '人工基数 HKD', standard_work_hours: '标准工时',
  position: '位置', paint_cost_hkd: '油漆 HKD', labor_cost_hkd: '人工 HKD', spray_labor_hkd: '喷油人工 HKD',
  paint_hkd: '油漆 HKD', part: '部位', craft: '工艺', pieces: '片数', usage: '用量', markup: '倍率',
  fabric_moq_y: '布料起订量 码', below_moq_fee_rmb: '不足起订量附加费 RMB', exchange_rate: '汇率',
  length: '长', width: '宽', height: '高', length_in: '长 英寸', width_in: '宽 英寸', height_in: '高 英寸',
  qty_per_carton: '每箱数量', paper_price_factor: '主纸箱系数', inner_paper_price_factor: '内纸箱系数',
  flat_card_price_factor: '平卡系数', testing_fee_enabled: '计算测试费', testing_fee_total_usd: '测试费 USD',
  moq: '起订量', include_in_output: '参与输出', selected_markup_moq: '采用起订量', misc_ratio: '杂项比例',
  mold_allocation_enabled: '分摊模具费用', amortization_qty: '模费分摊数量', prototype_total_usd: '手板费 USD',
  prototype_amortization_qty: '手板费分摊数量', testing_total_usd: '测试费 USD', testing_amortization_qty: '测试费分摊数量',
  customer_mold_subsidy_usd: '客户模费补贴 USD', bonding_rmb: '邦定 RMB', smt_rmb: '贴片 RMB',
  testing_rmb: '测试 RMB', packaging_rmb: '包装 RMB', profit_rate_percent: '利润 %',
  enabled: '启用', freight_enabled: '计算运费', lifting_enabled: '计算吊柜费',
  cap_40: '40 尺柜容量', cap_20: '20 尺柜容量', cap_10t: '10 吨车容量', cap_5t: '5 吨车容量',
  hk40: '香港 40 尺柜运费', hk20: '香港 20 尺柜运费', hk10t: '香港 10 吨车运费', hk5t: '香港 5 吨车运费',
  yt40: '盐田 40 尺柜运费', yt20: '盐田 20 尺柜运费', yt10t: '盐田 10 吨车运费', yt5t: '盐田 5 吨车运费',
  capacity_cuft: '容量 立方尺', freight_cost_hkd: '运费 HKD', carton_cuft: '箱体积 立方尺',
}
const containers: Record<string, string> = {
  materials: '材料', molds: '模具', parts: '子配件', production_mold_costs: '生产模具费用',
  packaging_materials: '包装材料', cartons: '纸箱', flat_cards: '平卡',
  product_size_in: '产品尺寸（英寸）', color_box_size_in: '彩盒尺寸（英寸）', pdq_size_in: '展示盒尺寸（英寸）',
  freight_calc: '运输', shipping: '倍率与杂项', markup_tiers: '起订量与倍率',
  injection_lines: '注塑', blow_lines: '吹塑', lines: '明细', rows: '工序明细',
  components: '电子元件', children: '子元件', quick_quotes: '快速报价', quick_quote: '快速报价',
  groups: '产品组', quote_groups: '电子报价组', processes: '工序', operations: '工序',
  clamp: '夹模', pad_print: '移印', uv: '紫外线处理', spray: '喷油', edge: '修边', paint: '油漆',
  dip: '浸油', wipe: '抹油', pp_water: '处理水', customer_supplied_materials: '客供材料',
}
const categories: Record<string, string> = { hardware: '五金', auxiliary: '辅助材料 / 外购件', packaging: '包装', assembly: '组装', clothes: '衣服', hair: '头发' }
const object = (value: unknown): RecordValue => value && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : {}
function display(value: unknown): string {
  if (value == null || value === '') return '—'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') return Number.isFinite(value) ? String(Number(value.toFixed(6))) : '—'
  return String(value)
}
function itemFields(row: RecordValue) {
  const hasRmb = row.unit_price_rmb != null && row.unit_price_rmb !== ''
  const currency = String(row.unit_price_source_currency || row.source_currency || (hasRmb ? 'RMB' : 'HKD')).toUpperCase()
  return Object.fromEntries(Object.entries(row).filter(([key, value]) => labels[key] && value != null && value !== '' && typeof value !== 'object'
    && !(key === 'unit_price_hkd' && currency === 'RMB') && !(key === 'unit_price_rmb' && currency === 'HKD'))
    .map(([key, value]) => [labels[key]!, display(value)]))
}
function itemName(row: RecordValue, fallback: string): string {
  return String(row.item || row.name || row.chinese_name || row.doll_name || (row.moq != null ? `起订量 ${row.moq}` : '') || fallback)
}
function extract(payload: RecordValue, department: string): Map<string, CompareItem[]> {
  const groups = new Map<string, CompareItem[]>()
  const add = (group: string, item: CompareItem) => {
    if (Object.keys(item.fields).length || item.name !== '基本设置') groups.set(group, [...(groups.get(group) ?? []), item])
  }
  function walk(data: RecordValue, group: string, name: string) {
    add(group || '基本设置', { name, fields: itemFields(data) })
    for (const [key, value] of Object.entries(data)) {
      if (!containers[key]) continue
      const groupName = [group, containers[key]].filter(Boolean).join(' · ')
      if (Array.isArray(value)) {
        value.forEach((entry, index) => {
          const row = object(entry)
          if (!Object.keys(row).length) return
          const category = categories[String(row.category)]
          const rowGroup = department === 'engineering' && key === 'materials' ? category || '其他材料' : groupName
          const rowName = itemName(row, `${containers[key]} ${index + 1}`)
          add(rowGroup, { name: rowName, fields: itemFields(row) })
          for (const [childKey, childValue] of Object.entries(row)) {
            if (containers[childKey]) walk({ [childKey]: childValue }, `${rowGroup} · ${rowName}`, '基本设置')
          }
        })
      } else if (value && typeof value === 'object') walk(object(value), groupName, containers[key]!)
    }
  }
  walk(payload, '', '基本设置')
  return groups
}
function equal(a: CompareItem, b: CompareItem) {
  const keys = new Set([...Object.keys(a.fields), ...Object.keys(b.fields)])
  return a.name === b.name && [...keys].every(key => (a.fields[key] ?? '—') === (b.fields[key] ?? '—'))
}
export function pairComparisonItems(before: CompareItem[], after: CompareItem[]): CompareRow[] {
  const used = new Set<number>()
  // Reserve exact matches first, including duplicate names; inserting or reordering a row is not a price change.
  const matches = before.map(item => {
    const index = after.findIndex((candidate, i) => !used.has(i) && equal(item, candidate))
    if (index >= 0) used.add(index)
    return index
  })
  before.forEach((item, i) => {
    if (matches[i]! >= 0) return
    const index = after.findIndex((candidate, j) => !used.has(j) && candidate.name === item.name)
    if (index >= 0) { matches[i] = index; used.add(index) }
  })
  const result: CompareRow[] = before.map((item, i) => {
    const target = after[matches[i]!]
    const changed = !target || !equal(item, target)
    return { before: item, after: target, changed, status: !target ? '已删除' : changed ? '有修改' : '相同' }
  })
  after.forEach((item, i) => { if (!used.has(i)) result.push({ after: item, changed: true, status: '新增' }) })
  return result
}
export function buildQuoteComparison(base: ApiInternalQuote, target: ApiInternalQuote, comparison: ApiInternalQuoteVersionComparison) {
  const order = ['engineering', 'molding', 'assembly', 'painting', 'electronic', 'slush', 'sewing', 'hair', 'sales']
  return [...comparison.sections].sort((a, b) => order.indexOf(a.section_code) - order.indexOf(b.section_code)).flatMap(section => {
    const before = base.sections.find(s => s.department === section.section_code)
    const after = target.sections.find(s => s.department === section.section_code)
    if (!before?.is_required && !after?.is_required) return []
    const left = extract(before?.payload ?? {}, section.section_code), right = extract(after?.payload ?? {}, section.section_code)
    const groups = [...new Set([...left.keys(), ...right.keys()])].map(name => ({ name, rows: pairComparisonItems(left.get(name) ?? [], right.get(name) ?? []) }))
    return [{ ...section, groups, changedRows: groups.reduce((sum, group) => sum + group.rows.filter(row => row.changed).length, 0) }]
  })
}
const headerLabels: Record<string, string> = { qty: '报价数量', quantity: '报价数量', product_name: '产品名称', customer: '客户', target_customer_price: '客户目标价', target_date: '目标日期', remark: '报价备注', business_owner_name: '业务负责人', 'reference_snapshot.fx.rmb_hkd': '人民币 / 港币汇率', 'reference_snapshot.fx.hkd_usd': '港币 / 美元汇率' }
export function comparisonConditions(comparison: ApiInternalQuoteVersionComparison) {
  return comparison.header_changes.filter(change => headerLabels[change.path]).map(change => ({ label: headerLabels[change.path], before: display(change.before), after: display(change.after) }))
}
