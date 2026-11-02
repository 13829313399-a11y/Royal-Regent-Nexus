import { http } from '@/lib/http'
import type { CartonMarkAssetWorkflow } from '@/api/cartonMark'

export type AssetDepartment = 'sales-business' | 'pmc-warehouse' | 'carton' | 'supplier'
export type QuickAssetStatus = 'DRAFT' | 'PENDING' | 'READY' | 'HISTORY'
export type QuickTargetScope = 'ALL' | 'PENDING_SCHEDULE'
export interface QuickTarget {
  kind: 'REGULAR' | 'SCHEDULE' | 'SAMPLE' | 'MISC'
  id: string
  sheet: string
  row: number
  fingerprint: string
  contract_no: string
  customer_name?: string
  item_no?: string
  customer_po?: string
  customer_code?: string
  ordered?: boolean
}
export type QuickTargetRef = Pick<QuickTarget, 'kind' | 'id' | 'sheet' | 'row' | 'fingerprint'>
export interface QuickAsset {
  can_classify?: boolean
  allowed_statuses?: QuickAssetStatus[]
  can_associate?: boolean
  view_factory_id?: string
  shared_factory_ids?: string[]
  created_by_name?: string
  created_at?: string
  id: string
  factory_id: string
  owner_department: AssetDepartment
  owner_supplier_id?: string | null
  purpose: 'MATERIAL' | 'EVIDENCE'
  kind: 'excel' | 'pdf' | 'image' | 'text'
  file_name: string
  content_type: string
  sha256: string
  revision: number
  contract_number: string
  text: string | null
  workflow: CartonMarkAssetWorkflow
  targets: (Omit<QuickTarget, 'fingerprint'> & { fingerprint?: string })[]
  warning: string
}
export interface QuickUploadBody {
  request_id: string
  owner_department: AssetDepartment
  text: string
  contract_number: string
  association: 'AUTO' | 'MANUAL' | 'NONE'
  target_scope?: QuickTargetScope
  target?: QuickTargetRef
  targets?: QuickTargetRef[]
  shared_factory_ids?: string[]
  status: QuickAssetStatus
}
const BASE = '/carton-mark/assets/quick'
function scoped(asset: QuickAsset, factory: string) {
  if (!asset.id || (asset.view_factory_id || asset.factory_id) !== factory) throw new Error('资料范围与当前厂区不一致，请重新读取。')
  return asset
}
export function createCartonQuickAssetsApi(client = http) {
  return {
    async list(factory: string, department: AssetDepartment, signal?: AbortSignal) {
      const { data } = await client.get<{ items: QuickAsset[]; total: number }>(BASE, {
        params: { factory_id: factory, owner_department: department }, signal,
      })
      for (const asset of data.items) {
        scoped(asset, factory)
      }
      return data
    },
    async candidates(factory: string, department: AssetDepartment, contract: string, signal?: AbortSignal, scope: QuickTargetScope = 'ALL', assetId?: string) {
      return (await client.get<{ items: QuickTarget[]; total: number }>(BASE + '/candidates', {
        params: { factory_id: factory, owner_department: department, contract_number: contract, target_scope: scope, asset_id: assetId }, signal,
      })).data.items
    },
    async upload(factory: string, body: QuickUploadBody, file?: File, signal?: AbortSignal) {
      const form = new FormData()
      form.set('metadata', JSON.stringify(body))
      if (file) form.set('file', file)
      const { data } = await client.post<QuickAsset>(BASE, form, {
        params: { factory_id: factory }, headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000, signal,
      })
      scoped(data, factory)
      if (data.owner_department !== body.owner_department || data.purpose !== 'MATERIAL') throw new Error('保存结果归属不一致，请原样重试核实。')
      return data
    },
    async confirm(factory: string, asset: Pick<QuickAsset, 'id' | 'revision'>, requestId: string, signal?: AbortSignal) {
      const { data } = await client.post<QuickAsset>(BASE + '/' + encodeURIComponent(asset.id) + '/classification', {
        revision: asset.revision, request_id: requestId, status: 'READY',
      }, { params: { factory_id: factory }, signal })
      scoped(data, factory)
      if (data.id !== asset.id) throw new Error('保存结果与当前资料不一致，请原样重试核实。')
      return data
    },
    async classify(factory: string, asset: Pick<QuickAsset, 'id' | 'revision'>, status: QuickAssetStatus, requestId: string, signal?: AbortSignal) {
      const { data } = await client.post<QuickAsset>(BASE + '/' + encodeURIComponent(asset.id) + '/classification', {
        revision: asset.revision, request_id: requestId, status,
      }, { params: { factory_id: factory }, signal })
      scoped(data, factory)
      if (data.id !== asset.id) throw new Error('保存结果与当前资料不一致，请原样重试核实。')
      return data
    },
    async associate(factory: string, asset: Pick<QuickAsset, 'id' | 'revision'>, targets: QuickTargetRef[], requestId: string, signal?: AbortSignal, scope: QuickTargetScope = 'ALL') {
      const { data } = await client.post<QuickAsset>(BASE + '/' + encodeURIComponent(asset.id) + '/associations', {
        revision: asset.revision, request_id: requestId, targets, target_scope: scope,
      }, { params: { factory_id: factory }, signal })
      return scoped(data, factory)
    },
    async share(factory: string, asset: Pick<QuickAsset, 'id' | 'revision'>, factories: string[], requestId: string, signal?: AbortSignal) {
      const { data } = await client.post<QuickAsset>(BASE + '/' + encodeURIComponent(asset.id) + '/sharing', {
        revision: asset.revision, request_id: requestId, shared_factory_ids: factories,
      }, { params: { factory_id: factory }, signal })
      return scoped(data, factory)
    },
    async document(factory: string, identifier: string, supplier: boolean, signal?: AbortSignal) {
      return (await client.get<Blob>(BASE + '/' + encodeURIComponent(identifier) + '/document', {
        params: { factory_id: factory, supplier_view: supplier }, responseType: 'blob', signal,
      })).data
    },
  }
}
export const cartonQuickAssetsApi = createCartonQuickAssetsApi()
