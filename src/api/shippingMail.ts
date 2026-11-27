import { http } from '../lib/http.js'

export interface ShippingMailLine {
  product_code?: string
  product_name?: string
  customer_po?: string
  quantity?: number | null
  cartons?: number | null
  cbm?: number | null
  gross_weight?: number | null
  net_weight?: number | null
  source_file?: string
}

export interface ShippingAttachment {
  filename: string
  kind?: string
  status?: string
  warnings?: string[]
}

export interface ShippingMailPreview {
  filename: string
  subject?: string
  sender?: string
  received_at?: string
  fields: Record<string, unknown>
  items: ShippingMailLine[]
  attachments: ShippingAttachment[]
  warnings: string[]
  rule_trace?: unknown[]
  parser_version?: string
  status?: string
}

export interface ShippingMailBatch {
  id: string
  file_name?: string
  filename?: string
  subject?: string
  sender?: string
  status: string
  total_count: number
  parsed_count: number
  failed_count: number
  created_at: string
}

export interface ShippingMailBatchItem {
  id: string
  filename: string
  status: string
  subject?: string
  fields?: Record<string, unknown>
  items?: ShippingMailLine[]
  warnings?: string[]
  task_ids?: string[]
}

export interface ShippingMailConfirmResult {
  batch: ShippingMailBatch
  tasks: Array<Record<string, unknown>>
}

export async function previewShippingMail(factoryId: string, file: File): Promise<ShippingMailPreview> {
  const form = new FormData()
  form.append('factory_id', factoryId)
  form.append('file', file)
  const { data } = await http.post<ShippingMailPreview>('/shipping/mail/preview', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return data
}

export async function createShippingMailBatch(factoryId: string, files: File[]) {
  const form = new FormData()
  form.append('factory_id', factoryId)
  for (const file of files) form.append('files', file)
  const { data } = await http.post<{ batch: ShippingMailBatch; items: ShippingMailBatchItem[] }>(
    '/shipping/mail/batches',
    form,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000 },
  )
  return data
}

export async function deleteShippingMailBatch(factoryId: string, batchId: string) {
  const { data } = await http.delete<{ deleted: boolean; items: number }>(`/shipping/mail/batches/${batchId}`, {
    params: { factory_id: factoryId },
  })
  return data
}

export async function getShippingMailBatch(factoryId: string, batchId: string) {
  const { data } = await http.get<{ batch: ShippingMailBatch; items: ShippingMailBatchItem[] }>(
    `/shipping/mail/batches/${batchId}`,
    { params: { factory_id: factoryId } },
  )
  return data
}

export interface LoadingSheetRecord {
  id: string
  number: string
  sheetDate: string
  filename: string
  filingCodes?: string[]
  variant?: string
  task_id?: string
  soNo: string
  contractNo: string
  transportCompany: string
  originPort: string
  createdAt: string
  totals: Record<string, number>
}

export interface LoadingSheetDetail extends LoadingSheetRecord {
  header: LoadingHeader
  lines: LoadingLine[]
}

export async function listLoadingSheets(factoryId: string, variant?: 'dk' | 'hq') {
  const { data } = await http.get<{ sheets: LoadingSheetRecord[] }>('/shipping/loading-sheets', {
    params: { factory_id: factoryId, variant: variant || '' },
  })
  return data.sheets
}

export async function getLoadingSheet(factoryId: string, sheetId: string) {
  const { data } = await http.get<LoadingSheetDetail>(`/shipping/loading-sheets/${sheetId}`, {
    params: { factory_id: factoryId },
  })
  return data
}

export interface WorkbookPreviewBorder {
  t?: string
  r?: string
  b?: string
  l?: string
}

