import { http } from '@/lib/http'
import { CUTTING_FACTORY } from './navigation'
import type { BomData, Command, MasterRecord } from './api'

export interface BomPreview {
  file_name: string
  file_sha256: string
  fingerprint: string | null
  issues: { sheet: string; row: number | null; message: string }[]
  candidate: {
    code: string
    existing_id: string | null
    expected_version: number
    data: BomData
    material_rows: (BomData['requirements'][number] & { row: number; material_code: string; material_name: string })[]
  } | null
}
export interface BomImportCommand extends Command {
  fingerprint: string
  file_sha256: string
  file_name: string
}
export interface BomImportResult { record: MasterRecord; file_name: string; file_sha256: string }

const base = '/cutting-operations/bom-import'
function upload(file: File, command?: BomImportCommand) {
  const body = new FormData()
  body.append('factory_id', CUTTING_FACTORY)
  body.append('bom_file', file)
  if (command) {
    for (const key of ['operation_id', 'expected_version', 'reason', 'fingerprint', 'file_sha256'] as const) {
      body.append(key, String(command[key]))
    }
  }
  return body
}
const options = { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 }
export const bomImportApi = {
  async template(): Promise<Blob> {
    return (await http.get(`${base}/template`, { params: { factory_id: CUTTING_FACTORY }, responseType: 'blob' })).data
  },
  async preview(file: File): Promise<BomPreview> {
    return (await http.post(`${base}/preview`, upload(file), options)).data
  },
  async confirm(file: File, command: BomImportCommand): Promise<BomImportResult> {
    return (await http.post(`${base}/confirm`, upload(file, command), options)).data
  },
  async recover(command: BomImportCommand): Promise<{state: 'committed'; result: BomImportResult} | {state: 'abandoned'}> {
    return (await http.post(`${base}/recover`, { command })).data
  },
}
