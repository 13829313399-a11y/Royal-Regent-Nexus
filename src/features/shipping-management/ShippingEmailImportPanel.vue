<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ChevronDown, CloudUpload, RefreshCw, Trash2, UserRound } from '@lucide/vue'
import {
  confirmShippingMailBatch,  createShippingMailBatch,
  deleteShippingMailBatch,
  generateShippingDocs,
  getShippingMailAccount,
  getShippingMailBatch,
  listShippingMailBatches,
  previewShippingMail,
  searchScheduleProducts,
  saveShippingMailAccount,
  syncShippingMailAccount,
  testShippingMailAccount,
  type ShippingMailAccount,
  type ShippingMailBatch,
  type ShippingMailLine,
  type ShippingMailPreview,
} from '@/api/shippingMail'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ factoryId: string }>()
const emit = defineEmits<{ notify: [message: string]; 'open-module': [page: 'so' | 'truck' | 'supplement' | 'customs'] }>()

const selectedFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const recordsOpen = ref(false)
const selectedBatchId = ref('')
const selectedBatchItem = ref<{ id: string; status: string; task_ids: string[] } | null>(null)
const pendingBatchDelete = ref('')
const deletingBatch = ref(false)
const batchLoading = ref(false)
const selectedBatchIds = ref<string[]>([])
const bulkDeleteArmed = ref(false)
const bulkDeleting = ref(false)
const mailServer = ref('')
const mailAddress = ref('')
const mailPassword = ref('')
const parsing = ref(false)
const confirming = ref(false)
const confirmedTaskId = ref('')
const createError = ref('')
const previews = ref<ShippingMailPreview[]>([])
const batches = ref<ShippingMailBatch[]>([])
const loadError = ref('')
const account = ref<ShippingMailAccount | null>(null)
const accountError = ref('')
const accountBusy = ref(false)
const syncing = ref(false)

const summary = reactive({
  terminal: '',
  fromPort: '',
  toPort: '',
  country: '',
  voyageNo: '',
  bookingNo: '',
  containerSo: '',
  vesselName: '',
  shipper: '',
  contractNo: '',
  poNo: '',
  containerType: '',
  bookingDate: '',
  brandName: '',
})

const summaryFields = [
  { key: 'terminal', label: '码头' },
  { key: 'country', label: '国家' },
  { key: 'voyageNo', label: '航次' },
  { key: 'bookingNo', label: '订仓号' },
  { key: 'containerSo', label: '柜S/O' },
  { key: 'vesselName', label: '船名' },
  { key: 'shipper', label: '发货商' },
  { key: 'contractNo', label: '合同号' },
  { key: 'poNo', label: 'PO（箱唛）' },
  { key: 'containerType', label: '柜型' },
  { key: 'bookingDate', label: '截止日期' },
  { key: 'brandName', label: '品牌名称' },
] as const

const demoPackingList: ShippingMailLine[] = [
  { product_code: '15754', product_name: '链条枪', quantity: 12, cartons: 4, cbm: 2.4, gross_weight: 18.5 },
  { product_code: '92107', product_name: '泡泡棒', quantity: 24, cartons: 6, cbm: 3.1, gross_weight: 22.0 },
  { product_code: '88123', product_name: '户外水壶', quantity: 8, cartons: 2, cbm: 1.2, gross_weight: 9.6 },
  { product_code: '77201', product_name: '折叠椅', quantity: 6, cartons: 2, cbm: 1.8, gross_weight: 14.2 },
]

const demoRecords = [
  { id: '', subject: 'SHZ8265013 出货通知', from: 'shipping@customer.com', time: '11/13 09:42', status: '已确认', tone: 'blue' },
  { id: '', subject: 'SO 822 出货明细更新', from: 'ops@forwarder.com', time: '11/13 09:15', status: '已解析', tone: 'blue' },
  { id: '', subject: 'Fwd: 柜号 C260304887 装柜照片', from: 'warehouse@example.com', time: '11/13 08:51', status: '待确认', tone: 'orange' },
  { id: '', subject: 'SO 823 附件缺失', from: 'ops@forwarder.com', time: '11/13 08:20', status: '解析失败', tone: 'red' },
]

const statusDot: Record<string, string> = {
  blue: 'bg-blue-500',
  orange: 'bg-amber-500',
  red: 'bg-rose-500',
}