export interface WorkbookPreviewCell {
  v: string
  rs?: number
  cs?: number
  skip?: boolean
  bg?: string
  color?: string
  bold?: boolean
  italic?: boolean
  underline?: boolean
  fontSize?: number
  fontFamily?: string
  align?: 'left' | 'center' | 'right'
  valign?: 'top' | 'middle' | 'bottom'
  wrap?: boolean
  border?: WorkbookPreviewBorder
}

export interface WorkbookPreviewSheet {
  name: string
  rows: string[][]
  colWidths?: number[]
  rowHeights?: Array<number | null>
  cells?: WorkbookPreviewCell[][]
}

export async function updateLoadingSheetHeader(
  factoryId: string,
  sheetId: string,
  header: Partial<Pick<LoadingHeader, 'contractNo' | 'soNo' | 'vessel' | 'voyage' | 'plate' | 'containerNo' | 'sealNo' | 'tareWeight'>>,
) {
  const { data } = await http.patch<{ updated: boolean; filename: string; path: string }>(
    `/shipping/loading-sheets/${sheetId}/header`, header, { params: { factory_id: factoryId } },
  )
  return data
}

export async function openLoadingSheet(factoryId: string, sheetId: string) {
  const { data } = await http.post<{ opened?: boolean; path: string; filename: string; sheets?: WorkbookPreviewSheet[] }>(`/shipping/loading-sheets/${sheetId}/open`, null, {
    params: { factory_id: factoryId },
  })
  return data
}

export async function downloadLoadingSheet(factoryId: string, sheetId: string) {
  const { data } = await http.get(`/shipping/loading-sheets/${sheetId}/download`, {
    params: { factory_id: factoryId },
    responseType: 'blob',
    timeout: 120_000,
  })
  return data as Blob
}

export async function deleteLoadingSheet(factoryId: string, sheetId: string) {
  const { data } = await http.delete<{ deleted: boolean }>(`/shipping/loading-sheets/${sheetId}`, {
    params: { factory_id: factoryId },
  })
  return data
}

export async function confirmShippingMailBatch(
  batchId: string,
  factoryId: string,
  itemIds: string[],
  fields: Record<string, string> = {},
  modules?: string[],
) {
  const { data } = await http.post<ShippingMailConfirmResult>(
    `/shipping/mail/batches/${batchId}/confirm`,
    { factory_id: factoryId, item_ids: itemIds, fields, ...(modules?.length ? { modules } : {}) },
    { timeout: 120_000 },
  )
  return data
}

export async function listShippingMailBatches(factoryId: string) {
  const { data } = await http.get<{ batches: ShippingMailBatch[] }>('/shipping/mail/batches', {
    params: { factory_id: factoryId },
  })
  return data.batches
}

export interface ShippingMailAccount {
  configured: boolean
  factory_id: string
  host: string
  port: number
  username: string
  use_ssl: boolean
  folder: string
  enabled: boolean
  has_password: boolean
  last_sync_at: string
  last_status: string
  last_error: string
}

export interface ShippingMailSyncRun {
  id: string
  factory_id: string
  trigger: string
  status: string
  fetched: number
  imported: number
  confirmed: number
  failed: number
  message: string
  started_at: string
  finished_at: string
}

export async function getShippingMailAccount(factoryId: string) {
  const { data } = await http.get<{ account: ShippingMailAccount }>('/shipping/mail/account', {
    params: { factory_id: factoryId },
  })
  return data.account
}

export async function saveShippingMailAccount(payload: {
  factory_id: string
  host: string
  port: number
  username: string
  password: string
  use_ssl: boolean
  folder: string
  enabled: boolean
}) {
  const { data } = await http.put<{ account: ShippingMailAccount }>('/shipping/mail/account', payload)
  return data.account
}

export async function testShippingMailAccount(factoryId: string, password = '') {
  const { data } = await http.post<{ ok: boolean; message: string }>('/shipping/mail/account/test', {
    factory_id: factoryId,
    password,
  })
  return data
}

