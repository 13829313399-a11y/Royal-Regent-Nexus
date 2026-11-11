import { nexusBase } from '../deployment'

export type ModuleKey = 'products' | 'customers' | 'schedules' | 'purchase' | 'quotes' | 'molding' | 'outbound' | 'shipments'

export interface PermissionModule {
  key: ModuleKey
  name: string
  path: string
  positions: number[]
}

export const PERMISSION_MODULES: PermissionModule[] = [
  { key: 'customers', name: '客户管理', path: '/customers', positions: [2] },
  { key: 'products', name: '货号库（含物料、字典）', path: '/products', positions: [0, 1] },
  { key: 'quotes', name: '报价', path: '/quotes', positions: [5] },
  { key: 'purchase', name: '采购订单', path: '/purchase', positions: [4] },
  { key: 'molding', name: '生产单', path: '/molding-pos', positions: [6] },
  { key: 'schedules', name: '排期', path: '/schedules', positions: [3] },
  { key: 'outbound', name: '出库', path: '/outbound', positions: [7] },
  { key: 'shipments', name: '走货明细', path: '/shipments', positions: [8] },
]

export interface AuthSession {
  nexus?: boolean
  identity?: string
  factoryId?: string
  serverNow?: string
  nextTransitionAt?: string
  databaseManage?: boolean
  token: string
  displayName: string
  userbqrpower: string
  usereditpower: string
}

const STORAGE_KEY = 'indo_auth'
let nexusSession: AuthSession | null = null
let nexusSessionLocked = false
let sessionGeneration = 0
const sessionListeners = new Set<(session: AuthSession | null) => void>()
export const getSessionGeneration = () => sessionGeneration
export const isNexusSessionLocked = () => nexusSessionLocked
export function invalidateNexusSession() {
  nexusSessionLocked = true
  saveSession(null)
}
export function sessionFingerprint(v: AuthSession | null) {
  return JSON.stringify(v ? [v.identity, v.factoryId, v.userbqrpower, v.usereditpower, !!v.databaseManage] : null)
}
export function subscribeSession(listener: (session: AuthSession | null) => void) {
  sessionListeners.add(listener)
  return () => { sessionListeners.delete(listener) }
}

export function getStoredSession(): AuthSession | null {
  if (nexusBase()) return nexusSession
  try {
    const v = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
    return v?.token ? v as AuthSession : null
  } catch { return null }
}

export function saveSession(v: AuthSession | null) {
  if (nexusBase()) {
    if (v && nexusSessionLocked) return
    if (sessionFingerprint(nexusSession) !== sessionFingerprint(v)) sessionGeneration++
    nexusSession = v
    sessionListeners.forEach(listener => listener(v))
    return
  }
  if (v) localStorage.setItem(STORAGE_KEY, JSON.stringify(v))
  else localStorage.removeItem(STORAGE_KEY)
}

export function hasBits(bits: string | undefined, positions: number[]) {
  return positions.every(p => bits?.[p] === '1')
}

export function isAdminSession(v: AuthSession | null) {
  if (v?.nexus || nexusBase()) return false
  return v?.userbqrpower === '111111111' && v?.usereditpower === '111111111'
}

export function canManageLegacyUsers(v: AuthSession | null) {
  return !v?.nexus && isAdminSession(v)
}

export function canManageLegacyDatabase(v: AuthSession | null) {
  return !v?.nexus && isAdminSession(v)
}

export function moduleForPath(pathname: string) {
  if (pathname.startsWith('/tool-materials')) return PERMISSION_MODULES.find(x => x.key === 'products')
  if (pathname.startsWith('/supplier-summary')) return PERMISSION_MODULES.find(x => x.key === 'products')
  if (pathname.startsWith('/dictionaries')) return PERMISSION_MODULES.find(x => x.key === 'products')
  if (pathname.startsWith('/material-alerts')) return PERMISSION_MODULES.find(x => x.key === 'purchase')
  return PERMISSION_MODULES.find(x => pathname.startsWith(x.path))
}
