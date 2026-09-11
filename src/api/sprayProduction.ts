import { http } from '@/lib/http'

export interface SprayEntity { id: string; [key: string]: unknown }
export interface SpraySummary {
  factory_id: string; revision: number; as_of: string; data_mode: string; coverage: string
  counts: Record<string, number>; permissions: string[]
}
export interface SprayPage { items: SprayEntity[]; total: number; page: number; page_size: number }
export interface SprayResult { id?: string; ids?: string[]; revision: number; [key: string]: unknown }
export const sprayProductionApi = {
  async summary(factory: string, signal?: AbortSignal) {
    return (await http.get<SpraySummary>('/spray-production/summary', { params: { factory_id: factory }, signal })).data
  },
  async collection(factory: string, kind: string, signal?: AbortSignal, page = 1) {
    return (await http.get<SprayPage>(`/spray-production/collections/${kind}`, { params: { factory_id: factory, page, page_size: 1000 }, signal })).data
  },
  async balances(factory: string, signal?: AbortSignal, page = 1) {
    return (await http.get<Record<string, Record<string, string>>>('/spray-production/balances', { params: { factory_id: factory, page }, signal })).data
  },
  async command(factory: string, action: string, payload: Record<string, unknown>) {
    return (await http.post<SprayResult>(`/spray-production/commands/${action}`, { ...payload, factory_id: factory })).data
  },
  async trace(factory: string, batch: string) {
    return (await http.get<{ balances: Record<string, string>; movements: SprayEntity[] }>(`/spray-production/batches/${batch}/trace`, { params: { factory_id: factory } })).data
  },
  async settlementPreview(factory: string, payload: Record<string, unknown>) {
    return (await http.post<SprayEntity>('/spray-production/settlements/preview', { ...payload, factory_id: factory })).data
  },
  async upload(factory: string, file: File) {
    const data = new FormData(); data.append('file', file)
    return (await http.post<{ id: string }>('/spray-production/imports', data, { params: { factory_id: factory }, headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 })).data
  },
  async source(factory: string, id: string, sheet = '', page = 1) {
    return (await http.get<{ source: SprayEntity; sheets: string[]; total: number; rows: SprayEntity[] }>(`/spray-production/imports/${id}`, { params: { factory_id: factory, sheet, page } })).data
  },
  async preferences(factory: string) { return (await http.get<{items:SprayEntity[]}>('/spray-production/preferences',{params:{factory_id:factory}})).data.items },
  async payrollPreview(factory:string,payload:Record<string,unknown>) { return (await http.post<SprayResult>('/spray-production/payroll/preview',{...payload,factory_id:factory})).data },
  async historyPreview(factory:string,payload:Record<string,unknown>) { return (await http.post<SprayResult>('/spray-production/history/preview',{...payload,factory_id:factory}, {timeout:120000})).data },
  async reconcile(factory:string,period:string) { return (await http.get<SprayResult>('/spray-production/history/reconcile',{params:{factory_id:factory,period}})).data },
  async template(factory:string,id:string) { return (await http.get<Blob>(`/spray-production/imports/${id}/template`,{params:{factory_id:factory},responseType:'blob'})).data },
  async renderTemplate(factory:string,id:string,bindings:Record<string,unknown>[]) { return (await http.post<Blob>(`/spray-production/imports/${id}/render`,{factory_id:factory,bindings},{responseType:'blob'})).data },
  async mappingSuggestion(factory:string,id:string,sheet:string) { return (await http.get<Record<string,unknown>>(`/spray-production/imports/${id}/mapping-suggestion`,{params:{factory_id:factory,sheet}})).data },
}
