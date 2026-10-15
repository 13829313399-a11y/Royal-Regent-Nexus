import { http } from '@/lib/http'
import type { Command, MaterialData } from './api'
export type MaterialAction = 'request' | 'receive' | 'void' | 'close' | 'reuse'
export interface WarehouseMaterial { id: string; code: string; name: string; revision: number; unit: string; category: string; spec: string; color: string }
export interface MaterialCommand extends Command { business_date: string; original_id?: string; quantity?: string; task_id?: string; plan_version?: number; row?: number; material_id?: string; material_revision?: number; mapping_basis?: string; due_date?: string|null }
export interface MaterialRequestRow {
  due_date?: string|null; accepted_plan_version?: number; history?: Array<{id:string;original_id:string;kind:string;date:string;occurred_at:string;actor:string;reason:string;quantity:string;reversed:boolean;plan_version?:number|null}>
  id: string; date: string; quantity: string; issued_quantity: string; unit: string; item_code: string; item_name: string; closed: boolean; close_reason: string; reason: string
  context: { dispatch_id?: string; bom_id?: string; resource_id?: string; resource_version?: number; order_no: string; plan_version: number; bom_version: number; task_id: string; task_name: string; resource_name: string; execution: string; row: number; mapping_basis: string; cutting_material: MaterialData & {code:string}; warehouse_material: WarehouseMaterial }
  issues: Array<{ id:string; date:string; quantity:string; received_quantity:string; returned_quantity:string; reversed:boolean; lot:string; roll_no:string; location:string }>
  receipts: Array<{id:string;original_id:string;date:string;quantity:string;reason:string;actor:string;reversed:boolean}>
}
export interface MaterialTotals {
  basis_plan_version?:number;basis_target_sets?:number|null
  dispatch_id: string; bom_id: string; bom_version: number; task_id: string; resource_id: string; resource_version: number; row: number
  task_name: string; material_name: string; unit: string; theoretical_quantity: string|null
  requested_quantity: string; effective_requested_quantity: string; issued_quantity: string; received_quantity: string; returned_quantity: string; net_received_quantity: string; outstanding_quantity: string; exceeds_theoretical: boolean
}
export interface MaterialLedger { revision: number; requests: MaterialRequestRow[]; totals?: MaterialTotals[] }
const base = '/cutting-operations'
export const materialApi = {
  async catalog(q='',page=1):Promise<{items:WarehouseMaterial[];total:number;page:number}> { return (await http.get(`${base}/warehouse-materials`,{params:{factory_id:'huakang-c',q,page}})).data },
  async read(id:string):Promise<MaterialLedger> { return (await http.get(`${base}/orders/${encodeURIComponent(id)}/materials`,{params:{factory_id:'huakang-c'}})).data },
  async post(id:string,action:MaterialAction,body:MaterialCommand) { return (await http.post(`${base}/orders/${encodeURIComponent(id)}/materials/${action}`,body)).data },
  async recover(id:string,action:MaterialAction,command:MaterialCommand):Promise<{state:'committed'|'abandoned'}> { return (await http.post(`${base}/orders/${encodeURIComponent(id)}/material-operations/recover`,{action,command})).data },
}
