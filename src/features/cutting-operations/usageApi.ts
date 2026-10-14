import { http } from '@/lib/http'
import type { Command } from './api'
import type { MaterialRequestRow } from './materialsApi'
export type UsageAction = 'post'|'void'|'review'|'price'|'correct'
export interface UsageCommand extends Command {
  day:string;issue_id?:string;document_id?:string;consumed_quantity?:string;loss_quantity?:string;counted_remaining?:string
  unit_cost?:string;currency?:string;price_reference?:string
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
export interface UsageLedger {revision:number;issues:UsageIssue[];documents:UsageDocument[];amounts?:Record<string,string>;pending_pricing?:number;price_history?:UsagePrice[]}
export interface UsageBalance {day:string;warehouse_cutoff:number;received_quantity:string;returned_quantity:string;consumed_quantity:string;loss_quantity:string;available_quantity:string;same_day_document_ids:string[];later_documents:Array<{document_id:string;day:string}>;revision:number}
const base='/cutting-operations/orders'
export const usageApi={
  async balance(id:string,issueId:string,day:string,documentId?:string):Promise<UsageBalance>{return(await http.get(`${base}/${encodeURIComponent(id)}/usage-balance`,{params:{factory_id:'huakang-c',issue_id:issueId,day,document_id:documentId||undefined}})).data},
  async read(id:string,withCosts=false):Promise<UsageLedger>{return(await http.get(`${base}/${encodeURIComponent(id)}/usage`,{params:{factory_id:'huakang-c',with_costs:withCosts}})).data},
  async post(id:string,action:UsageAction,body:UsageCommand){return(await http.post(`${base}/${encodeURIComponent(id)}/usage/${action}`,body)).data},
  async recover(id:string,action:UsageAction,command:UsageCommand):Promise<{state:'committed'|'abandoned'}>{return(await http.post(`${base}/${encodeURIComponent(id)}/usage-operations/recover`,{action,command})).data},
}
