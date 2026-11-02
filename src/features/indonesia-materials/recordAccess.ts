import type { MaterialRecord } from '@/api/indonesiaMaterials'
import type { MaterialsWorkspace } from './workspace'

export function lostRecordAccess(ws: Pick<MaterialsWorkspace, 'record'>, row?: MaterialRecord | null) {
  return !!row?.responsibility && !ws.record(row.id)
}
