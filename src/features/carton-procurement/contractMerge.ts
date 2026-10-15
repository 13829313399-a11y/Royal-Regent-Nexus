import { http } from '@/lib/http'
import type { CartonOrderResponse } from '@/api/cartonProcurement'

export interface ContractMergeRequest {
  factory_id: string
  request_id: string
  contract_no: string
  expected_revisions: Record<string, number>
  reason: string
}
export async function mergeOrderContract(payload: ContractMergeRequest) {
  return (await http.post<CartonOrderResponse[]>('/carton-procurement/orders/merge-contract', payload)).data
}
export function mergeStorageKey(user: string, epoch: number, factory: string) {
  return `carton-contract-merge:v1:${encodeURIComponent(user)}:${epoch}:${encodeURIComponent(factory)}`
}
