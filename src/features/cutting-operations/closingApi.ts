import { http } from '@/lib/http'
import { CUTTING_FACTORY } from './navigation'
import type { ReportDocument } from './reportingApi'

export interface MonthlyProduction {
  task_id:string; task_name:string; resource_name:string; execution:string; planned:number
  opening_completed:number; closing_completed:number; completed:number; handed:number
  claimed:number; returned:number; accepted:number; rejected:number; completed_unhanded:number
  pending_return:number; pending_acceptance:number; missing_days:string[]
  daily_rejected:number; daily_scrap:number; loose:Array<{code:string;name:string;quantity:number;rejected:number;scrap:number}>
}
export interface MonthlyMaterial {
  issue_id:string; context:{item_name:string;unit:string;root_batch_id:string;task_name:string;resource_name:string}
  opening_quantity:string;issued_quantity:string;unsigned_quantity:string;received_quantity:string
  returned_quantity:string;consumed_quantity:string;loss_quantity:string;ending_quantity:string
  normal_cost?:string|null;loss_cost?:string|null
  price?:{version:number;actor:string;date:string;reason:string;data:{entry:{unit_cost:string;currency:string;price_reference:string}}}|null
}
export interface ClosingPreview {
  line_id:string;month:string;start:string;end:string;through:string;generated_at:string;state:'preview';partial:boolean
  basis:{order_version:number;plan_version:number|null;usage_revision:number;warehouse_revision:number}
  plan_stale?:boolean;production:MonthlyProduction[];materials:MonthlyMaterial[]
  issues:Array<{code:string;message:string;workspace:string;document_id:string;task_id?:string;issue_id?:string}>
  costs?:Record<string,{normal:string;loss:string}>;pending_pricing?:number;wip_status?:'not_frozen'
  current_allocation_review?:Array<{task_name:string;resource_name:string;status:string;reasons:string[]}>
  production_documents:Array<ReportDocument & {scope?:TraceScope}>
  usage_documents:Array<{document_id:string;effective:boolean;scope?:TraceScope;context?:TraceContext;history:Array<{id:string;action:string;version:number;day:string;actor:string;date:string;reason:string;entry:{consumed_quantity?:string;loss_quantity?:string;counted_remaining?:string};replaces_document_id?:string;replaced_by_document_id?:string}>}>
  warehouse_documents:Array<{id:string;kind:string;day:string;original_id:string|null;quantity:string|null;unit:string|null;reversed:boolean;actor:string;date:string;reason:string;context?:TraceContext;scope?:'opening'|'period'|'later'}>
}
export interface TraceScope {opening:boolean;period:boolean;earlier_history:boolean;period_history:boolean}
export interface TraceContext {task_id?:string;task_name?:string;resource_name?:string;item_code?:string;item_name?:string;unit?:string;issue_id?:string;request_id?:string;root_batch_id?:string}

export const closingApi = {
  async read(lineId:string, month:string, withCosts=false):Promise<ClosingPreview> {
    return (await http.get(`/cutting-operations/orders/${encodeURIComponent(lineId)}/closing-preview`,
      {params:{factory_id:CUTTING_FACTORY,month,with_costs:withCosts}})).data
  },
}
