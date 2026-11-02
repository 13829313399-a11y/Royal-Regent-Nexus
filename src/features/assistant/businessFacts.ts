import type { Message } from './types'

// Presentation only. Values, units, definitions and clocks come from the same
// authorized V3 tool result; this module never aggregates rows or queries data.
const presentations: Record<string, {module: string; primary: string[]; labels: Record<string, string>}> = {
  get_injection_overview: {module:'injection-scheduling', primary:['demand_count','held_count','wait_material_count','remaining_material_kg','warehouse_shortage_kg','actual_delivery_late_count'], labels:{
    demand_count:'需求行数', held_count:'挂起（含待料）', wait_material_count:'待料标记', remaining_material_kg:'预计剩余生产用料',
    known_remaining_material_kg:'用料已知小计', remaining_material_unknown_count:'用料未知需求', forecast_late_count:'预计排期超期风险',
    forecast_unknown_count:'排期预测未知', warehouse_shortage_kg:'仓库实际短缺', actual_delivery_late_count:'实际交货延期'}},
  get_printer_status: {module:'three-d-printing', primary:['printer_count','stale_count','unknown_current_state_count','reported_running_count','physically_stopped_count','task_queue_count'], labels:{
    printer_count:'机台数', current_telemetry_count:'当前有效遥测', stale_count:'观测过期机台', unknown_current_state_count:'当前状态未知',
    reported_running_count:'有效遥测报告运行', physically_stopped_count:'物理停机', task_queue_count:'任务队列'}},
  get_my_work: {module:'work-center', primary:['filtered_count','authorized_actionable_total','authorized_info_unread_total','authorized_overdue_total','authorized_snoozed_total'], labels:{
    filtered_count:'当前筛选事项', authorized_actionable_total:'全部授权 · 可办理', authorized_assigned_total:'全部授权 · 指派',
    authorized_team_queue_total:'全部授权 · 团队队列', authorized_focus_total:'全部授权 · 关注', authorized_snoozed_total:'全部授权 · 稍后',
    authorized_overdue_total:'全部授权 · 逾期', authorized_info_unread_total:'全部授权 · 未读信息', authorized_waiting_total:'全部授权 · 等待',
    authorized_verification_required_total:'全部授权 · 待核实'}},
  list_customer_orders: {module:'customer-orders', primary:['order_count','unfinished_count','remaining_quantity','shipped_quantity','overdue_count','unknown_quantity_count'], labels:{
    order_count:'订单行数', unfinished_count:'未发完订单', remaining_quantity:'未发数量', shipped_quantity:'已发数量', overdue_count:'逾期订单',
    unknown_quantity_count:'数量未知订单', overdue_unknown_count:'逾期口径未知', cancelled_count:'已取消订单'}},
  get_carton_overview: {module:'carton-procurement', primary:['record_count','remaining_quantity','received_quantity','ending_quantity','available_quantity'], labels:{
    record_count:'原台账记录数', pending_count:'未结束单据', overdue_count:'到货逾期单据', required_quantity:'纸品需求量', received_quantity:'履约收料',
    remaining_quantity:'纸品尚未收到', available_quantity:'仓库可用库存', opening_quantity:'期初账面结存', inbound_quantity:'期间入库', outbound_quantity:'期间出库',
    adjustment_quantity:'期间库存调整', ending_quantity:'期末账面结存'}},
  get_internal_quote_overview: {module:'internal-quote', primary:['document_count','version_count'], labels:{document_count:'逻辑报价文档', version_count:'原报价版本'}},
  get_uv_operations_snapshot: {module:'uv-operations', primary:['planned','completed','remaining','incomplete_tasks','overdue_tasks','material_shortage'], labels:{
    tasks:'任务总数', original_tasks:'原生产任务', rework_tasks:'返工任务', cancelled_tasks:'取消任务', planned:'原任务计划量', completed:'最终合格量',
    remaining:'尚未最终处置', scrap:'报废量', incomplete_tasks:'未完成原任务', overdue_tasks:'逾期任务', material_shortage:'实际缺料'}},
  get_spray_operations_snapshot: {module:'spray-production', primary:['finished','scrap','rework_current','wip','in_process','material_shortage'], labels:{
    records:'原记录数', planned:'需求行计划量', white:'当前白胚库存', wip:'当前中间工序在制', hold:'当前待处理库存', finished:'当前合格在库',
    in_process:'待最终处置库存', scrap:'已生效生产报废', arrival_rejected:'来料拒收', rework_current:'当前返工来源库存',
    rework_processed:'返工工序处理量', dispatched:'累计发出交接量', handover_accepted:'累计交接验收', handover_rejected:'累计交接拒收',
    returned:'累计实物退货', in_transit:'交接待验收', net_accepted:'验收减退货', scheduled_input:'工序计划投入', reported_input:'工序已报投入',
    pending_input:'工序待报投入', material_shortage:'实际缺料', settled_amount:'结算金额'}},
}

