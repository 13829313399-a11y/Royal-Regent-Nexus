import { http } from '@/lib/http'

export interface CartonPriceReview {
  id: string; factory_id: string; receipt_line_id: string; shipment_id: string; shipment_line_id: string
  source_kind: 'REGULAR' | 'SPECIAL'; status: 'PENDING' | 'PROPOSED' | 'CONFIRMED'; revision: number
  original_unit_price: string | null; proposed_unit_price: string | null; effective_unit_price: string | null
  original_free_confirmed: boolean; currency: string; document_no: string; item_no: string
  packaging_type: string; specification: string; unit: string; quantity: string; receipt_status: string
  reason: string; locked: boolean; actionable: boolean
  history: { revision: number; status: string; reason: string; action: string; occurred_at: string; actor_user_id: string; proposed_unit_price?: string | null }[]
}
const base = '/carton-price-reviews'
export const cartonPriceReviewsApi = {
  async list(factory_id: string, supplier = false, shipment_id?: string, signal?: AbortSignal) {
    return (await http.get<{ items: CartonPriceReview[] }>(`${base}/${supplier ? 'supplier' : 'internal'}`, { params: { factory_id, shipment_id }, signal })).data.items
  },
  async propose(id: string, body: { factory_id: string; expected_revision: number; request_id: string; proposed_unit_price: string | null; free_confirmed: boolean; reason: string }) {
    return (await http.post<CartonPriceReview>(`${base}/internal/${encodeURIComponent(id)}/propose`, body)).data
  },
  async decide(id: string, body: { factory_id: string; expected_revision: number; request_id: string; decision: 'CONFIRM' | 'REJECT'; reason: string }) {
    return (await http.post<CartonPriceReview>(`${base}/supplier/${encodeURIComponent(id)}/decide`, body)).data
  },
}