const items = computed<ShippingMailLine[]>(() => {
  const parsed = previews.value.flatMap((preview) => preview.items ?? [])
  if (parsed.length) return parsed
  return selectedBatchId.value ? [] : demoPackingList
})

const recordRows = computed(() => {
  if (!batches.value.length) return demoRecords
  return batches.value.map((batch) => ({
    id: batch.id,
    subject: batch.filename ?? batch.file_name ?? batch.id,
    from: `解析 ${batch.parsed_count}/${batch.total_count} 条`,
    time: batch.created_at,
    status: batch.status === 'confirmed' ? '已确认' : batch.status === 'failed' ? '解析失败' : '待确认',
    tone: batch.status === 'confirmed' ? 'blue' : batch.status === 'failed' ? 'red' : 'orange',
  }))
})

const tableName = computed(() => `${summary.terminal || '待定码头'}SO排期表`)

const warnings = computed(() => [...new Set(previews.value.flatMap((preview) => preview.warnings ?? []))])

const canConfirm = computed(() => selectedFiles.value.length > 0)

function previewMessage(title: string) {
  emit('notify', `界面预览：${title}尚未接入后端接口。`)
}

const scheduleLabel = computed(() => {
  return '每天 08:00–23:00 每小时自动收件（华兴 / 华登 / 华康A / 华康B / 华康D）；24:00 后停止'
})

const accountStatus = computed(() => {
  if (!account.value?.configured) return '尚未配置邮箱，保存并连接后开始每周自动收件。'
  if (account.value.last_status === 'error') return `上次同步失败：${account.value.last_error}`
  if (account.value.last_sync_at) return `上次同步：${account.value.last_sync_at.replace('T', ' ')}`
  return '邮箱已配置，等待首次同步。'
})

async function loadAccount() {
  try {
    account.value = await getShippingMailAccount(props.factoryId)
    mailServer.value = account.value.host
    mailAddress.value = account.value.username
    accountError.value = ''
  } catch (error) {
    accountError.value = getApiErrorMessage(error)
  }
}

async function saveAndConnect() {
  accountBusy.value = true
  accountError.value = ''
  try {
    if (!mailPassword.value.trim() && !account.value?.has_password) {
      throw new Error('请填写网易邮箱授权码')
    }
    if (!mailPassword.value.trim() && account.value?.username && mailAddress.value.trim() !== account.value.username) {
      throw new Error('更换邮箱地址后必须重新填写新邮箱的授权码')
    }
    const [host, portText] = mailServer.value.trim().split(':')
    const port = Number(portText) || 993
    account.value = await saveShippingMailAccount({
      factory_id: props.factoryId,
      host: (host ?? '').trim(),
      port,
      username: mailAddress.value.trim(),
      password: mailPassword.value,
      use_ssl: true,
      folder: 'INBOX',
      enabled: true,
    })
    mailPassword.value = ''
    const tested = await testShippingMailAccount(props.factoryId)
    emit('notify', tested.message || '邮箱连接成功，已启用每周自动收件。')
  } catch (error) {
    accountError.value = getApiErrorMessage(error)
    await loadAccount()
    emit('notify', `邮箱配置失败：${accountError.value}`)
  } finally {
    accountBusy.value = false
  }
}

async function syncNow() {
  syncing.value = true
  try {
    const run = await syncShippingMailAccount(props.factoryId)
    emit('notify', `同步完成：拉取 ${run.fetched} 封，新增 ${run.imported} 封，自动生成 ${run.confirmed} 条排期。`)
    await loadBatches()
    await loadAccount()
  } catch (error) {
    emit('notify', `同步失败：${getApiErrorMessage(error)}`)
  } finally {
    syncing.value = false
  }
}

onMounted(loadAccount)

function onFileChange(event: Event) {
  const files = [...((event.target as HTMLInputElement).files ?? [])]
  setFiles(files)
}

function onDrop(event: DragEvent) {
  setFiles([...(event.dataTransfer?.files ?? [])])
}

function resetSummary() {
  for (const field of summaryFields) summary[field.key as keyof typeof summary] = ''
}

