import type { AxiosRequestConfig } from 'axios'
import { createCustomerOrderApi } from '../../../../src/api/customerOrder'
import { http } from './api'
export type { MappedCustomerCode } from '../../../../src/api/customerOrder'

// Keep the online page's multipart controls and download decoding unchanged.
export const customerOrderApi = createCustomerOrderApi({
  async post<T>(url: string, data?: unknown, config?: unknown) {
    const operation = /^\/customer-orders\/green-toys\/(preview|export)-batch$/.exec(url)?.[1]
    if (!operation || !(data instanceof FormData) || data.get('factory_id') !== 'huakang-a') {
      throw new Error('本试用包仅开放华康A Green Toys订单入排期。')
    }
    data.set('customer_code', 'green-toys')
    const response = await http.post<T>(`/orders/${operation}`, data, config as AxiosRequestConfig)
    return { data: response.data, headers: response.headers }
  },
})
