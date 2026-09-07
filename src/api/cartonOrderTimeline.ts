import { http } from '@/lib/http'

export interface OrderTimelineEvent {
  id: string
  occurred_at: string
  event_type: string
  event_label: string
  order_id: string | null
  customer_code: string
  customer_name: string
  contract_no: string
  item_no: string
  product_name: string
  document_no: string
  material_label: string
  quantity_change: string | null
  quantity_before: string | null
  quantity_after: string | null
  unit: string
  quantity_basis: 'ORDER_PRODUCT' | 'INVENTORY' | 'NONE'
  reason: string
  actor_name: string
  description: string
}
export const cartonOrderTimelineApi = {
  async get(factoryId: string, filters: { customer_code: string; date_from: string; date_to: string; search: string; order_id: string; inventory_key: string }) {
    const response = await http.get<{ events: OrderTimelineEvent[] }>('/carton-procurement/inventory/order-timeline', {
      params: { factory_id: factoryId, ...filters },
    })
    return response.data
  },
}