function setFiles(files: File[]) {
  selectedFiles.value = files
  previews.value = []
  selectedBatchId.value = ''
  selectedBatchItem.value = null
  confirmedTaskId.value = ''
  createError.value = ''
  resetSummary()
  loadError.value = ''
  if (files.length) {
    emit('notify', `已选择 ${files.length} 个文件，正在自动解析…`)
    void parseSelected()
  }
}

function openFilePicker() {
  fileInput.value?.click()
}

async function fillPoFromSchedule() {
  if ((summary.poNo && summary.brandName) || !summary.contractNo.trim()) return
  try {
    const items = await searchScheduleProducts(props.factoryId, summary.contractNo.trim())
    const contract = summary.contractNo.trim().toLowerCase()
    const matched = items.find((item) => String(item.contract_no || '').trim().toLowerCase() === contract)
    if (matched?.customer_po && !summary.poNo) summary.poNo = String(matched.customer_po)
    if (!summary.brandName && (matched?.brand || matched?.customer)) {
      summary.brandName = String(matched.brand || matched.customer)
    }
  } catch {
    // keep PO/brand empty when schedule lookup fails
  }
}

function applyFields(preview: ShippingMailPreview) {
  const fields = preview.fields ?? {}
  const str = (key: string) => (typeof fields[key] === 'string' ? (fields[key] as string) : '')
  const tails = fields.contract_tails
  if (!summary.terminal) summary.terminal = str('terminal')
  if (!summary.fromPort) summary.fromPort = str('from_port')
  if (!summary.toPort) summary.toPort = str('to_port')
  if (!summary.country) summary.country = str('destination_country')
  if (!summary.voyageNo) summary.voyageNo = str('voyage_no')
  if (!summary.bookingNo) summary.bookingNo = str('booking_no') || str('so_number')
  if (!summary.containerSo) summary.containerSo = str('container_so') || str('so_number')
  if (!summary.vesselName) summary.vesselName = str('vessel_name')
  if (!summary.shipper) summary.shipper = str('shipper') || '华兴玩具制品（河源）有限公司'
  if (!summary.contractNo) {
    const tailValues = Array.isArray(tails) ? tails.map((tail) => String(tail).trim()).filter(Boolean) : []
    let combined = str('contract_no')
    for (const tail of tailValues) {
      if (tail && !combined.endsWith(tail)) combined += tail
    }
    summary.contractNo = combined
  }
  if (!summary.poNo) {
    const lines = preview.items ?? []
    const po = str('po_no') || str('customer_po') || String(lines.map((line) => String((line as unknown as Record<string, unknown>).customer_po || '')).find(Boolean) || '')
    if (po) summary.poNo = po
  }
  if (!summary.brandName) summary.brandName = str('brand') || str('brand_name') || str('customer')
  if (!summary.containerType) summary.containerType = str('container_type')
  if (!summary.bookingDate) summary.bookingDate = str('cutoff_date') || str('si_deadline') || str('booking_date') || str('planned_ship_date')
  void fillPoFromSchedule()
}

async function parseSelected() {
  if (!selectedFiles.value.length) {
    emit('notify', '请先选择 .eml 邮件或扫描件（PDF / Word / Excel）。')
    return
  }
  parsing.value = true
  loadError.value = ''
  createError.value = ''
  resetSummary()
  confirmedTaskId.value = ''
  const results: ShippingMailPreview[] = []
  try {
    const parsed = await Promise.all(selectedFiles.value.map((file) => previewShippingMail(props.factoryId, file)))
    results.push(...parsed)
    previews.value = results
    for (const preview of results) applyFields(preview)
    emit('notify', `解析完成：${results.length} 个文件，${items.value.length} 行货物明细。`)
  } catch (error) {
    loadError.value = getApiErrorMessage(error)
    emit('notify', `解析失败：${loadError.value}`)
  } finally {
    parsing.value = false
  }
}

const missingBooking = computed(() => previews.value.length > 0 && !summary.bookingNo && !summary.contractNo)

