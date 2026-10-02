import { http } from '@/lib/http'
import type { BusinessOrderAlert } from '@/features/carton-procurement/businessAlerts'
import type { CartonExceptionResponse, CartonImportBatchResponse, CartonOrderResponse, CartonScheduleOrder } from './cartonProcurement'

export type DashboardOrder = Omit<CartonScheduleOrder, 'split_records'> & { order_date: string; due_date: string }
export interface CartonDashboardWorkspace {
  factory_id: string; business_date: string; generated_at: string
  items: BusinessOrderAlert[]; total: number; offset: number; limit: number
  summary: { total: number; missing: number; increase: number; decrease: number }
  reminders: BusinessOrderAlert[]
  pending_order_count: number; open_exception_count: number; weekly_attention_count: number
  inventory_by_unit: { unit: string; quantity: string }[]
  recent_orders: DashboardOrder[]; priority_exceptions: CartonExceptionResponse[]
  pending_splits: DashboardOrder[]; pending_split_count: number
}
export const cartonDashboardApi = {
  async workspace(factory: string, filters: { customer: string; search: string; status: string; kind: string; offset: number; limit: number }) {
    return (await http.get<CartonDashboardWorkspace>('/carton-procurement/dashboard/workspace', { params: { factory_id: factory, ...filters } })).data
  },
  async batch(factory: string, id: string) {
    return (await http.get<CartonImportBatchResponse>(`/carton-procurement/imports/${encodeURIComponent(id)}`, { params: { factory_id: factory } })).data
  },
  async context(factory: string, id: string) {
    return (await http.get<{ alert: BusinessOrderAlert; batch: CartonImportBatchResponse; orders: CartonOrderResponse[]; matching_orders: CartonScheduleOrder[]; marks: Record<string, { marked: boolean; actor: string; updated_at: string }> }>('/carton-procurement/dashboard/alert-context', { params: { factory_id: factory, alert_id: id } })).data
  },
}
