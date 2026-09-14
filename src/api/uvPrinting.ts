import { http } from '@/lib/http'
import type {
  CreateUvReport,
  Id,
  UvAssignment,
  UvAssignmentInput,
  UvCorrectionInput,
  UvDailyProjection,
  UvDailyReport,
  UvExpense,
  UvExpenseInput,
  UvExportInput,
  UvHandoverInput,
  UvHandoverRecord,
  UvInkBalance,
  UvInkIssueInput,
  UvInkMovement,
  UvInkPurchaseInput,
  UvInkSku,
  UvJobReconcileInput,
  UvMachine,
  UvMachineDetail,
  UvMachineSaveInput,
  UvMonthlyPolicy,
  UvMonthlyPolicyInput,
  UvMonthlyProjection,
  UvMutationResult,
  UvOperationRecord,
  UvPage,
  UvPayrollPreview,
  UvPricingAdoptInput,
  UvPricingInput,
  UvPricingQuote,
  UvPricingQuoteInput,
  UvPricingResult,
  UvPrintJob,
  UvProcessVersion,
  UvProcessVersionInput,
  UvProduct,
  UvProductSaveInput,
  UvQualityCommandInput,
  UvRateVersion,
  UvRateVersionInput,
  UvReport,
  UvReportCommandInput,
  UvResponse,
  UvReverseInput,
  UvScope,
  UvShiftTemplate,
  UvSummary,
  UvVoidInput,
  UvWorkerRef,
  UvWorkspaceTransport,
  UvReportExport,
} from '../features/uv-printing/contracts'

/**
 * 正式 UV API 客户端。
 *
 * - 复用宿主 `@/lib/http`（baseURL 通常是 `/api`），只写 `/uv-printing/...`，
 *   避免拼成 `/api/api/...`；
 * - 常规查询都传明确 `factory_id`，缺厂区由后端返回 422，前端不回落华康A；
 * - 组件不得绕过本文件直接拼接 HTTP。
 */

const BASE = '/uv-printing'

function assertLiveResponse<T>(response: UvResponse<T>): UvResponse<T> {
  if (response.meta.data_mode !== 'live' || response.meta.factory_id !== 'huakang-a') {
    throw Object.assign(new Error('UV 正式接口返回了非本厂 live 数据，已停止使用该响应。'), {
      code: 'uv_factory_mismatch', status: 502,
    })
  }
  return response
}

function scopeParams(scope: UvScope): Record<string, string | number> {
  const params: Record<string, string | number> = { factory_id: scope.factory_id }
  if (scope.business_date) params.business_date = scope.business_date
  if (scope.date_from) params.date_from = scope.date_from
  if (scope.date_to) params.date_to = scope.date_to
  if (scope.shift) params.shift = scope.shift
  if (scope.machine_id) params.machine_id = scope.machine_id
  if (scope.product_id) params.product_id = scope.product_id
  if (scope.status) params.status = scope.status
  if (scope.q) params.q = scope.q
  params.page = scope.page ?? 1
  params.page_size = scope.page_size ?? 50
  return params
}

