import { http } from '@/lib/http'
import { CUTTING_FACTORY } from './navigation'
import type { CuttingOrder } from './ordersApi'
import type { UsageIssue } from './usageApi'
export interface Page<T> { data:T[];total:number;page:number;page_size:number;token?:string }
export interface Identity { line_id:string;order_no:string;customer:string;item_no:string }
export interface TaskRow extends Identity {
  task_id:string;task_name:string;resource_name:string;execution:string;planned:number;reported:boolean;has_fact:boolean
  day_completed:number;day_handed:number;completed:number;target_sets:number;returned:number;accepted:number;historical:boolean;reasons:string[]
}
export interface TaskView extends Page<TaskRow> {
  day:string;stats:{tasks:number;reported:number;unreported:number;planned:number;completed:number;handed:number;abnormal:number;unplanned_facts:number}
}
export interface PlanningView extends Page<CuttingOrder> { stats:{total:number;scheduled:number;unscheduled:number;partial:number;review:number} }
export interface InventoryView extends Page<UsageIssue & Identity & {unsigned_quantity:string;issue_count?:number}> {units:Record<string,Record<string,string>>}
export interface CostRow extends Identity {normal:Record<string,string>;loss:Record<string,string>;completed:Record<string,string|null>;wip:Record<string,string|null>;pending_pricing:number;allocation_pending:number}
export interface CostView extends Page<CostRow> {currencies:Record<string,{normal:string;loss:string;completed:string|null;wip:string|null}>;pending_pricing:number}
export type FinancialDomain='period'|'settlement'|'payment'
export interface FrozenRecord {kind:FinancialDomain;event_id:string;document_id:string;version:number;month:string;valid:boolean;actor:string;date:string}
export interface MonthView {month:string;domains:Array<{kind:FinancialDomain;available:boolean;reason?:string;states?:Record<string,number>;count?:number}>;frozen:FrozenRecord[]}
export interface ActivityRow {order_no?:string|null;price_evidence?:{line_id:string;task_id:string;unit_price:string;currency:string;evidence:string};source:string;id:string;line_id:string;version:number;action:string;occurred_at:string;business_day:string|null;document_id:string;actor:string;reason:string;related_id:string|null;month:string|null}
const get=async<T>(path:string,params:Record<string,unknown>={})=>(await http.get<T>(`/cutting-operations/workspace/${path}`,{params:{factory_id:CUTTING_FACTORY,...params}})).data
export const workspaceApi={
  planning:(params:Record<string,unknown>)=>get<PlanningView>('planning',params),
  tasks:(params:Record<string,unknown>)=>get<TaskView>('tasks',params),
  inventory:(params:Record<string,unknown>)=>get<InventoryView>('inventory',params),
  costs:(params:Record<string,unknown>)=>get<CostView>('costs',params),
  activity:(params:Record<string,unknown>)=>get<Page<ActivityRow>>('activity',params),
  masters:()=>get<{bom:number;draft:number;material:number;resource:number}>('masters'),
  monthly:(month:string)=>get<MonthView>(`months/${month}`),
}
export const businessDay=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())