export interface BusinessFact {
  key: string; label: string; value: string; unit: string; definition: string; unknown: boolean
}
export interface BusinessFacts {
  id: string; title: string; scope: string; status: string; asOf: string; observedAt: string; retrievedAt: string; timezone: string
  cacheHit: boolean; cacheCreatedAt: string
  total: number | null; returned: number; truncated: boolean; primary: BusinessFact[]; otherStates: BusinessFact[]; metrics: BusinessFact[]; unknowns: string[]
}
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const timestamp = (value: unknown) => typeof value === 'string' && Number.isFinite(Date.parse(value)) ? value : ''
const baseKey = (key: string) => key.split(/[\[:]/)[0] || key

export function businessFacts(message: Message): BusinessFacts[] {
  if (message.unavailable || message.role !== 'assistant') return []
  const evidence = message.content_parts.find(p => p.type === 'evidence')
  if (!evidence || evidence.run_id !== message.run_id || !Array.isArray(evidence.sources)) return []
  const sources = evidence.sources.filter(object)
  const facts: BusinessFacts[] = [], seen = new Set<string>()
  for (const part of message.content_parts) {
    const result = part.result
    if (!object(result) || (part.type !== 'business_snapshot' && !(part.type === 'tool_result' && part.name === result.tool_name)) || result.contract_version !== 3 || result.run_id !== message.run_id || typeof result.tool_name !== 'string') continue
    const presentation = presentations[result.tool_name]
    if (!presentation || !['ok','empty','partial','unknown','stale'].includes(String(result.status)) || !object(result.scope) || result.scope.module_id !== presentation.module) continue
    const refs = result.source_refs
    if (!Array.isArray(refs) || !refs.length || !refs.every(id => typeof id === 'string' && sources.some(s => s.kind === 'business' && s.source_id === id && s.run_id === message.run_id && s.tool_name === result.tool_name && s.citation_eligible !== false))) continue
    if (!object(result.metrics) || !object(result.definitions) || typeof result.scope.label !== 'string' || !timestamp(result.as_of) || !timestamp(result.retrieved_at)) continue
    const definitions = result.definitions
    const metrics: BusinessFact[] = []
    for (const [key, metric] of Object.entries(result.metrics)) {
      const label = presentation.labels[baseKey(key)]
      if (!label || !object(metric) || typeof metric.unit !== 'string' || typeof metric.definition_id !== 'string' || typeof definitions[metric.definition_id] !== 'string') continue
      const known = metric.status === 'known'
      if (known ? !(typeof metric.value === 'number' && Number.isSafeInteger(metric.value) || typeof metric.value === 'string' && /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(metric.value)) : metric.value !== null || !['unknown','not_applicable'].includes(String(metric.status))) continue
      const unit = typeof metric.currency === 'string' && metric.currency ? `${metric.unit} · ${metric.currency}` : metric.unit
      metrics.push({key, label, value:known ? String(metric.value) : metric.status === 'not_applicable' ? '不适用' : '未知', unit, definition:String(definitions[metric.definition_id]), unknown:!known})
    }
    if (!metrics.length) continue
    const id = `${String(result.tool_call_id)}:${String(result.step_id)}:${refs.join(':')}`
    if (seen.has(id)) continue
    seen.add(id)
    const primary = presentation.primary.flatMap(key => metrics.filter(m => baseKey(m.key) === key)).slice(0,6)
    const chosen = primary.length ? primary : metrics.slice(0,6)
    const freshness = object(result.freshness) ? result.freshness.state : null
    if (object(result.freshness) && result.freshness.cache_hit !== undefined && typeof result.freshness.cache_hit !== 'boolean') continue
    const cacheHit = object(result.freshness) && result.freshness.cache_hit === true
    const cacheCreatedAt = cacheHit && object(result.freshness) ? timestamp(result.freshness.cache_created_at) : ''
    if (cacheHit && !cacheCreatedAt) continue
    const status = result.status === 'stale' || freshness === 'stale' ? '观测已过期' : result.status === 'empty' ? '空结果' : result.status === 'unknown' ? '状态未知' : result.status === 'partial' ? '含未知项' : '查询快照'
    facts.push({id, title:String(sources.find(s => s.source_id === refs[0])?.title || '业务查询'), scope:result.scope.label,
      status:cacheHit ? `缓存快照${status === '查询快照' ? '' : ` · ${status}`}` : status, cacheHit, cacheCreatedAt,
      asOf:timestamp(result.as_of), observedAt:timestamp(result.observed_at), retrievedAt:timestamp(result.retrieved_at), timezone:typeof result.timezone === 'string' ? result.timezone : '',
      total:typeof result.total_count === 'number' && Number.isSafeInteger(result.total_count) ? result.total_count : null,
      returned:typeof result.returned_count === 'number' && Number.isSafeInteger(result.returned_count) ? result.returned_count : 0, truncated:result.truncated === true,
      primary:chosen, otherStates:metrics.filter(m => m.unknown && !chosen.some(p => p.key === m.key)), metrics,
      unknowns:Array.isArray(result.unknown_fields) ? result.unknown_fields.filter(object).flatMap(u => typeof u.reason === 'string' ? [u.reason] : []) : []})
  }
  return facts
}