export async function syncShippingMailAccount(
  factoryId: string,
  options: { sinceDays?: number; limit?: number; includeSynced?: boolean } = {},
) {
  const { data } = await http.post<{ run: ShippingMailSyncRun }>('/shipping/mail/account/sync', {
    factory_id: factoryId,
    since_days: options.sinceDays ?? 8,
    limit: options.limit ?? 50,
    include_synced: options.includeSynced ?? false,
  }, {
    timeout: 300_000,
  })
  return data.run
}

export async function listShippingMailRuns(factoryId: string) {
  const { data } = await http.get<{ runs: ShippingMailSyncRun[] }>('/shipping/mail/account/runs', {
    params: { factory_id: factoryId },
  })
  return data.runs
}

export interface LoadingLine {
  id: string
  tradingCompany: string
  contract: string
  filingCode: string
  declareCode: string
  coefficient?: number | null
  quantity: number | null
  cartons: number | null
  grossWeight: number | null
  netWeight: number | null
  cbm: number | null
  category: string
  grossPerCarton: number | null
  netPerCarton: number | null
  description: string
  department: string
  pallet?: number | null
  cartonMark?: string
}

export interface LoadingHeader {
  shipper: string
  consignee: string
  tradingCompany: string
  soNo: string
  contractNo?: string
  filingCode?: string
  vessel: string
  voyage: string
  containerType: string
  cutoff: string
  sheetDate: string
  preparer: string
  brandNote: string
  poNo?: string
  originPort: string
  transportCompany: string
  tableName?: string
  number: string
  plate: string
  containerNo: string
  sealNo: string
  tareWeight: string
  destinationCountry: string
  bookingDate: string
  bookingNo?: string
  tradeTerm?: string
  shippingClerk?: string
  truckHead?: string
  cartonMark?: string
  photoNote: string
  department: string
}

export interface LoadingDraft {
  number: string
  header: LoadingHeader
  lines: LoadingLine[]
  totals: Record<string, number>
  taskId: string
}

export interface ProductSearchItem {
  product_code: string
  product_name?: string
  quantity?: number | null
  cartons?: number | null
  coefficient?: number | null
  gross_weight?: number | null
  net_weight?: number | null
  cbm?: number | null
  contract_no?: string
  customer_po?: string
  country?: string
  consignee?: string
  so_number?: string
  brand?: string
  customer?: string
  source?: string
}

export async function searchScheduleProducts(factoryId: string, q: string) {
  const { data } = await http.get<{ items: ProductSearchItem[] }>('/shipping/loading-sheets/product-search', {
    params: { factory_id: factoryId, q },
  })
  return data.items
}

export async function lookupScheduleLines(factoryId: string, q: string) {
  const { data } = await http.get<{ lines: Array<Record<string, unknown>> }>('/shipping/loading-sheets/schedule-lines', {
    params: { factory_id: factoryId, q },
  })
  return data.lines
}

export async function draftLoadingSheet(factoryId: string, taskId: string): Promise<LoadingDraft> {
  const { data } = await http.post<LoadingDraft>('/shipping/loading-sheets/draft', {
    factory_id: factoryId,
    task_id: taskId,
  })
  return data
}

export async function exportLoadingSheet(factoryId: string, draft: LoadingDraft, variant: 'dk' | 'hq' = 'dk'): Promise<Blob> {
  const { data } = await http.post('/shipping/loading-sheets/export', {
    factory_id: factoryId,
    taskId: draft.taskId,
    header: draft.header,
    lines: draft.lines,
    variant,
  }, { responseType: 'blob', timeout: 120_000 })
  return data as Blob
}

export interface ZuruLine {
  id: string
  tradingHouse: string
  contract: string
  filingCode: string
  declareCode: string
  brand: string
  coefficient?: number | null
  quantity: number | null
  cartons: number | null
  grossWeight: number | null
  netWeight: number | null
  cbm: number | null
  cbmPerCarton?: number | null
  country: string
  grossPerCarton: number | null
  netPerCarton: number | null
  remark: string
  po: string
}