async function ensureConfirmedTask(modules?: string[]): Promise<string | null> {
  if (confirmedTaskId.value) return confirmedTaskId.value
  createError.value = ''
  if (selectedBatchId.value && selectedBatchItem.value) {
    const item = selectedBatchItem.value
    if (item.status === 'confirmed') {
      confirmedTaskId.value = String(item.task_ids[0] || '')
      if (confirmedTaskId.value) return confirmedTaskId.value
      createError.value = '该解析记录已确认，但没有关联排期'
      return null
    }
    if (item.status !== 'pending') {
      createError.value = `该解析记录状态为 ${item.status}，不能创建`
      return null
    }
    confirming.value = true
    try {
      const confirmed = await confirmShippingMailBatch(selectedBatchId.value, props.factoryId, [item.id], {}, modules)
      const taskId = String((confirmed.tasks?.[0] as { id?: string } | undefined)?.id || '')
      confirmedTaskId.value = taskId
      selectedBatchItem.value = { ...item, status: 'confirmed', task_ids: taskId ? [taskId] : [] }
      emit('notify', '已确认该解析记录并生成排期。')
      await loadBatches()
      return taskId || null
    } catch (error) {
      createError.value = `创建失败：${getApiErrorMessage(error)}`
      return null
    } finally {
      confirming.value = false
    }
  }
  if (!canConfirm.value) {
    createError.value = '请先上传并解析邮件或附件，再创建单据。'
    return null
  }
  if (!previews.value.length) {
    createError.value = '请先上传并解析邮件，再创建单据。'
    return null
  }
  if (!summary.bookingNo) {
    createError.value = '没有识别到订舱号/订舱信息，无法创建排期；请上传订舱确认邮件，或在上方补填订舱号后再试。'
    return null
  }
  confirming.value = true
  try {
    const created = await createShippingMailBatch(props.factoryId, selectedFiles.value)
    const pending = created.items.filter((item) => item.status === 'pending').map((item) => item.id)
    if (!pending.length) throw new Error('没有可确认的邮件')
    const confirmed = await confirmShippingMailBatch(created.batch.id, props.factoryId, pending, {
      so_number: summary.bookingNo.trim(),
      contract_no: summary.contractNo.trim(),
      po_no: summary.poNo.trim(),
      container_type: summary.containerType.trim(),
      brand: summary.brandName.trim(),
      from_port: summary.fromPort.trim(),
      to_port: summary.toPort.trim(),
      destination_country: summary.country.trim(),
      voyage_no: summary.voyageNo.trim(),
      vessel_name: summary.vesselName.trim(),
      container_so: summary.containerSo.trim(),
      shipper: summary.shipper.trim(),
      cutoff_date: summary.bookingDate.trim(),
      terminal: summary.terminal.trim(),
    }, modules)
    const taskId = String((confirmed.tasks?.[0] as { id?: string } | undefined)?.id || '')
    confirmedTaskId.value = taskId
    emit('notify', `已创建 ${pending.length} 条 SO 排期（${tableName.value}）。`)
    await loadBatches()
    return taskId || null
  } catch (error) {
    createError.value = `创建失败：${getApiErrorMessage(error)}`
    return null
  } finally {
    confirming.value = false
  }
}

async function createModule(module: 'so' | 'truck' | 'supplement' | 'customs') {
  const taskId = await ensureConfirmedTask(module === 'customs' ? undefined : [module])
  if (!taskId) return
  if (module !== 'customs') {
    try {
      const result = await generateShippingDocs(props.factoryId, taskId, [module])
      emit('notify', result.docs.length ? `已创建 ${result.docs.length} 份文件。` : '文件已存在，正在打开模块。')
    } catch (error) {
      createError.value = `创建失败：${getApiErrorMessage(error)}`
      return
    }
  }
  emit('open-module', module)
}

async function confirmCreate() {
  await ensureConfirmedTask()
}

async function openBatch(batchId: string) {
  if (!batchId) return
  selectedBatchId.value = batchId
  batchLoading.value = true
  resetSummary()
  try {
    const detail = await getShippingMailBatch(props.factoryId, batchId)
    const item = detail.items[0]
    if (!item) {
      loadError.value = '该解析记录没有邮件明细'
      previews.value = []
      return
    }
    previews.value = [{
      filename: item.filename,
      fields: item.fields ?? {},
      items: item.items ?? [],
      warnings: item.warnings ?? [],
      attachments: [],
      rule_trace: [],
      status: item.status,
      parser_version: '',
    } as ShippingMailPreview]
    selectedBatchItem.value = { id: item.id, status: item.status, task_ids: item.task_ids ?? [] }
    confirmedTaskId.value = item.status === 'confirmed' ? String(item.task_ids?.[0] || '') : ''
    applyFields(previews.value[0])
    createError.value = ''
    loadError.value = ''
  } catch (error) {
    loadError.value = getApiErrorMessage(error)
  } finally {
    batchLoading.value = false
  }
}

