import { http } from '@/lib/http'
import { CUTTING_FACTORY } from './navigation'
import type { Command } from './api'
import type { ClosingPreview, MonthlyMaterial } from './closingApi'

export type PeriodAction='save'|'submit'|'return'|'lock'|'reopen'
export type PeriodState='open'|'draft'|'submitted'|'returned'|'locked'|'reopened'
export interface PeriodIssue {code:string;message:string;line_id?:string;issue_id?:string;workspace?:string;document_id?:string;task_id?:string}
export interface PeriodRow {
  issue_id:string;line_id:string;context:{task_name:string;resource_name:string;item_name:string;unit:string;root_batch_id:string}
  opening_normal_quantity:string;ending_normal_quantity:string;opening_loss_quantity:string;ending_loss_quantity:string
  opening_custody:string;ending_custody:string;opening_sets:number|null;ending_sets:number|null;carried_completed_quantity:string|null
  opening_completed_quantity?:string;completed_quantity?:string;opening_wip_quantity?:string;ending_wip_quantity?:string
  currency?:string;amounts?:Record<string,string>;price:MonthlyMaterial['price']
}
export interface PeriodAllocation {issue_id:string;opening_completed_quantity:string;completed_quantity:string}
export interface PeriodSave extends Command {
  month:string;basis_token:string;allocations:PeriodAllocation[];materials_complete:boolean;public_material_pending:boolean
  opening_verified:boolean;unrecorded_opening:boolean;exceptions_reviewed:boolean
}
export interface PeriodDecision extends Command {month:string}
export interface PeriodSnapshot {
  month:string;start:string;end:string;orders:ClosingPreview[];allocations:PeriodRow[];costs:Record<string,Record<string,string>>
  blockers:PeriodIssue[];notices:PeriodIssue[];previous_month:string|null;previous_lock_id:string|null;generated_at:string
}
export interface PeriodEvent {id:string;month:string;version:number;action:PeriodAction;actor:string;actor_id:string;date:string;reason:string}
export interface PeriodComparison {
  previous_id:string;previous_version:number;previous_actor:string;previous_date:string;previous_reason:string
  evidence_changed:boolean;partial_pricing:boolean;costs:Record<string,Record<string,string>>
  orders:Array<Pick<ClosingPreview,'line_id'|'order_snapshot'>>
  rows:Array<{issue_id:string;line_id:string;before:PeriodRow|null;after:PeriodRow|null;quantity_delta:Record<string,string>;amount_delta:Record<string,string>|null}>
}
export interface PeriodRecord {
  comparison?:PeriodComparison|null
  first_month?:string|null;next_month?:string|null;pending_reclose?:string[];sequence_repair?:boolean
  month:string;revision:number;state:PeriodState;selected_state:PeriodState;event_id:string|null;history:PeriodEvent[];locked_months:string[]
  data:{basis_token:string;input:PeriodSave;snapshot:PeriodSnapshot;submitted_by:string|null;local_admin_acceptance?:boolean}|null
}
export interface PeriodBasis {month:string;basis_token:string;revision:number;state:PeriodState;rows:PeriodRow[];orders?:ClosingPreview[];blockers:PeriodIssue[];notices:PeriodIssue[];previous_month:string|null}
const base='/cutting-operations'
export const periodApi={
  async read(month:string,eventId?:string):Promise<PeriodRecord>{return(await http.get(`${base}/periods/${encodeURIComponent(month)}`,{params:{factory_id:CUTTING_FACTORY,event_id:eventId}})).data},
  async basis(month:string):Promise<PeriodBasis>{return(await http.get(`${base}/periods/${encodeURIComponent(month)}/basis`,{params:{factory_id:CUTTING_FACTORY}})).data},
  async write(action:PeriodAction,body:PeriodSave|PeriodDecision){return(await http.post(`${base}/periods/${action}`,body)).data},
  async recover(action:PeriodAction,body:PeriodSave|PeriodDecision):Promise<{state:'committed'|'abandoned'}>{return(await http.post(`${base}/period-operations/recover`,{action,command:body})).data},
}
