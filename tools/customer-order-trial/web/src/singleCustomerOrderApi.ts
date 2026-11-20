import type { AxiosRequestConfig } from 'axios'
import { createCustomerOrderApi } from '../../../../src/api/customerOrder'
import { http } from './api'
export type { MappedCustomerCode } from '../../../../src/api/customerOrder'

// Keep the online page's multipart controls and download decoding unchanged.
export const customerOrderApi = createCustomerOrderApi({
  async post<T>(url: string, data?: unknown, config?: unknown) {
    const match = /^\/customer-orders\/(casdon|jakks|goliath|simba|spin|zuru)\/(preview|export)-batch$/.exec(url)
    const customer = match?.[1]
    const operation = match?.[2]
    const factory = data instanceof FormData ? String(data.get('factory_id') ?? '') : ''
    const allowedFactory = customer === 'zuru' ? ['huakang-a', 'huaxing'].includes(factory) : factory === 'huadeng'
    if (!operation || !(data instanceof FormData) || !allowedFactory) {
      throw new Error('本专客试用包仅开放指定厂区和客户。')
    }
    data.set('customer_code', customer!)
    const response = await http.post<T>(`/orders/${operation}`, data, config as AxiosRequestConfig)
    return { data: response.data, headers: response.headers }
  },
})
