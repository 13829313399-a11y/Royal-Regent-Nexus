import { http } from '@/lib/http'
import type { Command } from './api'
import type { MaterialRequestRow } from './materialsApi'
export type UsageAction = 'post'|'void'|'review'|'price'|'correct'|'allocate'
export interface UsageCommand extends Command {
  day:string;issue_id?:string;document_id?:string;consumed_quantity?:string;loss_quantity?:string;counted_remaining?:string
  unit_cost?:string;currency?:string;price_reference?:string
  basis_token?:string;allocations?:Array<{issue_id:string;completed_quantity:string}>;materials_complete?:boolean;public_material_pending?:boolean
}
export interface UsagePrice {version:number;actor:string;date:string;reason:string;data:{context?:UsageIssue['context'];entry:{day:string;unit_cost:string;currency:string;price_reference:string;issue_id?:string}}}
export interface UsageIssue {
  issue_id:string;context:MaterialRequestRow['context']&{root_batch_id:string;unit:string;item_code:string;item_name:string;lot:string;roll_no:string;location:string}
  reversed:boolean;issued_quantity:string;received_quantity:string;returned_quantity:string;consumed_quantity:string;loss_quantity:string;remaining_quantity:string
  price?:UsagePrice|null;cost_status?:string;normal_cost?:string|null;loss_cost?:string|null
}
export interface UsageDocument {
  id:string;voided:boolean;reviewed:boolean;entry:{day:string;issue_id:string;consumed_quantity:string;loss_quantity:string;counted_remaining:string}
  context:UsageIssue['context'];actor:string;created_at:string;reason:string;cost_at_post?:{version:number;unit_cost:string;currency:string}|null
  warehouse_cutoff?:number;replaces_document_id?:string|null;replaced_by_document_id?:string|null
  history:Array<{id:string;version:number;action:string;actor:string;date:string;business_day:string;reason:string}>
}
export interface CostGroup {
  key:string;issue_count:number;pending_pricing:number
  costs:Record<string,{normal:string;loss:string;total:string}>
}
export interface UsageCostSummary {
  tasks:Array<CostGroup & {context:Pick<UsageIssue['context'],'dispatch_id'|'bom_id'|'bom_version'|'task_id'|'resource_id'|'resource_version'|'task_name'|'resource_name'|'execution'>}>
  materials:Array<CostGroup & {material:UsageIssue['context']['warehouse_material'];item_code:string;item_name:string;unit:string
    received_quantity:string;returned_quantity:string;consumed_quantity:string;loss_quantity:string;remaining_quantity:string;pending_quantity:string}>
}
export interface AllocationGroup {
  key:string;context:UsageCostSummary['tasks'][number]['context'];basis_token:string;completed_sets:number|null
  status:'blocked'|'unconfirmed'|'stale'|'pending'|'confirmed';reasons:string[];pending_pricing:number
  rows:Array<{issue_id:string;item_name:string;root_batch_id:string;unit:string;consumed_quantity:string;completed_quantity:string|null;wip_quantity:string|null}>
  costs:Record<string,{completed:string|null;wip:string|null;loss:string;unit_cost:string|null}>
  materials_complete:boolean;public_material_pending:boolean;latest_id:string|null
}
export interface CostAllocationView {
  schema_ready:boolean;groups:AllocationGroup[]
  history:Array<{id:string;version:number;actor:string;date:string;reason:string;context:AllocationGroup['context'];entry:UsageCommand;completed_sets:number;replaces_id:string|null
    price_snapshot:Array<{issue_id:string;price:UsagePrice|null;normal_cost:string|null;loss_cost:string|null}>
    basis_documents?:{usage?:Array<{document_id:string;event_id:string;version:number;entry:{day:string;issue_id:string;consumed_quantity:string;loss_quantity:string}}>
      production?:Array<{document_id:string;event_id:string;version:number;entry:{day:string;kind:string;sets:number}}>}}>
}
export interface UsageLedger {revision:number;issues:UsageIssue[];documents:UsageDocument[];amounts?:Record<string,string>;pending_pricing?:number;price_history?:UsagePrice[];cost_summary?:UsageCostSummary;cost_allocation?:CostAllocationView}
export interface UsageBalance {day:string;warehouse_cutoff:number;received_quantity:string;returned_quantity:string;consumed_quantity:string;loss_quantity:string;available_quantity:string;same_day_document_ids:string[];later_documents:Array<{document_id:string;day:string}>;revision:number}
const base='/cutting-operations/orders'
export const usageApi={
  async balance(id:string,issueId:string,day:string,documentId?:string):Promise<UsageBalance>{return(await http.get(`${base}/${encodeURIComponent(id)}/usage-balance`,{params:{factory_id:'huakang-c',issue_id:issueId,day,document_id:documentId||undefined}})).data},
  async read(id:string,withCosts=false):Promise<UsageLedger>{return(await http.get(`${base}/${encodeURIComponent(id)}/usage`,{params:{factory_id:'huakang-c',with_costs:withCosts}})).data},
  async post(id:string,action:UsageAction,body:UsageCommand){return(await http.post(`${base}/${encodeURIComponent(id)}/usage/${action}`,body)).data},
  async recover(id:string,action:UsageAction,command:UsageCommand):Promise<{state:'committed'|'abandoned'}>{return(await http.post(`${base}/${encodeURIComponent(id)}/usage-operations/recover`,{action,command})).data},
}