export interface ZuruHeader {
  toNames: string[]
  fromName: string
  sheetDate: string
  cutoff: string
  number: string
  soNo: string
  vesselVoyage: string
  blNo: string
  transportCompany: string
  containerType: string
  tradeTerm: string
  plate: string
  containerNo: string
  sealNo: string
  tareWeight: string
  originPort: string
  destinationCountry: string
}

export interface ZuruDraft {
  taskId: string
  header: ZuruHeader
  lines: ZuruLine[]
  totals: Record<string, number>
}

export async function draftZuruSheet(factoryId: string, taskId: string): Promise<ZuruDraft> {
  const { data } = await http.post<ZuruDraft>('/shipping/loading-sheets/zuru/draft', {
    factory_id: factoryId,
    task_id: taskId,
  })
  return data
}

export async function exportZuruSheet(factoryId: string, draft: ZuruDraft): Promise<Blob> {
  const { data } = await http.post('/shipping/loading-sheets/zuru/export', {
    factory_id: factoryId,
    taskId: draft.taskId,
    header: draft.header,
    lines: draft.lines,
  }, { responseType: 'blob', timeout: 120_000 })
  return data as Blob
}

export interface ProductHistoryRecord {
  id: string
  product_code: string
  product_name: string
  category: string
  gross_per_carton: string
  net_per_carton: string
  customer: string
  source: string
  updated_at: string
}