async function get<T>(path: string, scope: UvScope, signal?: AbortSignal): Promise<UvResponse<T>> {
  return assertLiveResponse((await http.get<UvResponse<T>>(`${BASE}${path}`, { params: scopeParams(scope), signal })).data)
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<UvResponse<T>> {
  return assertLiveResponse((await http.post<UvResponse<T>>(`${BASE}${path}`, body, { signal })).data)
}

async function downloadExport(file: UvReportExport, kind: UvExportInput['kind']): Promise<void> {
  if (!file.download_url) throw new Error('正式导出未返回下载地址，未生成文件。')
  const downloadUrl = new URL(file.download_url, window.location.origin)
  const expectedPath = `/api/uv-printing/exports/${kind}`
  if (downloadUrl.origin !== window.location.origin || downloadUrl.pathname !== expectedPath) {
    throw new Error('正式导出返回了无效下载地址，已停止下载。')
  }
  // `http` 的 baseURL 是 `/api`，下载地址已是完整的同源 API 路径，不能再交给 Axios 拼接。
  const response = await fetch(`${downloadUrl.pathname}${downloadUrl.search}`, { credentials: 'include' })
  if (!response.ok) throw Object.assign(new Error(`导出下载失败（${response.status}）。`), { status: response.status })
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = file.file_name
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export const uvPrintingApi: UvWorkspaceTransport = {
  summary: (scope, signal) => get<UvSummary>('/summary', scope, signal),
  machines: (scope, signal) => get<UvPage<UvMachine>>('/machines', scope, signal),
  jobs: (scope, signal) => get<UvPage<UvPrintJob>>('/jobs', scope, signal),
  reports: (scope, signal) => get<UvPage<UvReport>>('/production-reports', scope, signal),
  createReport: (input: CreateUvReport) => post<UvMutationResult<UvReport>>('/production-reports', input),

  products: (scope, signal) => get<UvPage<UvProduct>>('/products', scope, signal),
  productDetail: async (productId: Id, signal) => assertLiveResponse((
    await http.get<UvResponse<UvProduct>>(`${BASE}/products/${productId}`, {
      params: { factory_id: 'huakang-a' },
      signal,
    })
  ).data),
  saveProduct: (input: UvProductSaveInput) => input.id
    ? post<UvMutationResult<UvProduct>>(`/products/${input.id}`, input)
    : post<UvMutationResult<UvProduct>>('/products', input),
  addProcessVersion: (input: UvProcessVersionInput) => post<UvMutationResult<UvProcessVersion>>(
    `/products/${input.product_id}/process-versions`,
    input,
  ),
  rateVersions: (scope, signal) => get<UvPage<UvRateVersion>>('/rate-versions', scope, signal),
  saveRateVersion: (input: UvRateVersionInput) => input.id
    ? post<UvMutationResult<UvRateVersion>>(`/rate-versions/${input.id}`, input)
    : post<UvMutationResult<UvRateVersion>>('/rate-versions', input),

  machineDetail: async (machineId, scope, signal) => assertLiveResponse((
    await http.get<UvResponse<UvMachineDetail>>(`${BASE}/machines/${machineId}`, {
      params: scopeParams(scope),
      signal,
    })
  ).data),
  saveMachine: (input: UvMachineSaveInput) => post<UvMutationResult<UvMachine>>(`/machines/${input.id}`, input),

  reconcileJob: (input: UvJobReconcileInput) => post<UvMutationResult<UvPrintJob>>(`/jobs/${input.job_id}/reconcile`, input),
  confirmReport: (input: UvReportCommandInput) => post<UvMutationResult<UvReport>>(
    `/production-reports/${input.report_id}/confirm`,
    input,
  ),
  updateQuality: (input: UvQualityCommandInput) => post<UvMutationResult<UvReport>>(
    `/production-reports/${input.report_id}/quality`,
    input,
  ),
  correctReport: (input: UvCorrectionInput) => post<UvMutationResult<UvReport>>(
    `/production-reports/${input.report_id}/corrections`,
    input,
  ),
  voidReport: (input: UvVoidInput) => post<UvMutationResult<UvReport>>(
    `/production-reports/${input.report_id}/void`,
    input,
  ),

  handovers: (scope, signal) => get<UvPage<UvHandoverRecord>>('/handovers', scope, signal),
  saveHandover: (input: UvHandoverInput) => input.id
    ? post<UvMutationResult<UvHandoverRecord>>(`/handovers/${input.id}`, input)
    : post<UvMutationResult<UvHandoverRecord>>('/handovers', input),

  inkSkus: (scope, signal) => get<UvPage<UvInkSku>>('/ink-skus', scope, signal),
  inkBalances: (scope, signal) => get<UvPage<UvInkBalance>>('/ink-balances', scope, signal),
  inkMovements: (scope, signal) => get<UvPage<UvInkMovement>>('/ink-movements', scope, signal),
  createInkIssue: (input: UvInkIssueInput) => post<UvMutationResult<UvInkMovement>>('/ink-movements', {
    ...input,
    kind: 'issue_out',
  }),
  createInkPurchase: (input: UvInkPurchaseInput) => post<UvMutationResult<UvInkMovement>>('/ink-movements', {
    ...input,
    kind: 'purchase_in',
  }),
  reverseInkMovement: (input: UvReverseInput) => post<UvMutationResult<UvInkMovement>>(
    `/ink-movements/${input.target_id}/reverse`,
    input,
  ),

  workers: (scope, signal) => get<UvPage<UvWorkerRef>>('/workers', scope, signal),
  shiftTemplates: (scope, signal) => get<UvPage<UvShiftTemplate>>('/shift-templates', scope, signal),
  assignments: (scope, signal) => get<UvPage<UvAssignment>>('/shift-assignments', scope, signal),
  saveAssignments: (input: UvAssignmentInput) => post<UvMutationResult<UvAssignment[]>>('/shift-assignments', input),
  payrollPreview: (scope, signal) => get<UvPayrollPreview>('/payroll/preview', scope, signal),

  expenses: (scope, signal) => get<UvPage<UvExpense>>('/expenses', scope, signal),
  createExpense: (input: UvExpenseInput) => post<UvMutationResult<UvExpense>>('/expenses', input),
  monthlyPolicy: async (month, scope, signal) => assertLiveResponse((
    await http.get<UvResponse<UvMonthlyPolicy | null>>(`${BASE}/monthly-policies/${month}`, {
      params: { factory_id: scope.factory_id },
      signal,
    })
  ).data),
  saveMonthlyPolicy: (input: UvMonthlyPolicyInput) => post<UvMutationResult<UvMonthlyPolicy>>(
    `/monthly-policies/${input.month}`,
    input,
  ),

  pricingPreview: (input: UvPricingInput) => post<UvPricingResult>('/pricing/preview', { ...input, factory_id: 'huakang-a' }),
  pricingQuotes: (scope, signal) => get<UvPage<UvPricingQuote>>('/pricing-quotes', scope, signal),
  savePricingQuote: (input: UvPricingQuoteInput) => post<UvMutationResult<UvPricingQuote>>('/pricing-quotes', input),
  adoptPricingQuote: (input: UvPricingAdoptInput) => post<UvMutationResult<UvRateVersion>>(
    `/pricing-quotes/${input.quote_id}/adopt`,
    input,
  ),

  dailyReport: (scope, signal) => get<UvDailyReport>('/reports/daily', scope, signal),
  dailyProjection: (scope, signal) => get<UvPage<UvDailyProjection>>('/reports/daily-projection', scope, signal),
  monthlyProjection: (scope, signal) => get<UvMonthlyProjection>('/reports/monthly', scope, signal),
  exportReport: async (input: UvExportInput) => {
    const result = await post<UvReportExport>(`/exports/${input.kind}`, input)
    await downloadExport(result.data, input.kind)
    return result
  },
  operationResult: async (operationId, scope) => assertLiveResponse((
    await http.get<UvResponse<UvOperationRecord | null>>(`${BASE}/operations/${operationId}`, {
      params: { factory_id: scope.factory_id },
    })
  ).data),
}
