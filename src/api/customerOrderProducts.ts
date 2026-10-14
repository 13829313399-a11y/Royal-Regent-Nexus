import { http } from '@/lib/http'
import type { OrderProductCatalog, OrderProductChange, OrderProductChoice } from '@/types/customerOrderProduct'
const base = '/customer-order-product-rules'
const scope = 'factory_id=huaxing&customer_code=dickie'
export const customerOrderProductsApi = {
  async catalog(signal?: AbortSignal) { return (await http.get<OrderProductCatalog>(`${base}?${scope}`, { signal })).data },
  async save(value: OrderProductChoice & { expected_revision: number; active: boolean }, signal?: AbortSignal) {
    return (await http.post<OrderProductCatalog>(`${base}?${scope}`, value, { signal, headers: { 'X-Order-Product-Rules': '1' } })).data
  },
  async history(product: string, signal?: AbortSignal) {
    return (await http.get<{ total: number; items: OrderProductChange[] }>(`${base}/history?${scope}&product_no=${encodeURIComponent(product)}`, { signal })).data
  },
}