async function createFromBatch(batchId: string, module: 'so' | 'truck' | 'supplement' | 'customs') {
  if (!batchId) return
  createError.value = ''
  try {
    const detail = await getShippingMailBatch(props.factoryId, batchId)
    const item = detail.items[0]
    if (!item) throw new Error('该解析记录没有邮件明细')
    let taskId = item.status === 'confirmed' ? String(item.task_ids?.[0] || '') : ''
    if (!taskId) {
      if (item.status !== 'pending') throw new Error(`该记录状态为 ${item.status}，不能创建`)
      const confirmed = await confirmShippingMailBatch(batchId, props.factoryId, [item.id])
      taskId = String((confirmed.tasks?.[0] as { id?: string } | undefined)?.id || '')
    }
    if (!taskId) throw new Error('没有生成排期任务')
    if (module !== 'customs') {
      await generateShippingDocs(props.factoryId, taskId, [module])
    }
    await loadBatches()
    emit('open-module', module)
    emit('notify', '已从解析记录创建单据。')
  } catch (error) {
    createError.value = `创建失败：${getApiErrorMessage(error)}`
  }
}

function onCreateFromRecord(event: Event, batchId: string) {
  const select = event.target as HTMLSelectElement
  const module = select.value as 'so' | 'truck' | 'supplement' | 'customs' | ''
  select.value = ''
  if (module) void createFromBatch(batchId, module)
}

function askDeleteBatch(batchId: string) {
  pendingBatchDelete.value = batchId
  window.setTimeout(() => {
    if (pendingBatchDelete.value === batchId) pendingBatchDelete.value = ''
  }, 5000)
}

async function confirmDeleteBatch(batchId: string) {
  deletingBatch.value = true
  try {
    await deleteShippingMailBatch(props.factoryId, batchId)
    pendingBatchDelete.value = ''
    if (selectedBatchId.value === batchId) {
      selectedBatchId.value = ''
      selectedBatchItem.value = null
      previews.value = []
      resetSummary()
    }
    await loadBatches()
    emit('notify', '解析记录已删除。')
  } catch (error) {
    loadError.value = getApiErrorMessage(error)
  } finally {
    deletingBatch.value = false
  }
}

async function loadBatches() {
  try {
    batches.value = await listShippingMailBatches(props.factoryId)
    const ids = new Set(batches.value.map((batch) => batch.id))
    selectedBatchIds.value = selectedBatchIds.value.filter((id) => ids.has(id))
    loadError.value = ''
  } catch (error) {
    loadError.value = getApiErrorMessage(error)
  }
}

const selectableBatchIds = computed(() => recordRows.value.filter((row) => row.id).map((row) => row.id))
const allBatchesSelected = computed(() => selectableBatchIds.value.length > 0 && selectableBatchIds.value.every((id) => selectedBatchIds.value.includes(id)))

function toggleBatch(id: string) {
  selectedBatchIds.value = selectedBatchIds.value.includes(id)
    ? selectedBatchIds.value.filter((value) => value !== id)
    : [...selectedBatchIds.value, id]
  bulkDeleteArmed.value = false
}

function onToggleAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  selectedBatchIds.value = checked ? [...selectableBatchIds.value] : []
  bulkDeleteArmed.value = false
}

async function bulkDeleteBatches() {
  if (!selectedBatchIds.value.length) return
  if (!bulkDeleteArmed.value) {
    bulkDeleteArmed.value = true
    window.setTimeout(() => { bulkDeleteArmed.value = false }, 5000)
    return
  }
  bulkDeleting.value = true
  try {
    let deleted = 0
    for (const batchId of [...selectedBatchIds.value]) {
      try {
        await deleteShippingMailBatch(props.factoryId, batchId)
        deleted += 1
      } catch {
        // continue deleting the rest
      }
    }
    selectedBatchIds.value = []
    bulkDeleteArmed.value = false
    await loadBatches()
    emit('notify', `已删除 ${deleted} 条解析记录。`)
  } finally {
    bulkDeleting.value = false
  }
}

