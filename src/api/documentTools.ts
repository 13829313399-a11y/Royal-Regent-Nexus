import { http } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'

export type Operation =
  | 'word_to_pdf'
  | 'pdf_to_word'
  | 'word_to_excel'
  | 'excel_to_word'
  | 'pdf_to_excel'
  | 'excel_to_pdf'
  | 'pdf_split'
export interface Anchor {
  method?: string
  page_index?: number | null
  bbox_pt?: number[] | null
  sheet?: string | null
  cell?: string | null
  block_id?: string | null
  anchor_precision?: string
}
export interface DocumentPage {
  page_index: number
  display_page_number: number
  width_pt: number
  height_pt: number
  rotation: number
  classification?: string
}
export interface Artifact {
  id: string
  role: string
  format: string
  filename: string
  size: number
  revision: number
  expires_at?: string | number | null
}
export interface Issue {
  id: string
  code: string
  message: string
  severity: string
  target_id?: string
  source: Anchor
  candidates: string[]
  status: string
  action: string
}
export interface Cell {
  id: string
  row: number
  column: number
  rowspan: number
  colspan: number
  raw_text: string
  display_text: string
  resolution: string
  source: Anchor
}
export interface Table {
  id: string
  title: string
  row_count: number
  column_count: number
  cells: Cell[]
  source: Anchor
}
export interface Block {
  id: string
  kind: string
  text: string
  source: Anchor
}
export interface Result {
  schema_version: number
  source_type: string
  pages: DocumentPage[]
  tables: Table[]
  blocks: Block[]
  issues: Issue[]
  total_cells: number
  total_blocks?: number
  offset: number
  limit: number
}
export interface Job {
  id: string
  source_id: string
  source_name: string
  operation: string
  execution_status: string
  quality_status: string
  stage: string
  completed_units: number
  total_units: number | null
  revision: number
  options: Record<string, unknown>
  summary: Record<string, unknown>
  error_code?: string
  error_message?: string
  created_at: string
  finished_at?: string
  cancel_requested: boolean
  artifacts: Artifact[]
}
export interface Source {
  id: string
  original_name: string
  detected_type: string
  inspection_status: string
  inspection_job_id: string
  manifest: {
    pages?: DocumentPage[]
    sheets?: Array<string | { name: string; hidden?: boolean }>
    issues?: Issue[]
    supported_operations?: string[]
  }
  artifacts: Artifact[]
}
export interface Capabilities {
  engines?: Record<
    string,
    { configured: boolean; tested: boolean; status?: string; model?: string }
  >
  operations: Array<{
    id: Operation
    label: string
    available: boolean
    reason?: string
  }>
  worker: { online: boolean }
  limits: { max_file_bytes: number; max_pages: number }
}
export interface PageList<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
const root = '/tools'
export const documentTools = {
  capabilities: async () =>
    (await http.get<Capabilities>(`${root}/capabilities`)).data,
  upload: async (file: File, progress: (percent: number) => void) => {
    const data = new FormData()
    data.append('file', file)
    return (
      await http.post<{ source_id: string; inspection_job_id: string }>(
        `${root}/uploads`,
        data,
        {
          headers: { 'Content-Type': undefined },
          timeout: 120000,
          onUploadProgress: (event) => {
            if (event.total)
              progress(Math.round((event.loaded / event.total) * 100))
          },
        },
      )
    ).data
  },
  source: async (id: string) =>
    (await http.get<Source>(`${root}/sources/${id}`)).data,
  password: async (id: string, password: string) =>
    (
      await http.post<{ job_id: string }>(`${root}/sources/${id}/password`, {
        password,
      })
    ).data,
  create: async (
    source_id: string,
    operation: Operation,
    options: Record<string, unknown>,
    batch_id?: string,
  ) =>
    (
      await http.post<{ job_id: string }>(`${root}/jobs`, {
        source_id,
        operation,
        options,
        client_request_id: createRandomUuid(),
        batch_id,
      })
    ).data,
  jobs: async (page = 1) =>
    (
      await http.get<PageList<Job>>(`${root}/jobs`, {
        params: { page, page_size: 20 },
      })
    ).data,
  job: async (id: string) => (await http.get<Job>(`${root}/jobs/${id}`)).data,
  issues: async (id: string, page = 1) =>
    (
      await http.get<PageList<Issue>>(`${root}/jobs/${id}/issues`, {
        params: { page, page_size: 25 },
      })
    ).data,
  result: async (
    id: string,
    table_id?: string,
    offset = 0,
    target_id?: string,
  ) =>
    (
      await http.get<Result>(`${root}/jobs/${id}/result`, {
        params: { table_id, offset, limit: 200, target_id },
      })
    ).data,
  cancel: async (id: string) =>
    (await http.post<Job>(`${root}/jobs/${id}/cancel`)).data,
  delete: async (id: string) => {
    await http.delete(`${root}/jobs/${id}`)
  },
  retry: async (id: string) =>
    (await http.post<{ job_id: string }>(`${root}/jobs/${id}/retry`)).data,
  revise: async (
    id: string,
    payload: {
      base_revision: number
      corrections: Array<{
        target_id: string
        new_value: string
        reason: string
      }>
      region?: { page_index: number; bbox_pt: number[] }
    },
  ) =>
    (await http.post<{ job_id: string }>(`${root}/jobs/${id}/revise`, payload))
      .data,
  package: async (artifact_ids: string[]) =>
    (
      await http.post<{ job_id: string }>(`${root}/packages`, {
        artifact_ids,
        client_request_id: createRandomUuid(),
      })
    ).data,
  suggestions: async (id: string, page_index: number, axis: string) =>
    (
      await http.get<{
        cuts_pt: number[]
        protected_regions: Array<{ kind: string; bbox_pt: number[] }>
      }>(`${root}/sources/${id}/split-suggestions`, {
        params: { page_index, axis },
      })
    ).data,
  artifactUrl: (id: string, download = false) =>
    `${http.defaults.baseURL}${root}/artifacts/${encodeURIComponent(id)}/${download ? 'download' : 'content'}`,
}

export const operationLabels: Record<Operation, string> = {
  word_to_pdf: 'Word → PDF',
  pdf_to_word: 'PDF → Word',
  word_to_excel: 'Word → Excel',
  excel_to_word: 'Excel → Word',
  pdf_to_excel: 'PDF → Excel',
  excel_to_pdf: 'Excel → PDF',
  pdf_split: 'PDF 精确分页',
}
export const statusLabels: Record<string, string> = {
  queued: '等待处理',
  running: '处理中',
  awaiting_input: '需要密码',
  succeeded: '已生成',
  failed: '处理失败',
  cancelled: '已撤回',
  not_checked: '未检查',
  checking: '正在核验',
  passed: '已执行检查通过',
  needs_review: '建议核验',
  manually_confirmed: '已人工确认',
  inspect: '检查文档',
  extract: '提取结构',
  recognize: '识别内容',
  rebuild: '生成文档',
  validate: '核对内容',
  package: '打包文件',
}
export const isActiveJob = (job: Job) =>
  ['queued', 'running'].includes(job.execution_status)
