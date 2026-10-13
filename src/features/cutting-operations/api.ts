import { http } from '@/lib/http'
import { CUTTING_FACTORY } from './navigation'

export type Kind = 'material' | 'resource' | 'bom'
export interface MaterialData { name: string; category: 'fabric' | 'accessory'; unit: string; specification: string; color: string; source_reference: string }
export interface WorkCalendarData { weekdays: number[]; exceptions: Array<{ day: string; working: boolean; reason: string }>; basis: string }
export interface ResourceData { calendar?: WorkCalendarData | null; preparation_workdays?: number; name: string; execution: 'internal' | 'outsourced'; process: 'cutting'; contact: string; source_reference: string }
export interface Part { code: string; name: string; pieces_per_set: number }
export interface Requirement { material_id: string; material_version: number; part_codes: string[]; quantity_per_set: string; unit: string; required_for_cutting: boolean; stage: string; note: string }
export interface BomData { name: string; item_no: string; style: string; color: string; source_reference: string; parts: Part[]; requirements: Requirement[] }
export type MasterData = MaterialData | ResourceData | BomData
export interface MasterRecord { id: string; factory_id: string; kind: Kind; code: string; version: number; status: 'active' | 'inactive' | 'draft' | 'published'; data: MasterData; actor_id: string; created_at: string; reason: string; material_references?: Record<string, { code: string; name: string }> }
export interface MasterPage { data: MasterRecord[]; total: number; page: number; page_size: number }
export interface Access { enabled: boolean; schema_ready: boolean; orders_schema_ready?: boolean; reporting_schema_ready?: boolean; permissions: string[] }
export interface Command { factory_id: typeof CUTTING_FACTORY; operation_id: string; expected_version: number; reason: string }
export interface SaveCommand extends Command { kind: Kind; code: string; data: MasterData }
export interface StateCommand extends Command { status: 'active' | 'inactive' | 'published' }
const base = '/cutting-operations'
export const cuttingApi = {
  async access(): Promise<Access> { return (await http.get(`${base}/access`, { params: { factory_id: CUTTING_FACTORY } })).data },
  async list(kind: Kind, page = 1, q = ''): Promise<MasterPage> { return (await http.get(`${base}/masters`, { params: { factory_id: CUTTING_FACTORY, kind, page, q } })).data },
  async versions(id: string, page = 1): Promise<MasterPage> { return (await http.get(`${base}/masters/${encodeURIComponent(id)}/versions`, { params: { factory_id: CUTTING_FACTORY, page } })).data },
  async save(body: SaveCommand, id?: string): Promise<MasterRecord> { return id ? (await http.put(`${base}/masters/${encodeURIComponent(id)}`, body)).data : (await http.post(`${base}/masters`, body)).data },
  async state(id: string, body: StateCommand): Promise<MasterRecord> { return (await http.post(`${base}/masters/${encodeURIComponent(id)}/state`, body)).data },
}

export function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(e => `${e.loc?.join('.') ?? ''}：${e.msg}`).join('；')
  return '请求未完成，请检查连接后重试。'
}
