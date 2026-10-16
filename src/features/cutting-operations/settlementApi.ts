import { http } from '@/lib/http'
import { CUTTING_FACTORY } from './navigation'
import type { Command } from './api'

export type FeeAction='price'|'save'|'submit'|'return'|'confirm'|'reopen'
export type FeeState='open'|'draft'|'submitted'|'returned'|'confirmed'|'reopened'
export type FeeCurrency='CNY'|'HKD'|'USD'
export interface FeePrice {id:string;version:number;actor:string;actor_id:string;date:string;reason:string;unit_price:string;currency:FeeCurrency;evidence:string;tax_basis:'inclusive'}
export interface FeeRow {
  line_id:string;task_id:string;acceptance_id:string;acceptance_event_id:string;day:string;accepted_sets:number;reserved_sets:number;available_sets:number;task_remaining_sets:number
  correction_pending:boolean;context_token:string;context:{task_name:string;resource_name:string;resource_id:string;task_target:number;bom_id:string;bom_version:number;plan_version:number}
  order:Record<string,string|number|null>
  acceptance_evidence:string;acceptance_actor:string;acceptance_date:string;price:FeePrice|null
}
export interface FeeSelection {line_id:string;acceptance_id:string;sets:number}
export interface FeeSave extends Command {document_id:string;month:string;basis_token:string;selections:FeeSelection[];vendor_evidence:string;vendor_confirmation_token?:string}
export interface FeeQuote extends Command {line_id:string;task_id:string;context_token:string;unit_price:string;currency:FeeCurrency;evidence:string}
export interface FeeDecision extends Command {document_id:string}
export type FeeBody=FeeSave|FeeQuote|FeeDecision
export interface FeeBasis {month:string;cutoff:string;rows:FeeRow[];revision:number;basis_token:string}
export interface FeeSnapshot {month:string;cutoff:string;resource_id:string;resource_name:string;currency:FeeCurrency;rows:Array<FeeRow&{sets:number;amount:string;prior_priced_sets:number}>;sets:number;total:string;tax_basis:'inclusive';vendor_evidence:string}
export interface FeeRecord {
  dependencies?:Array<{document_id:string;month:string;state:FeeState;sets:number;version:number}>
  totals?:Array<{state:FeeState;currency:FeeCurrency;sets:number;total:string}>
  previous_snapshot?:FeeSnapshot|null
  revision:number;document_id:string|null;state:FeeState;selected_state:FeeState;event_id:string|null
  statements:Array<{document_id:string;event_id:string;state:FeeState;month:string;resource_name:string;currency:FeeCurrency;total:string;sets:number}>
  data:{input:FeeSave;snapshot:FeeSnapshot;prepared_by:string;submitted_by:string|null;replaces_id:string|null;local_admin_acceptance?:boolean;confirmed_at?:string;vendor_confirmation?:{token:string;actor:string;date:string}|null}|null
  history:Array<{id:string;action:FeeAction;version:number;actor:string;actor_id:string;date:string;reason:string}>
  price_history:FeePrice[]
}
const base='/cutting-operations'
export const settlementApi={
  async preview(body:FeeSave):Promise<{snapshot:FeeSnapshot;confirmation_token:string}>{return(await http.post(`${base}/settlement-preview`,body)).data},
  async read(month:string,documentId?:string,eventId?:string):Promise<FeeRecord>{return(await http.get(`${base}/settlements/${encodeURIComponent(month)}`,{params:{factory_id:CUTTING_FACTORY,document_id:documentId,event_id:eventId}})).data},
  async basis(month:string,documentId?:string):Promise<FeeBasis>{return(await http.get(`${base}/settlements/${encodeURIComponent(month)}/basis`,{params:{factory_id:CUTTING_FACTORY,document_id:documentId}})).data},
  async write(action:FeeAction,body:FeeBody):Promise<{document_id:string}>{return(await http.post(`${base}/settlements/${action}`,body)).data},
  async recover(action:FeeAction,body:FeeBody):Promise<{state:'committed'|'abandoned'}>{return(await http.post(`${base}/settlement-operations/recover`,{action,command:body})).data},
}