export async function importProductHistory(factoryId: string, customer: string, files: File[]) {
  const form = new FormData()
  form.append('factory_id', factoryId)
  form.append('customer', customer)
  for (const file of files) form.append('files', file)
  const { data } = await http.post<{
    created: number
    updated: number
    total: number
    records: ProductHistoryRecord[]
  }>('/shipping/product-history/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return data
}

export async function listProductHistory(factoryId: string, customer = '') {
  const { data } = await http.get<{ records: ProductHistoryRecord[] }>('/shipping/product-history', {
    params: { factory_id: factoryId, customer },
  })
  return data.records
}

export interface TruckLine {
  id: string
  department: string
  tradingHouse: string
  contract: string
  filingCode: string
  declareCode: string
  name: string
  country: string
  category: string
  quantity: number | null
  coefficient: number | null
  pieces: number | null
  grossWeight: number | null
  netWeight: number | null
  cbm: number | null
  cartonMark: string
  totalCartons: string
  grossPerCarton: number | null
  netPerCarton: number | null
  remark: string
}

export interface TruckHeader {
  shipper: string
  consignee: string
  reference: string
  toName: string
  vehicle: string
  cfs: string
  tradeTerm: string
  cc: string
  tableName: string
  consolidator: string
  scheduleText: string
  brandNote: string
  plate: string
  cutoff: string
  sheetDate: string
  preparer: string
  bookingDate: string
}

export interface TruckDraft {
  taskId: string
  header: TruckHeader
  lines: TruckLine[]
  totals: Record<string, number>
}

export async function draftTruckSheet(factoryId: string, taskId: string): Promise<TruckDraft> {
  const { data } = await http.post<TruckDraft>('/shipping/loading-sheets/truck/draft', {
    factory_id: factoryId,
    task_id: taskId,
  })
  return data
}

export async function exportTruckSheet(factoryId: string, draft: TruckDraft): Promise<Blob> {
  const { data } = await http.post('/shipping/loading-sheets/truck/export', {
    factory_id: factoryId,
    taskId: draft.taskId,
    header: draft.header,
    lines: draft.lines,
  }, { responseType: 'blob', timeout: 120_000 })
  return data as Blob
}

export interface BulkTruckLine {
  id: string
  tradingHouse: string
  contract: string
  filingCode: string
  declareCode: string
  coefficient: number | null
  name?: string
  quantity: number | null
  cartons: number | null
  boards: string
  grossWeight: number | null
  netWeight: number | null
  cbm: number | null
  country: string
  grossPerCarton: number | null
  netPerCarton: number | null
  cbmPerCarton: number | null
  brand: string
  so: string
  po: string
  shippingNote: string
  remark: string
  manual?: boolean
}

export interface BulkTruckHeader {
  toNames: string[]
  fromName: string
  sheetDate: string
  vehicle: string
  transport: string
  truckType: string
  tradeTerm: string
  tableName: string
  cutoff: string
  originPort: string
  brandName?: string
  contractNo?: string
  poNo?: string
  orderNo?: string
  filingCode?: string
  bookingNo?: string
  transportCompanyName?: string
  remark?: string
  shipper?: string
  consignee?: string
  country?: string
  arrivalCutoff?: string
  tradingHouse?: string
  plate?: string
  warehouseNo?: string
  consolidator?: string
  truckCount?: string | number
}

export interface BulkTruckDraft {
  taskId: string
  header: BulkTruckHeader
  lines: BulkTruckLine[]
  totals: Record<string, number>
}

export async function draftBulkTruckSheet(factoryId: string, taskId: string): Promise<BulkTruckDraft> {
  const { data } = await http.post<BulkTruckDraft>('/shipping/loading-sheets/bulk-truck/draft', {
    factory_id: factoryId,
    task_id: taskId,
  })
  return data
}

export async function exportBulkTruckSheet(factoryId: string, draft: BulkTruckDraft): Promise<Blob> {
  const { data } = await http.post('/shipping/loading-sheets/bulk-truck/export', {
    factory_id: factoryId,
    taskId: draft.taskId,
    header: draft.header,
    lines: draft.lines,
  }, { responseType: 'blob', timeout: 120_000 })
  return data as Blob
}

export interface SupplementLine {
  id: string
  mixNo: string
  containerNo: string
  sealNo: string
  size: string
  itemNo: string
  description: string
  salesConf: string
  po: string
  ctns: number | null
  pallet: string
  qty: number | null
  booking: string
  deliveryDate: string
  cbmPerCarton: number | null
  cbm: number | null
  gwPerCarton: number | null
  gw: number | null
  pack: string
  tare: number | null
  vgm: number | null
}

export interface SupplementHeader {
  to: string
  from: string
  subject: string
  ref: string
  date: string
  customerMarket: string
  vessel: string
  portOfLoading: string
  portOfDischarge: string
  etd: string
  invoice: string
  origin: string
  receipt: string
}

export interface SupplementDraft {
  taskId: string
  header: SupplementHeader
  lines: SupplementLine[]
  totals: Record<string, number>
}

export async function draftSupplementSheet(factoryId: string, taskId: string): Promise<SupplementDraft> {
  const { data } = await http.post<SupplementDraft>('/shipping/loading-sheets/supplement/draft', {
    factory_id: factoryId,
    task_id: taskId,
  })
  return data
}

export async function exportSupplementSheet(factoryId: string, draft: SupplementDraft): Promise<Blob> {
  const { data } = await http.post('/shipping/loading-sheets/supplement/export', {
    factory_id: factoryId,
    taskId: draft.taskId,
    header: draft.header,
    lines: draft.lines,
  }, { responseType: 'blob', timeout: 120_000 })
  return data as Blob
}

export interface CustomsDoc {
  id: string
  filename: string
  subject: string
  port: string
  container_type: string
  si_cutoff: string
  special_note: string
  size: number
  created_at: string
  read: boolean
}

export async function listCustomsDocs(factoryId: string) {
  const { data } = await http.get<{ docs: CustomsDoc[]; unread: number }>('/shipping/customs-docs', {
    params: { factory_id: factoryId },
  })
  return data
}

export async function markCustomsDocsRead(factoryId: string) {
  const { data } = await http.post<{ marked: number }>('/shipping/customs-docs/read', { factory_id: factoryId })
  return data
}

export async function downloadCustomsDoc(factoryId: string, docId: string) {
  const { data } = await http.get(`/shipping/customs-docs/${docId}/download`, {
    params: { factory_id: factoryId },
    responseType: 'blob',
    timeout: 120_000,
  })
  return data as Blob
}

export async function importFactorySchedule(factoryId: string, history = false) {
  const { data } = await http.post<{
    factory_id: string
    created: number
    updated: number
    groups: number
    lines: number
    history?: boolean
  }>('/shipping/schedule-import', null, { params: { factory_id: factoryId, history }, timeout: 120_000 })
  return data
}

export interface CodeMappingImportRow {
  date: string
  contractNo: string
  code: string
  name: string
  quantity: string
  cartons: string
  perCarton: string
  category: string
  note: string
  gross: string
  net: string
  volume: string
  source: string
  country: string
  customer: string
  transport: string
  containerMode: string
  trip: string
  containerType: string
  plate: string
  containerNo: string
  sealNo: string
  port: string
  mode: string
  po: string
  status: string
  tone: 'blue' | 'orange' | 'red'
}

export async function exportCodeMappingRows(factoryId: string, date: string, rows: Array<Record<string, unknown>>) {
  const { data } = await http.post<{ path: string; filename: string; count: number }>('/shipping/code-mappings/export', {
    factory_id: factoryId,
    date,
    rows,
  })
  return data
}

export async function importCodeMappingFile(factoryId: string, file: File): Promise<{ filename: string; rows: CodeMappingImportRow[]; count: number }> {
  const form = new FormData()
  form.append('factory_id', factoryId)
  form.append('file', file)
  const { data } = await http.post<{ filename: string; rows: CodeMappingImportRow[]; count: number }>('/shipping/code-mappings/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return data
}

export interface ScheduleFileImportResult {
  filename: string
  rows: number
  groups: number
  created: number
  updated: number
}

export async function importFactoryScheduleFile(factoryId: string, file: File): Promise<ScheduleFileImportResult> {
  const form = new FormData()
  form.append('factory_id', factoryId)
  form.append('file', file)
  const { data } = await http.post<ScheduleFileImportResult>('/shipping/schedule-import/file', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return data
}

export interface GeneratedDoc {
  id: string
  module: string
  filename: string
  email_name?: string
  brand_name?: string
  task_id: string
  created_at: string
}

export async function listGeneratedDocs(factoryId: string, module: string) {
  const { data } = await http.get<{ docs: GeneratedDoc[] }>('/shipping/generated-docs', {
    params: { factory_id: factoryId, module },
  })
  return data.docs
}

export interface GeneratedDocDetail extends GeneratedDoc {
  header: Record<string, unknown>
  lines: Array<Record<string, unknown>>
}

export async function getGeneratedDoc(factoryId: string, docId: string) {
  const { data } = await http.get<GeneratedDocDetail>(`/shipping/generated-docs/${docId}`, {
    params: { factory_id: factoryId },
  })
  return data
}

export async function updateGeneratedDoc(
  factoryId: string,
  docId: string,
  header: Record<string, unknown>,
  lines: Array<Record<string, unknown>>,
) {
  const { data } = await http.patch<GeneratedDocDetail>(`/shipping/generated-docs/${docId}`, {
    factory_id: factoryId,
    header,
    lines,
  })
  return data
}

export async function downloadGeneratedDoc(factoryId: string, docId: string) {
  const { data } = await http.get(`/shipping/generated-docs/${docId}/download`, {
    params: { factory_id: factoryId },
    responseType: 'blob',
    timeout: 120_000,
  })
  return data as Blob
}

export async function previewGeneratedDoc(factoryId: string, docId: string) {
  const { data } = await http.post<{ opened: boolean; path: string; filename?: string; sheets?: WorkbookPreviewSheet[] }>(
    `/shipping/generated-docs/${docId}/preview`, null, { params: { factory_id: factoryId } },
  )
  return data
}

export async function previewLoadingSheet(factoryId: string, sheetId: string) {
  const { data } = await http.post<{ opened: boolean; path: string; filename?: string; sheets?: WorkbookPreviewSheet[] }>(
    `/shipping/loading-sheets/${sheetId}/preview`, null, { params: { factory_id: factoryId } },
  )
  return data
}

export async function updateGeneratedDocHeader(factoryId: string, docId: string, header: { contractNo?: string; plate?: string; remark?: string }) {
  const { data } = await http.patch<{ updated: boolean; filename: string; path: string }>(
    `/shipping/generated-docs/${docId}/header`, header, { params: { factory_id: factoryId } },
  )
  return data
}

export async function openGeneratedDoc(factoryId: string, docId: string) {
  const { data } = await http.post<{ opened: boolean; path: string; filename?: string; sheets?: WorkbookPreviewSheet[] }>(
    `/shipping/generated-docs/${docId}/open`, null, { params: { factory_id: factoryId } },
  )
  return data
}

export async function openCustomsDoc(factoryId: string, docId: string) {
  const { data } = await http.post<{ opened: boolean; path: string }>(
    `/shipping/customs-docs/${docId}/open`, null, { params: { factory_id: factoryId } },
  )
  return data
}

export async function deleteGeneratedDoc(factoryId: string, docId: string) {
  const { data } = await http.delete<{ deleted: boolean }>(`/shipping/generated-docs/${docId}`, {
    params: { factory_id: factoryId },
  })
  return data
}

export async function deleteCustomsDoc(factoryId: string, docId: string) {
  const { data } = await http.delete<{ deleted: boolean }>(`/shipping/customs-docs/${docId}`, {
    params: { factory_id: factoryId },
  })
  return data
}

export async function saveGeneratedDoc(factoryId: string, docId: string) {
  const { data } = await http.post<{ saved: boolean; path: string }>(
    `/shipping/generated-docs/${docId}/save`, null, { params: { factory_id: factoryId } },
  )
  return data
}

export async function saveCustomsDoc(factoryId: string, docId: string) {
  const { data } = await http.post<{ saved: boolean; path: string }>(
    `/shipping/customs-docs/${docId}/save`, null, { params: { factory_id: factoryId } },
  )
  return data
}

export async function generateShippingDocs(factoryId: string, taskId: string, modules: string[]) {
  const { data } = await http.post<{ docs: Array<{ module: string; filename: string; id: string }> }>(
    '/shipping/generated-docs/generate',
    { factory_id: factoryId, task_id: taskId, modules },
    { timeout: 120_000 },
  )
  return data
}

export interface ShippingScheduleRow {
  task_id: string
  so_number: string
  customer: string
  container_type: string
  port: string
  destination_country: string
  planned_ship_date: string
  si_deadline: string
  cutoff_date: string
  status: string
  contract_no: string
  product_code: string
  product_name: string
  customer_po: string
  quantity: number | null
  cartons: number | null
  cbm: number | null
  order_date: string
  inspection_date: string
  requested_ship_date: string
  sales_order_no: string
  packing: number | null
  standard: string
  remark: string
}

/** 工厂排期单明细：一个备案货号可能对应多个合同号，接口已按 合同 × 货号 拆行。 */
export async function listScheduleRows(factoryId: string) {
  const { data } = await http.get<{ rows: ShippingScheduleRow[]; tasks: number }>(
    '/shipping/schedule/rows',
    { params: { factory_id: factoryId } },
  )
  return data
}

export interface PalletStatsSummary {
  totalPallets: number
  totalContainers: number
  estimatedCost: number
  recordCount: number
  customerCount: number
}

export interface PalletStatsGroup {
  key: string
  factoryId: string
  factoryName: string
  customer: string
  spec: string
  unitPrice: number
  containerCount: number
  totalPallets: number
  estimatedCost: number
  recordCount: number
}

export type PalletRecordType = 'manual' | 'loading_sheet' | 'generated_doc'

export interface PalletStatsDetail {
  id: string
  factoryId: string
  originFactoryId?: string
  factoryName: string
  date: string
  customer: string
  containerNo: string
  containerType: string
  soNo: string
  contractNo: string
  filingCodes: string[]
  spec: string
  cartons: number
  pallets: number
  unitPrice: number
  estimatedCost: number
  source: string
  isContainer: boolean
  recordType: PalletRecordType
  editable: boolean
  remark: string
}

export interface PalletStatsResponse {
  year: string
  month: string
  factoryId: string
  customer: string
  q: string
  availableFactories: Array<{ id: string; name: string }>
  availableCustomers: string[]
  availableYears: string[]
  availableMonths: string[]
  excludedCount: number
  summary: PalletStatsSummary
  groups: PalletStatsGroup[]
  details: PalletStatsDetail[]
}

export interface ManualPalletRecordPayload {
  factory_id: string
  ship_date: string
  customer: string
  container_no?: string
  container_type?: string
  so_no?: string
  contract_no?: string
  filing_codes?: string
  spec?: string
  cartons?: number
  pallets: number
  unit_price?: number | null
  is_container?: boolean
  remark?: string
  record_type?: PalletRecordType
  origin_factory_id?: string
}

export interface PalletBatchDeleteItem {
  id: string
  factoryId: string
  originFactoryId?: string
  recordType: PalletRecordType
}

export interface PalletGroupUpdatePayload {
  items: PalletBatchDeleteItem[]
  factory_id: string
  customer: string
  spec: string
  container_count: number
  total_pallets: number
  unit_price: number
  estimated_cost?: number | null
  cost_overridden?: boolean
}

export interface PalletBatchDeleteResult {
  deletedManualCount: number
  excludedSyncCount: number
  totalRemoved: number
}

export async function fetchShippingPalletStats(params: {
  factory_id?: string
  year?: string
  month?: string
  customer?: string
  unit_price?: number
  q?: string
}): Promise<PalletStatsResponse> {
  const { data } = await http.get<PalletStatsResponse>('/shipping/pallet-stats', { params })
  return data
}

export async function exportShippingPalletStats(params: {
  factory_id?: string
  year?: string
  month?: string
  customer?: string
  unit_price?: number
  q?: string
}): Promise<Blob> {
  const { data } = await http.get('/shipping/pallet-stats/export', {
    params,
    responseType: 'blob',
    timeout: 120_000,
  })
  return data as Blob
}

export async function createShippingPalletRecord(payload: ManualPalletRecordPayload) {
  const { data } = await http.post('/shipping/pallet-stats/records', payload)
  return data
}

export async function updateShippingPalletRecord(recordId: string, payload: ManualPalletRecordPayload) {
  const { data } = await http.put(`/shipping/pallet-stats/records/${encodeURIComponent(recordId)}`, payload)
  return data
}

export async function updateShippingPalletGroup(payload: PalletGroupUpdatePayload) {
  const { data } = await http.put<{ updatedCount: number }>('/shipping/pallet-stats/groups', payload)
  return data
}

export async function batchDeleteShippingPalletRecords(items: PalletBatchDeleteItem[]): Promise<PalletBatchDeleteResult> {
  const { data } = await http.post<PalletBatchDeleteResult>('/shipping/pallet-stats/records/batch-delete', { items })
  return data
}

export async function restoreExcludedShippingPalletRecords(factoryId: string = 'all'): Promise<{ restoredCount: number }> {
  const { data } = await http.post<{ restoredCount: number }>('/shipping/pallet-stats/restore-excluded', {
    factory_id: factoryId,
  })
  return data
}
