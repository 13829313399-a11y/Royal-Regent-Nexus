import { reactive } from 'vue'
import type { PurchaseScope } from '@/api/fabricProcurement'
import type { SaveMasterRequest, LocationManage, MasterRecord } from '@/api/fabricMaster'

// Keep unknown writes through a login redirect, isolated by submitting account.
// Files and drafts stay in this tab's memory; they are not persisted to storage.
export interface PendingFabricImport {
  file: File
  scope: PurchaseScope
  token: string
  requestId: string
  actorId: string | undefined
  inFlight: boolean
}
export interface PendingFabricMasterSave {
  body: SaveMasterRequest
  actorId: string | undefined
  inFlight: boolean
}
export const pendingFabricImports = reactive(new Map<string, PendingFabricImport>())
export const pendingFabricMasterSaves = reactive(new Map<string, PendingFabricMasterSave>())
export interface PendingFabricLocationManage {
  body: LocationManage
  records: MasterRecord[]
  actorId: string | undefined
  inFlight: boolean
}
export const pendingFabricLocationManage = reactive(new Map<string, PendingFabricLocationManage>())
