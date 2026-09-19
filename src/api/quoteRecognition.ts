import { http } from '@/lib/http'
import type { RecognitionResponse, RecognitionTask } from '@/lib/customerPriceConverters/yinhuiRecognition'

export async function getQuoteRecognitionStatus(signal?: AbortSignal) {
  const response = await http.get<{ available: boolean; message: string }>('/pricing/yinhui-recognition/status', { params: { factory_id: 'huaxing' }, signal })
  return response.data
}
export async function recognizeQuoteFields(tasks: RecognitionTask[], signal?: AbortSignal) {
  const response = await http.post<RecognitionResponse>('/pricing/yinhui-recognition', { factory_id: 'huaxing', customer_id: 'yinhui', tasks }, { signal, timeout: 310000 })
  return response.data
}
