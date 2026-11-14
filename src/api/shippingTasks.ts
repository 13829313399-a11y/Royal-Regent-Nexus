import { http } from '../lib/http.js'

export interface ShippingScheduleTask {
  id: string
  factory_id: string
  source: string
  so_number: string
  customer: string
  container_type: string
  port: string
  destination_country: string
  shipment_mode: string
  status: string
  planned_ship_date: string
  si_deadline: string
  cutoff_date: string
  created_at: string
  updated_at: string
}

export async function listShippingTasks(
  factoryId: string,
  params: { q?: string; status?: string } = {},
) {
  const { data } = await http.get<{ tasks: ShippingScheduleTask[] }>('/shipping/tasks', {
    params: { factory_id: factoryId, q: params.q || '', status: params.status || '' },
  })
  return data.tasks
}
