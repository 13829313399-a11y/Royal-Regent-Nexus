import { http } from '@/lib/http'
import { CUTTING_FACTORY } from './navigation'
import type { Command } from './api'
import type { FeeCurrency } from './settlementApi'

export type PaymentAction='save'|'submit'|'return'|'confirm'|'reverse'
export type PaymentState='open'|'draft'|'submitted'|'returned'|'confirmed'|'reversed'
export interface PaymentAllocation {settlement_id:string;amount:string}
export interface PaymentSave extends Command {
  document_id:string;base_event_id?:string|null;day:string;voucher_no:string;method:'bank'|'cash'|'cheque'|'other';evidence:string
  currency:FeeCurrency;amount:string;basis_token:string;allocations:PaymentAllocation[];replaces_document_id:string|null
}
export interface PaymentDecision extends Command {document_id:string}
export type PaymentBody=PaymentSave|PaymentDecision
export interface PayableRow {
  settlement_id:string;settlement_event_id:string;month:string;resource_id:string;resource_name:string;currency:FeeCurrency
  payable:string;paid:string;pending:string;unpaid:string;available:string
  payments:Array<{document_id:string;day:string;state:PaymentState;amount:string;voucher_no:string}>
}
export interface PaymentBasis {rows:PayableRow[];revision:number;basis_token:string;document?:{event_id:string;input:PaymentSave;snapshot:PaymentSnapshot;actor:string;date:string}|null}
export interface PaymentSnapshot {
  day:string;voucher_no:string;method:PaymentSave['method'];evidence:string;resource_id:string;resource_name:string
  currency:FeeCurrency;amount:string;allocations:Array<PayableRow&{amount:string}>;replaces_document_id:string|null
}
export interface PaymentRecord {
  month?:string;current_month?:string
  previous_compilation?:{event_id:string;snapshot:PaymentSnapshot;actor:string;date:string}|null
  revision:number;rows:PayableRow[];totals:Array<{currency:FeeCurrency;payable:string;paid:string;pending:string;unpaid:string;available:string}>
  documents:Array<{document_id:string;day:string;state:PaymentState;voucher_no:string;resource_name:string;currency:FeeCurrency;amount:string;replaces_document_id:string|null}>
  document_id:string|null;state:PaymentState;selected_state:PaymentState;event_id:string|null
  data:{input:PaymentSave;snapshot:PaymentSnapshot;prepared_by:string;submitted_by:string|null;local_admin_acceptance?:boolean;confirmed_at?:string;reversed_at?:string}|null
  history:Array<{id:string;action:PaymentAction;actor:string;date:string;reason:string;month?:string}>
  replacements:Array<{document_id:string;day:string;state:PaymentState}>
  original?:{document_id:string;day:string;state:PaymentState}|null
}
const base='/cutting-operations'
export const paymentApi={
  async read(month:string,id?:string,eventId?:string):Promise<PaymentRecord>{return(await http.get(`${base}/payments/${encodeURIComponent(month)}`,{params:{factory_id:CUTTING_FACTORY,document_id:id,event_id:eventId}})).data},
  async basis(id?:string):Promise<PaymentBasis>{return(await http.get(`${base}/payment-basis`,{params:{factory_id:CUTTING_FACTORY,document_id:id}})).data},
  async preview(body:PaymentSave):Promise<PaymentSnapshot>{return(await http.post(`${base}/payment-preview`,body)).data},
  async write(action:PaymentAction,body:PaymentBody):Promise<{document_id:string;id?:string;month?:string}>{return(await http.post(`${base}/payments/${action}`,body)).data},
  async recover(action:PaymentAction,body:PaymentBody):Promise<{state:'committed'|'abandoned';result?:{document_id:string;id?:string;month?:string}}>{return(await http.post(`${base}/payment-operations/recover`,{action,command:body})).data},
}