async function toggleRecords() {
  recordsOpen.value = !recordsOpen.value
  if (recordsOpen.value) await loadBatches()
}

async function refreshRecords() {
  await loadBatches()
  emit('notify', '解析记录已刷新。')
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="min-w-0">
        <h2 class="text-[16px] font-bold tracking-[-0.02em] text-emerald-950">邮件导入</h2>
        <p class="mt-0.5 text-[11px] text-slate-500">上传 .eml 或扫描件，自动识别合同号、航次、码头并生成 SO 排期表。</p>
      </div>
      <span class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 text-[11px] font-medium text-emerald-900">
        <UserRound class="size-3.5" aria-hidden="true" />查看员 admin
      </span>
    </div>

    <section class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4" aria-label="上传邮件">
      <div
        class="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-emerald-300/70 bg-emerald-50/40 px-4 py-8 text-center transition hover:border-emerald-400 hover:bg-emerald-100/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600"
        role="button"
        tabindex="0"
        aria-label="拖拽或点击上传邮件与扫描件"
        @click="openFilePicker"
        @keydown.enter.prevent="openFilePicker"
        @keydown.space.prevent="openFilePicker"
        @dragover.prevent
        @drop.prevent="onDrop"
      >
        <span class="flex size-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
          <CloudUpload class="size-7" aria-hidden="true" />
        </span>
        <p class="mt-3 text-[13px] font-semibold text-emerald-950">将邮件或扫描件拖到此处，或点击上传（支持多封）</p>
        <p class="mt-1 text-[11px] text-emerald-800/60">支持 .eml / PDF / Word / Excel；扫描件需可提取文本或人工补录。</p>
        <input ref="fileInput" type="file" accept=".eml,.pdf,.docx,.xlsx,.xlsm" multiple class="hidden" @change="onFileChange">
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-800 px-4 text-[12px] font-semibold text-white shadow-sm transition hover:bg-emerald-900 disabled:opacity-60"
          :disabled="parsing"
          @click="parseSelected"
        >
          {{ parsing ? '解析中…' : `解析邮件（${selectedFiles.length}封）` }}
        </button>
        <button
          type="button"
          class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-100 px-4 text-[12px] font-semibold text-emerald-900 shadow-sm transition hover:bg-emerald-200 disabled:opacity-60"
          :disabled="parsing"
          @click="parseSelected"
        >
          AI自动解析
        </button>
        <span v-if="selectedFiles.length" class="text-[11px] text-slate-500">
          {{ selectedFiles.map((file) => file.name).join('、') }}
        </span>
      </div>
      <p v-if="loadError" class="mt-2 text-[11px] text-rose-600">{{ loadError }}</p>
    </section>

    <section class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4" aria-label="从邮箱直接导入">
      <h3 class="text-[13px] font-bold text-emerald-950">从邮箱直接导入</h3>
      <div class="mt-3 max-w-2xl space-y-2.5">
        <label class="flex items-center gap-3">
          <span class="w-20 shrink-0 text-right text-[12px] text-slate-600">邮件服务器</span>
          <input v-model="mailServer" type="text" placeholder="imap.example.com" class="h-9 min-w-0 flex-1 rounded-lg border border-emerald-100 bg-white px-3 text-[12px] text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-3 focus:ring-emerald-500/15">
        </label>
        <label class="flex items-center gap-3">
          <span class="w-20 shrink-0 text-right text-[12px] text-slate-600">邮箱地址</span>
          <input v-model="mailAddress" type="email" placeholder="shipping@example.com" class="h-9 min-w-0 flex-1 rounded-lg border border-emerald-100 bg-white px-3 text-[12px] text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-3 focus:ring-emerald-500/15">
        </label>
        <label class="flex items-center gap-3">
          <span class="w-20 shrink-0 text-right text-[12px] text-slate-600">授权码 / 密码</span>
          <input v-model="mailPassword" type="password" :placeholder="account?.has_password ? '已保存，留空不修改' : '网易邮箱请填授权码'" class="h-9 min-w-0 flex-1 rounded-lg border border-emerald-100 bg-white px-3 text-[12px] text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-3 focus:ring-emerald-500/15">
        </label>
      </div>
      <p class="mt-2 text-[11px] text-amber-700">
        网易 163/126 邮箱请填写弹窗上方那串授权码（通常 16 位）；「使用设备」名称最多 10 个字符，不是授权码。
      </p>
      <div class="mt-4 flex flex-wrap items-center gap-2">
        <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-blue-600 px-4 text-[12px] font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-60" :disabled="accountBusy" @click="saveAndConnect">
          {{ accountBusy ? '连接中…' : '保存并连接' }}
        </button>
        <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-4 text-[12px] font-semibold text-emerald-900 transition hover:bg-emerald-100 disabled:opacity-60" :disabled="syncing || !account?.configured" @click="syncNow">
          <RefreshCw class="size-3.5" aria-hidden="true" />{{ syncing ? '同步中…' : '立即同步' }}
        </button>
      </div>
      <p class="mt-2 text-[11px]" :class="accountError || account?.last_status === 'error' ? 'text-rose-600' : 'text-emerald-800/70'">
        {{ accountError || accountStatus }}
        <button v-if="accountError" type="button" class="ml-2 font-semibold underline underline-offset-2" @click="loadAccount">重试</button>
      </p>
      <p class="mt-1 text-[11px] text-slate-500">{{ scheduleLabel }}</p>
    </section>

    <section class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50" aria-label="解析记录">
      <div class="flex items-center justify-between gap-2 px-4 py-2.5">
        <button type="button" class="flex min-w-0 items-center gap-1.5 text-[13px] font-bold text-emerald-950" :aria-expanded="recordsOpen" @click="toggleRecords">
          <ChevronDown class="size-4 transition" :class="recordsOpen ? 'rotate-180' : ''" aria-hidden="true" />
          解析记录（{{ batches.length }}）
        </button>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-[11px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-50"
            :class="bulkDeleteArmed ? 'border-rose-300 bg-rose-50 text-rose-700' : 'border-rose-200 bg-white text-rose-600 hover:bg-rose-50'"
            :disabled="!selectedBatchIds.length || bulkDeleting"
            @click="bulkDeleteBatches"
          >
            <Trash2 class="size-3.5" aria-hidden="true" />{{ bulkDeleteArmed ? `确认删除 ${selectedBatchIds.length} 条` : `删除${selectedBatchIds.length ? ` (${selectedBatchIds.length})` : ''}` }}
          </button>
          <button
            v-if="bulkDeleteArmed"
            type="button"
            class="inline-flex h-8 items-center rounded-lg border border-slate-200 bg-white px-2.5 text-[11px] font-semibold text-slate-600 transition hover:bg-slate-50"
            @click="bulkDeleteArmed = false"
          >取消删除</button>
          <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 bg-white px-2.5 text-[11px] font-semibold text-emerald-800 transition hover:border-emerald-300 hover:bg-emerald-50" @click="refreshRecords">
            <RefreshCw class="size-3.5" aria-hidden="true" />刷新
          </button>
          <button v-if="recordsOpen" type="button" class="text-[11px] text-slate-400 hover:text-slate-600" @click="recordsOpen = false">收起</button>
        </div>
      </div>
      <div v-if="recordsOpen" class="border-t border-emerald-100 px-4 py-2">
        <table class="w-full text-left text-[11px]">
          <thead class="text-slate-400">
            <tr>
              <th scope="col" class="w-8 py-1.5 font-medium">
                <input type="checkbox" aria-label="全选解析记录" :checked="allBatchesSelected" @change="onToggleAll">
              </th>
              <th scope="col" class="py-1.5 font-medium">邮件主题</th>
              <th scope="col" class="py-1.5 font-medium">发件人 / 条数</th>
              <th scope="col" class="py-1.5 font-medium">解析时间</th>
              <th scope="col" class="py-1.5 text-right font-medium">状态</th>
              <th scope="col" class="py-1.5 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50 text-slate-600">
            <tr v-for="record in recordRows" :key="record.id || record.subject" :class="record.id ? 'cursor-pointer hover:bg-emerald-50/60' : ''" @click="openBatch(record.id)">
              <td class="py-1.5" @click.stop>
                <input
                  v-if="record.id"
                  type="checkbox"
                  :aria-label="`选择 ${record.subject}`"
                  :checked="selectedBatchIds.includes(record.id)"
                  @change="toggleBatch(record.id)"
                >
              </td>
              <td class="max-w-[280px] truncate py-1.5 font-medium" :class="record.id ? 'text-emerald-800 underline decoration-emerald-200 underline-offset-2' : 'text-slate-800'">{{ record.subject }}</td>
              <td class="py-1.5">{{ record.from }}</td>
              <td class="py-1.5 tabular-nums">{{ record.time }}</td>
              <td class="py-1.5 text-right">
                <span class="inline-flex items-center gap-1.5">
                  <span class="size-1.5 rounded-full" :class="statusDot[record.tone]" aria-hidden="true" />
                  {{ record.status }}
                </span>
              </td>
              <td class="py-1.5 text-right" @click.stop>
                <select
                  v-if="record.id"
                  class="mr-1 h-6 rounded border border-emerald-200 bg-white px-1 text-[10px] text-emerald-800"
                  aria-label="从解析记录创建单据"
                  @change="onCreateFromRecord($event, record.id)"
                >
                  <option value="">创建…</option>
                  <option value="so">创建SO出货表</option>
                  <option value="truck">创建车的出货单</option>
                  <option value="supplement">创建补料单</option>
                </select>
                <button
                  v-if="record.id && pendingBatchDelete === record.id"
                  type="button"
                  class="text-[11px] font-semibold text-rose-700 disabled:opacity-50"
                  :disabled="deletingBatch"
                  @click="confirmDeleteBatch(record.id)"
                >确认删除</button>
                <button
                  v-else-if="record.id"
                  type="button"
                  class="text-[11px] font-semibold text-rose-600"
                  @click="askDeleteBatch(record.id)"
                >删除</button>
                <span v-else class="text-slate-300">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4" aria-label="出货单草稿">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 class="text-[13px] font-bold text-emerald-950">{{ tableName }}</h3>
        <span class="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-900">{{ items.length }} 行</span>
      </div>

      <div class="mt-3 grid gap-3 rounded-lg bg-emerald-50/70 px-3 py-2.5 sm:grid-cols-2 lg:grid-cols-3">
        <label v-for="field in summaryFields" :key="field.key" class="block min-w-0">
          <span class="block text-[10px] font-medium text-emerald-800/70">{{ field.label }}</span>
          <input
            v-model="summary[field.key]"
            type="text"
            placeholder="-"
            :aria-label="field.label"
            class="mt-0.5 h-7 w-full rounded border border-transparent bg-transparent px-0 text-[12px] font-semibold text-emerald-950 outline-none transition placeholder:text-slate-400 hover:border-emerald-200 focus:border-emerald-400 focus:bg-white"
          >
        </label>
      </div>

      <div v-if="warnings.length" class="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-5 text-amber-900">
        <p v-for="warning in warnings" :key="warning">{{ warning }}</p>
      </div>

      <div class="mt-3 flex flex-wrap items-center justify-between gap-2">
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="h-8 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 text-[11px] font-semibold text-emerald-800 hover:bg-emerald-100" @click="createModule('so')">创建SO出货表</button>
          <button type="button" class="h-8 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 text-[11px] font-semibold text-emerald-800 hover:bg-emerald-100" @click="createModule('truck')">创建车的出货单</button>
          <button type="button" class="h-8 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 text-[11px] font-semibold text-emerald-800 hover:bg-emerald-100" @click="createModule('supplement')">创建补料单</button>
        </div>
        <button
          type="button"
          class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-700 px-4 text-[12px] font-semibold text-white shadow-sm transition hover:bg-emerald-800 disabled:opacity-60"
          :disabled="confirming"
          @click="confirmCreate"
        >
          {{ confirming ? '创建中…' : '确认创建出货单' }}
        </button>
      </div>
      <p v-if="missingBooking" class="mt-2 text-[11px] font-medium text-amber-700">
        只识别到装箱明细：未识别到订舱号/合同号，无法创建排期。请在上方补填订舱号，或上传订舱确认邮件（含 SO、船名、港口）。
      </p>
      <p v-if="createError" class="mt-1 text-[11px] font-medium text-rose-600">{{ createError }}</p>
    </section>
  </div>
</template>
