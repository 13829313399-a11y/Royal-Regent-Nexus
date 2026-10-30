import { http } from '@/lib/http'

export interface PrintFile { id: string; file_name: string; revision: number; sha256: string }
export interface PrintSplitInfo {
  print_changed?: boolean
  id: string; role: 'ORIGINAL' | 'CHILD'; status: string; source_order_no: string; source_contract_no: string
  targets: string[]; files: PrintFile[]
}
export interface PrintTarget {
  contract_no: string; customer_po: string; product_quantity: string | number | null; due_date: string
  asset_ids: string[]; files?: PrintFile[]; lines: { order_line_id: string; quantity: string | number }[]
}
export interface PrintPlan {
  print_changed?: boolean
  id: string; factory_id: string; order_id: string; order_no: string; contract_no: string; status: string
  revision: number; reason: string; response_reason: string; original_files: PrintFile[]; targets: PrintTarget[]
  members: { order_id: string; order_no: string; contract_no: string; role: string; files: PrintFile[] }[]
  papers?: { id: string; packaging_type: string; before_quantity: string; quantity: string; unit: string }[]
}
export interface PrintContext { inherited_original_files?: PrintFile[]; fixed_original_files?: PrintFile[]; revision: number; files: PrintFile[]; plans: PrintPlan[] }
export const printStatus: Record<string, string> = { DRAFT: '草稿 · 未发送', SENT: '待供应商确认', DISPUTED: '供应商有异议', WITHDRAWING: '撤回待供应商确认', ACTIVE: '已生效 · 分单执行', CANCELLED: '已撤销' }
export const cartonPrintSplitsApi = {
  async context(factory: string, number: string) {
    return (await http.get<PrintContext>(`/carton-procurement/orders/${encodeURIComponent(number)}/print-splits`, { params: { factory_id: factory } })).data
  },
  async create(factory: string, number: string, body: { request_id: string; expected_revision: number; reason: string; original_asset_ids: string[]; targets: PrintTarget[]; print_changed?: boolean; legacy_splits?: Record<string, number> }) {
    return (await http.post<PrintPlan>(`/carton-procurement/orders/${encodeURIComponent(number)}/print-splits`, { ...body, factory_id: factory })).data
  },
  async act(plan: PrintPlan, action: 'send' | 'withdraw', request_id: string, reason: string) {
    return (await http.post<PrintPlan>(`/carton-procurement/print-splits/${encodeURIComponent(plan.id)}/${action}`, { factory_id: plan.factory_id, expected_revision: plan.revision, request_id, reason })).data
  },
  async download(factory: string, plan: string, file: PrintFile, supplier = false) {
    const response = await http.get<Blob>(`/${supplier ? 'carton-supplier' : 'carton-procurement'}/print-splits/${encodeURIComponent(plan)}/files/${encodeURIComponent(file.id)}`, { params: { factory_id: factory }, responseType: 'blob' })
    const url = URL.createObjectURL(response.data), link = document.createElement('a')
    link.href = url; link.download = file.file_name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}
