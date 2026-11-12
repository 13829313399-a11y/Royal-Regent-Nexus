import axios from 'axios'
import { message } from 'antd'
import { getSessionGeneration, getStoredSession, saveSession, invalidateNexusSession } from '../auth/permissions'
import { beginNavigationWrite } from '../auth/navigationState'
import { apiBase, nexusBase } from '../deployment'

export const api = axios.create({ baseURL: apiBase(import.meta.env.BASE_URL) })

api.interceptors.request.use((config) => {
  if (nexusBase()) {
    const sessionRequest = config.url === '/session'
    if (!sessionRequest && !getStoredSession()) throw new axios.CanceledError('会话已失效，请重新进入工作区')
    ;(config as any).nexusGeneration = getSessionGeneration()
    if (!['get', 'head'].includes(config.method || 'get')) (config as any).finishNexusWrite = beginNavigationWrite()
    config.headers['X-Nexus-Shipping'] = '1'
    const identity = getStoredSession()?.identity
    if (identity) config.headers['X-Nexus-Shipping-Identity'] = identity
    return config
  }
  const token = getStoredSession()?.token
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (resp) => {
    ;(resp.config as any).finishNexusWrite?.()
    if (nexusBase() && resp.config.url !== '/session' && (resp.config as any).nexusGeneration !== getSessionGeneration())
      throw new axios.CanceledError('已忽略旧会话的响应')
    return resp
  },
  (error) => {
    error?.config?.finishNexusWrite?.()
    if (axios.isCancel(error)) return Promise.reject(error)
    if (nexusBase() && error?.config?.nexusGeneration !== getSessionGeneration()) return Promise.reject(new axios.CanceledError('已忽略旧会话的响应'))
    const data = error?.response?.data
    const status = error?.response?.status
    if (status === 401 && !String(error?.config?.url || '').includes('/auth/login')) {
      if (nexusBase()) invalidateNexusSession()
      else saveSession(null)
      if (nexusBase()) return Promise.reject(error)
      if (window.location.pathname !== `${import.meta.env.BASE_URL}login`) {
        window.location.href = `${import.meta.env.BASE_URL}login`
      }
    }
    if (nexusBase() && error?.response?.headers?.['x-nexus-shipping-session'] === 'invalid') invalidateNexusSession()
    if (nexusBase() && status === 403 && error?.config?.url !== '/session') window.dispatchEvent(new Event('nexus-shipping-recheck'))
    const text =
      (data && (data.error || data.message || data.detail)) ||
      (status === 403 ? '没有执行此操作的权限' : null) ||
      (status === 409 ? '数据已被他人修改，请刷新后重试' : null) ||
      error?.message || '网络错误'
    if (!(error?.config as any)?.skipErrorToast) {
      message.error({ key: 'api-error', content: '操作失败：' + text })
    }
    return Promise.reject(error)
  },
)

// Legacy-compat API entity shapes (snake_case, matches old Node backend exactly)

export interface Product {
  code: string
  name?: string
  hs_cn?: string
  hs_id?: string
  customer?: string
  updated_at?: string
  active_count?: number
  total_count?: number
  active?: boolean
}

export interface MoldingPart {
  category?: '塑胶' | '搪胶' | string
  partCode?: string
  partName?: string
  partNameEn?: string
  hsCN?: string
  hsID?: string
  ejections?: number
  usage?: number
  grossPerPc?: number
  netPerPc?: number
  image?: string
}
export interface Molding {
  moldId?: string
  moldName?: string
  materialName?: string
  colorCode?: string
  colorName?: string
  pigmentCode?: string
  netGramsPerShot?: number
  setsPerShot?: number
  workshop?: string
  notes?: string
  parts?: MoldingPart[]
}

export interface ProductDetail extends Product {
  moldings?: Molding[]
  materials?: Material[]
}

/** Read-only import evidence, stored only in a shipment's material snapshot. */
export interface ShipmentSourceCell {
  address: string
  label: string
  value: string | number | boolean | null
  display: string
  formula?: string
  error?: boolean
}
export interface ShipmentImportSource {
  file?: string
  sheet: string
  row: number
  cells: ShipmentSourceCell[]
  context: ShipmentSourceCell[]
}

export interface Material {
  // Local shipment snapshot only; keeps explicitly linked batches in one packing row.
  shipment_outbound_link_group?: string
  import_source?: ShipmentImportSource
  // A linked ordinary row converted to a local packing snapshot retains its
  // original product-HS fallback for absent codes; explicit empty codes do not.
  shipment_hs_product_fallback?: boolean
  department?: string
  id?: number
  tool_kind?: '工具' | '机器设备'
  related_product_code?: string
  revision?: number
  purchase_price?: number | null
  purchase_currency?: string | null
  product_code?: string
  item_no?: string
  name_zh?: string
  name_en?: string
  spec?: string
  category?: string
  material_code?: string
  hs_cn?: string
  hs_id?: string
  supplier?: string
  customs_company?: string
  unit_kg?: string
  gross_per_pc?: number
  net_per_pc?: number
  length?: number
  width?: number
  height?: number
  qty_per_carton?: number
  weight_per_carton?: number
  image_id?: string
  active?: boolean
  sort_order?: number
  image?: string
  usage_qty?: number   // 每个成品需要多少个该物料 (默认 1)
}

export interface HsDict      { keyword: string; hsCN?: string; hsID?: string }
export interface SupplierDict {
  id?: number
  keyword: string
  full?: string
  customs?: string
  nameEn?: string
  addressZh?: string
  addressEn?: string
  phone?: string
  email?: string
  contact?: string
}
export interface TranslationDict { keyword: string; english: string; active?: boolean; source?: string }
export interface Dictionaries { hs: HsDict[]; suppliers: SupplierDict[]; translations: TranslationDict[] }
