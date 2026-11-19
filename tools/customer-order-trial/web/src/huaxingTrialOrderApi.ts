import type { AxiosRequestConfig } from 'axios'
import { createCustomerOrderApi } from '../../../../src/api/customerOrder'
import { http } from './api'
export type { MappedCustomerCode } from '../../../../src/api/customerOrder'

// Keep the online page's multipart controls and download decoding unchanged.
export const customerOrderApi = createCustomerOrderApi({
  async post<T>(url: string, data?: unknown, config?: unknown) {
    const match = /^\/customer-orders\/(caixing|edu|dickie)\/(preview|export)-batch$/.exec(url)
    const operation = match?.[2]
    const customer = match?.[1]
    if (!operation || !customer || !(data instanceof FormData) || data.get('factory_id') !== 'huaxing') {
      throw new Error('本试用包仅开放华兴的彩星、EDU、Dickie。')
    }
    data.set('customer_code', customer)
    const response = await http.post<T>(`/orders/${operation}`, data, config as AxiosRequestConfig)
    return { data: response.data, headers: response.headers }
  },
})
