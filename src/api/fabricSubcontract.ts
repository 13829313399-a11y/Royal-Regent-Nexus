import { http } from '@/lib/http'

export const processes = ['捆条', '贴合', '电绣', '丝印'] as const
export type Process = typeof processes[number]
export const stageLabels = {
  SELECT: '选入原料', SEND: '原料实发', SIGN: '加工厂签收', DELIVER: '加工厂送达',
  RECEIVE: '回仓点收', ISSUE: '领用发料', VOID: '更正凭证', SOURCE: '补录来源',
} as const
export type Stage = keyof typeof stageLabels
export const actionLabels = {
  ...stageLabels, SEND: '发给加工厂', DELIVER: '加工厂送回', RECEIVE: '点收已到货', ISSUE: '部门领用',
} as const
export interface Processor {
  id: string; code: string; name: string; processes: Process[]; contact: string; phone: string; active: boolean
}
export interface Material {
  id: string; item_code: string; item_name: string; unit: string; material_category: string
}
export interface Batch extends Material {
  lot: string; roll_no: string; location: string; location_id: string; available?: string; output_id?: string
}
export interface Output extends Material {
  planned: string; delivered: string; received: string; outstanding: string; undelivered: string; uncounted: string; available: string
}
export interface OrderEvent {
  id: string; kind: Stage; target_id: string; business_date: string; recorded_at: string; quantity: string; unit: string;
  item_name: string; voucher: string; actor: string; voided: boolean; reason?: string; stock_id?: string;
  recipient?: string; destination?: string; remaining?: string; lot?: string; roll_no?: string; location?: string; batch?: Batch; output_id?: string
}
export interface SubOrder {
  id: string; process: Process; processor: Processor; business_date: string; due_date: string; source_no: string; previous_order_id?: string | null;
  inputs: (Batch & { planned: string; sent: string })[]; outputs: Output[]; batches: Batch[]; events: OrderEvent[]
  other_movements: { id: string; kind: 'ISSUE'|'TRANSFER'|'RETURN'|'CORRECTION'; business_date: string; actor: string;
    voucher: string; recipient: string; destination: string; item_name: string; quantity: string; unit: string; reversed: boolean }[]
}
export interface SubWorkspace {
  revision: number; processors: Processor[]; materials: Material[]; stock: Batch[]; orders: SubOrder[];
  locations: { id: string; label: string; category: string; status: string }[];
  can_operate: boolean; can_correct: boolean; can_manage: boolean
}
const base = '/warehouse-operations/fabric/subcontract'
export const subcontractApi = {
  async processors(): Promise<SubWorkspace> {
    const response = await http.get<Pick<SubWorkspace, 'processors'|'revision'|'can_manage'>>(base+'/processors', {params:{factory_id:'huakang-c'}})
    return {...response.data, orders:[], stock:[], materials:[], locations:[], can_correct:false, can_operate:false}
  },
  async workspace() { return (await http.get<SubWorkspace>(base, { params: { factory_id: 'huakang-c' } })).data },
  async save(path: string, body: Record<string, unknown>) {
    return (await http.post<{ id?: string; order_id?: string }>(base + path, body)).data
  },
}
export const warehouseDay = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date())
export const batchLabel = (b: Batch) => [b.item_code, b.item_name, b.location, b.lot && '缸 ' + b.lot,
  b.roll_no && '卷 ' + b.roll_no, b.available && '可用 ' + b.available + ' ' + b.unit].filter(Boolean).join(' · ')
