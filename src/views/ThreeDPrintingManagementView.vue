<script setup lang="ts">
import {
  Activity,
  Archive,
  Boxes,
  CalendarDays,
  CirclePause,
  CirclePlay,
  Download,
  History,
  ImagePlus,
  PackagePlus,
  Printer,
  RefreshCw,
  Save,
  Settings2,
  ShieldCheck,
  Trash2,
  Wrench,
} from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getApiErrorMessage } from '@/lib/http'
import { threeDPrintingApi } from '@/api/threeDPrinting'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import type {
  ThreeDAuditEvent,
  ThreeDDashboard,
  ThreeDMaintenance,
  ThreeDMaterial,
  ThreeDPrinter,
  ThreeDProduct,
  ThreeDProductionRecord,
  ThreeDSchedule,
} from '@/types/threeDPrinting'

type TabId = 'overview' | 'records' | 'products' | 'materials' | 'schedules' | 'maintenance' | 'audit'

const FACTORY_ID = 'huakang-a' as const
const tabs: { id: TabId; label: string; icon: typeof Printer }[] = [
  { id: 'overview', label: '打印机看板', icon: Printer },
  { id: 'records', label: '生产记录', icon: Activity },
  { id: 'products', label: '产品与图片', icon: ImagePlus },
  { id: 'materials', label: '物料与仓库', icon: Boxes },
  { id: 'schedules', label: '生产计划', icon: CalendarDays },
  { id: 'maintenance', label: '维护记录', icon: Wrench },
  { id: 'audit', label: '设置与审计', icon: ShieldCheck },
]

const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()
const activeTab = ref<TabId>('overview')
const dashboard = ref<ThreeDDashboard | null>(null)
const auditEvents = ref<ThreeDAuditEvent[]>([])
const loading = ref(false)
const saving = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const productSearch = ref('')
const dateFrom = ref('')
const dateTo = ref('')
let refreshTimer: ReturnType<typeof window.setInterval> | undefined

const canOperate = computed(() =>
  authStore.can('three_d_printing:operate', FACTORY_ID, 'three-d-printing'),
)
const canUploadImage = computed(() =>
  authStore.can('three_d_printing:image_upload', FACTORY_ID, 'three-d-printing'),
)
const canExport = computed(() =>
  authStore.can('three_d_printing:export', FACTORY_ID, 'three-d-printing'),
)
const canControl = computed(() =>
  authStore.can('three_d_printing:printer_control', FACTORY_ID, 'three-d-printing'),
)
const canReadAudit = computed(() =>
  authStore.can('three_d_printing:audit_read', FACTORY_ID, 'three-d-printing'),
)

function todayText() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const recordForm = reactive({
  id: '',
  revision: 1,
  business_date: todayText(),
  machine_no: 1,
  status: 'running' as 'running' | 'idle' | 'fault',
  product_id: '',
  product_name: '',
  material_name: '',
  weight_g: 0,
  quantity: 1,
  duration_hours: 0,
  design_fee: 0,
  quoted_price: 0,
  customer: '',
  remark: '',
})

const productForm = reactive({
  id: '',
  revision: 1,
  name: '',
  customer: '',
  material_name: '',
  weight_g: 0,
  duration_hours: 0,
  default_quantity: 1,
  quoted_price: 0,
})
const pendingProductImage = ref<File | null>(null)
const imageInputKey = ref(0)

const materialForm = reactive({
  name: '',
  material_type: '',
  price_per_kg: 0,
})

const stockInForm = reactive({
  business_date: todayText(),
  material_name: '',
  amount_g: 1000,
  vendor: '',
  cost: 0,
  remark: '',
})

const scheduleForm = reactive({
  business_date: todayText(),
  product_id: '',
  product_name: '',
  customer: '',
  material_name: '',
  weight_g: 1,
  quantity: 1,
  machine_no: 0,
  priority: 'normal' as 'high' | 'normal' | 'low',
  status: 'pending' as 'pending' | 'printing' | 'done' | 'cancelled',
  remark: '',
})

const maintenanceForm = reactive({
  business_date: todayText(),
  machine_no: 0,
  maintenance_type: '日常保养',
  description: '',
  cost: 0,
  vendor: '',
  remark: '',
})

const settingsForm = reactive({
  machine_count: 11,
  electricity_per_machine_day: 1.5,
  labor_per_day: 220,
  material_loss_rate: 1.2,
  profit_rate_percent: 40,
  revision: 1,
})

const visibleProducts = computed(() => {
  const query = productSearch.value.trim().toLowerCase()
  if (!query) return dashboard.value?.products ?? []
  return (dashboard.value?.products ?? []).filter((product) =>
    [product.name, product.customer, product.material_name]
      .some((value) => value.toLowerCase().includes(query)),
  )
})

const printerMetrics = computed(() => {
  const printers = dashboard.value?.printers ?? []
  return {
    total: printers.length,
    connected: printers.filter((printer) => printer.connected).length,
    running: printers.filter((printer) => printer.state === 'RUNNING').length,
    paused: printers.filter((printer) => printer.state === 'PAUSE').length,
  }
})

function stateLabel(state: string) {
  return {
    RUNNING: '打印中',
    PAUSE: '已暂停',
    IDLE: '空闲',
    FINISH: '已完成',
    FAILED: '失败',
    ERROR: '异常',
    OFFLINE: '离线',
  }[state] ?? state
}

function stateClass(printer: ThreeDPrinter) {
  if (!printer.connected) return 'bg-slate-100 text-slate-600'
  if (printer.state === 'RUNNING') return 'bg-emerald-100 text-emerald-700'
  if (printer.state === 'PAUSE') return 'bg-amber-100 text-amber-700'
  if (['FAILED', 'ERROR'].includes(printer.state)) return 'bg-rose-100 text-rose-700'
  return 'bg-sky-100 text-sky-700'
}

function money(value: unknown) {
  return `¥${Number(value || 0).toFixed(2)}`
}

function showSuccess(message: string) {
  successMessage.value = message
  window.setTimeout(() => {
    if (successMessage.value === message) successMessage.value = ''
  }, 3500)
}

async function loadDashboard(background = false) {
  if (!background) loading.value = true
  try {
    dashboard.value = await threeDPrintingApi.dashboard(dateFrom.value, dateTo.value)
    Object.assign(settingsForm, dashboard.value.settings)
    errorMessage.value = ''
  } catch (error) {
    if (!background) errorMessage.value = getApiErrorMessage(error)
  } finally {
    if (!background) loading.value = false
  }
}

async function mutate(action: () => Promise<unknown>, success: string) {
  saving.value = true
  errorMessage.value = ''
  try {
    await action()
    await loadDashboard(true)
    showSuccess(success)
    return true
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
    return false
  } finally {
    saving.value = false
  }
}

function chooseRecordProduct() {
  const product = dashboard.value?.products.find((item) => item.id === recordForm.product_id)
  if (!product) return
  recordForm.product_name = product.name
  recordForm.material_name = product.material_name
  recordForm.weight_g = product.weight_g
  recordForm.quantity = product.default_quantity
  recordForm.duration_hours = product.duration_hours
  recordForm.quoted_price = product.quoted_price
  recordForm.customer = product.customer
}

function resetRecordForm() {
  Object.assign(recordForm, {
    id: '',
    revision: 1,
    business_date: todayText(),
    machine_no: 1,
    status: 'running',
    product_id: '',
    product_name: '',
    material_name: '',
    weight_g: 0,
    quantity: 1,
    duration_hours: 0,
    design_fee: 0,
    quoted_price: 0,
    customer: '',
    remark: '',
  })
}

function editRecord(record: ThreeDProductionRecord) {
  Object.assign(recordForm, record)
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function submitRecord() {
  const payload = {
    factory_id: FACTORY_ID,
    business_date: recordForm.business_date,
    machine_no: recordForm.machine_no,
    status: recordForm.status,
    product_id: recordForm.product_id,
    product_name: recordForm.product_name,
    material_name: recordForm.material_name,
    weight_g: recordForm.weight_g,
    quantity: recordForm.quantity,
    duration_hours: recordForm.duration_hours,
    design_fee: recordForm.design_fee,
    quoted_price: recordForm.quoted_price,
    customer: recordForm.customer,
    remark: recordForm.remark,
  }
  const ok = await mutate(
    () => recordForm.id
      ? threeDPrintingApi.updateRecord(recordForm.id, { ...payload, revision: recordForm.revision })
      : threeDPrintingApi.createRecord(payload),
    recordForm.id ? '生产记录已更新' : '生产记录已新增',
  )
  if (ok) resetRecordForm()
}

async function removeRecord(record: ThreeDProductionRecord) {
  if (!window.confirm(`确认撤销 ${record.business_date} · ${record.machine_no}号机记录？历史审计会保留。`)) return
  await mutate(() => threeDPrintingApi.deleteRecord(record.id), '生产记录已撤销')
}

function resetProductForm() {
  Object.assign(productForm, {
    id: '',
    revision: 1,
    name: '',
    customer: '',
    material_name: '',
    weight_g: 0,
    duration_hours: 0,
    default_quantity: 1,
    quoted_price: 0,
  })
  pendingProductImage.value = null
  imageInputKey.value += 1
}

function editProduct(product: ThreeDProduct) {
  Object.assign(productForm, product)
  pendingProductImage.value = null
  imageInputKey.value += 1
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function selectProductImage(event: Event) {
  const input = event.target as HTMLInputElement
  pendingProductImage.value = input.files?.[0] ?? null
}

async function submitProduct() {
  saving.value = true
  errorMessage.value = ''
  try {
    const payload = {
      factory_id: FACTORY_ID,
      name: productForm.name,
      customer: productForm.customer,
      material_name: productForm.material_name,
      weight_g: productForm.weight_g,
      duration_hours: productForm.duration_hours,
      default_quantity: productForm.default_quantity,
      quoted_price: productForm.quoted_price,
    }
    const product = productForm.id
      ? await threeDPrintingApi.updateProduct(productForm.id, {
          ...payload,
          revision: productForm.revision,
        })
      : await threeDPrintingApi.createProduct(payload)
    if (pendingProductImage.value) {
      await threeDPrintingApi.uploadProductImage(product.id, pendingProductImage.value)
    }
    await loadDashboard(true)
    showSuccess(pendingProductImage.value ? '产品及图片已保存' : '产品已保存')
    resetProductForm()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    saving.value = false
  }
}

async function archiveProduct(product: ThreeDProduct) {
  if (!window.confirm(`确认停用产品“${product.name}”？历史生产记录不会删除。`)) return
  await mutate(() => threeDPrintingApi.archiveProduct(product.id), '产品已停用')
}

async function submitMaterial() {
  const ok = await mutate(
    () => threeDPrintingApi.createMaterial({ factory_id: FACTORY_ID, ...materialForm }),
    '物料已新增',
  )
  if (ok) Object.assign(materialForm, { name: '', material_type: '', price_per_kg: 0 })
}

async function archiveMaterial(material: ThreeDMaterial) {
  if (!window.confirm(`确认停用物料“${material.name}”？历史流水不会删除。`)) return
  await mutate(() => threeDPrintingApi.archiveMaterial(material.id), '物料已停用')
}

async function adjustStock(materialName: string, stock: number, minimum: number) {
  const raw = window.prompt(`将“${materialName}”库存调整为多少克？`, String(stock))
  if (raw === null) return
  const target = Number(raw)
  if (!Number.isFinite(target) || target < 0) {
    errorMessage.value = '库存必须是大于或等于 0 的数字'
    return
  }
  const reason = window.prompt('请输入调整原因（必填）', '库存盘点调整')
  if (!reason?.trim()) return
  await mutate(
    () => threeDPrintingApi.adjustInventory(materialName, target, minimum, reason.trim()),
    '库存已调整并记录流水',
  )
}

async function submitStockIn() {
  const ok = await mutate(() => threeDPrintingApi.stockIn(stockInForm), '入库已登记')
  if (ok) Object.assign(stockInForm, {
    business_date: todayText(),
    material_name: '',
    amount_g: 1000,
    vendor: '',
    cost: 0,
    remark: '',
  })
}

function chooseScheduleProduct() {
  const product = dashboard.value?.products.find((item) => item.id === scheduleForm.product_id)
  if (!product) return
  scheduleForm.product_name = product.name
  scheduleForm.customer = product.customer
  scheduleForm.material_name = product.material_name
  scheduleForm.weight_g = product.weight_g || 1
  scheduleForm.quantity = product.default_quantity
}

async function submitSchedule() {
  const ok = await mutate(
    () => threeDPrintingApi.createSchedule({ factory_id: FACTORY_ID, ...scheduleForm }),
    '生产计划已新增',
  )
  if (ok) Object.assign(scheduleForm, {
    business_date: todayText(),
    product_id: '',
    product_name: '',
    customer: '',
    material_name: '',
    weight_g: 1,
    quantity: 1,
    machine_no: 0,
    priority: 'normal',
    status: 'pending',
    remark: '',
  })
}

async function changeScheduleStatus(schedule: ThreeDSchedule, status: ThreeDSchedule['status']) {
  await mutate(
    () => threeDPrintingApi.updateScheduleStatus(schedule.id, status, schedule.revision),
    '计划状态已更新',
  )
}

async function removeSchedule(schedule: ThreeDSchedule) {
  if (!window.confirm(`确认删除计划“${schedule.product_name}”？`)) return
  await mutate(() => threeDPrintingApi.deleteSchedule(schedule.id), '计划已删除')
}

async function submitMaintenance() {
  const ok = await mutate(
    () => threeDPrintingApi.createMaintenance({ factory_id: FACTORY_ID, ...maintenanceForm }),
    '维护记录已新增',
  )
  if (ok) Object.assign(maintenanceForm, {
    business_date: todayText(),
    machine_no: 0,
    maintenance_type: '日常保养',
    description: '',
    cost: 0,
    vendor: '',
    remark: '',
  })
}

async function removeMaintenance(record: ThreeDMaintenance) {
  if (!window.confirm(`确认删除 ${record.business_date} 的维护记录？`)) return
  await mutate(() => threeDPrintingApi.deleteMaintenance(record.id), '维护记录已删除')
}

async function sendCommand(printer: ThreeDPrinter, action: 'pause' | 'resume') {
  const actionName = action === 'pause' ? '暂停' : '恢复'
  if (!window.confirm(`确认远程${actionName} ${printer.machine_no}号机？`)) return
  const reason = window.prompt(`请输入${actionName}原因（将写入审计记录）`)
  if (!reason?.trim()) return
  await mutate(
    () => threeDPrintingApi.command(printer, action, reason.trim()),
    `${actionName}指令已进入边缘代理队列`,
  )
}

async function saveSettings() {
  await mutate(
    () => threeDPrintingApi.updateSettings({
      factory_id: FACTORY_ID,
      ...settingsForm,
    }),
    '计费设置已更新',
  )
}

async function loadAudit() {
  if (!canReadAudit.value) return
  try {
    auditEvents.value = await threeDPrintingApi.audit()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  }
}

async function exportWorkbook() {
  saving.value = true
  try {
    const blob = await threeDPrintingApi.exportWorkbook()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `3D打印管理-${todayText()}.xlsx`
    link.click()
    URL.revokeObjectURL(url)
    showSuccess('导出文件已生成')
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    saving.value = false
  }
}

watch(activeTab, (tab) => {
  if (tab === 'audit') void loadAudit()
})

onMounted(async () => {
  if (appStore.activeProductionFactory.id !== FACTORY_ID) {
    appStore.setActiveFactory(FACTORY_ID)
    await router.replace({ query: { ...router.currentRoute.value.query, factory: FACTORY_ID } })
  }
  await loadDashboard()
  refreshTimer = window.setInterval(() => {
    if (activeTab.value === 'overview' && !saving.value) void loadDashboard(true)
  }, 8000)
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-4 px-5 py-5 lg:px-8">
        <div>
          <div class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">
            <Printer class="size-4" />
            华康A · 生产部
          </div>
          <h1 class="mt-2 text-2xl font-bold text-slate-950">3D打印机管理</h1>
          <p class="mt-1 text-sm text-slate-500">打印状态、生产记录、产品图片、物料库存与计划维护统一管理</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <span class="rounded-full bg-slate-100 px-3 py-2 text-xs text-slate-600">
            {{ dashboard?.generated_at ? `数据 ${dashboard.generated_at}` : '正在连接云端' }}
          </span>
          <button class="action-button secondary" type="button" :disabled="loading" @click="loadDashboard()">
            <RefreshCw class="size-4" :class="{ 'animate-spin': loading }" />
            刷新
          </button>
          <button v-if="canExport" class="action-button" type="button" :disabled="saving" @click="exportWorkbook">
            <Download class="size-4" />
            导出 Excel
          </button>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-[1600px] px-5 py-6 lg:px-8">
      <div v-if="errorMessage" class="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
        {{ errorMessage }}
      </div>
      <div v-if="successMessage" class="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
        {{ successMessage }}
      </div>

      <nav class="mb-6 flex gap-2 overflow-x-auto rounded-xl border border-slate-200 bg-white p-2 shadow-sm">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="flex shrink-0 items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition"
          :class="activeTab === tab.id ? 'bg-teal-700 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100'"
          @click="activeTab = tab.id"
        >
          <component :is="tab.icon" class="size-4" />
          {{ tab.label }}
        </button>
      </nav>

      <div v-if="loading && !dashboard" class="rounded-2xl border border-slate-200 bg-white p-16 text-center text-slate-500">
        正在加载3D打印数据…
      </div>

      <template v-else-if="dashboard">
        <section v-if="activeTab === 'overview'" class="space-y-6">
          <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div class="metric-card"><span>打印机总数</span><strong>{{ printerMetrics.total }}</strong><small>华康A 已配置机台</small></div>
            <div class="metric-card"><span>在线</span><strong class="text-emerald-700">{{ printerMetrics.connected }}</strong><small>30 秒内收到状态</small></div>
            <div class="metric-card"><span>打印中</span><strong class="text-sky-700">{{ printerMetrics.running }}</strong><small>由边缘代理实时回传</small></div>
            <div class="metric-card"><span>低库存</span><strong class="text-amber-700">{{ dashboard.summary.lowInventoryCount ?? 0 }}</strong><small>低于物料预警线</small></div>
          </div>

          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <article v-for="printerItem in dashboard.printers" :key="printerItem.id" class="panel-card p-5">
              <div class="flex items-start justify-between gap-3">
                <div class="flex items-center gap-3">
                  <div class="rounded-xl bg-teal-50 p-3 text-teal-700"><Printer class="size-5" /></div>
                  <div><h2 class="font-bold text-slate-950">{{ printerItem.machine_no }}号机</h2><p class="text-xs text-slate-500">{{ printerItem.model || printerItem.printer_type }}</p></div>
                </div>
                <span class="rounded-full px-2.5 py-1 text-xs font-semibold" :class="stateClass(printerItem)">{{ stateLabel(printerItem.state) }}</span>
              </div>
              <p class="mt-5 min-h-10 truncate text-sm font-medium text-slate-800">{{ printerItem.current_file || '暂无打印文件' }}</p>
              <div class="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
                <div class="h-full rounded-full bg-teal-600 transition-all" :style="{ width: `${printerItem.progress_percent}%` }" />
              </div>
              <div class="mt-2 flex justify-between text-xs text-slate-500"><span>{{ printerItem.progress_percent }}%</span><span>剩余 {{ printerItem.remaining_minutes }} 分钟</span></div>
              <div class="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
                <div class="rounded-lg bg-slate-50 p-2"><span class="block text-slate-400">喷嘴</span><strong>{{ printerItem.nozzle_temperature }}°</strong></div>
                <div class="rounded-lg bg-slate-50 p-2"><span class="block text-slate-400">热床</span><strong>{{ printerItem.bed_temperature }}°</strong></div>
                <div class="rounded-lg bg-slate-50 p-2"><span class="block text-slate-400">材料</span><strong class="truncate">{{ printerItem.live_material || '—' }}</strong></div>
              </div>
              <p v-if="printerItem.error_text" class="mt-3 rounded-lg bg-rose-50 p-2 text-xs text-rose-700">{{ printerItem.error_text }}</p>
              <div v-if="canControl" class="mt-4 flex gap-2 border-t border-slate-100 pt-4">
                <button v-if="printerItem.connected && printerItem.state === 'RUNNING'" class="action-button warning flex-1" type="button" @click="sendCommand(printerItem, 'pause')"><CirclePause class="size-4" />远程暂停</button>
                <button v-if="printerItem.connected && printerItem.state === 'PAUSE'" class="action-button flex-1" type="button" @click="sendCommand(printerItem, 'resume')"><CirclePlay class="size-4" />恢复打印</button>
              </div>
            </article>
          </div>

          <div class="grid gap-4 lg:grid-cols-4">
            <div class="metric-card"><span>记录数</span><strong>{{ dashboard.summary.recordCount ?? 0 }}</strong><small>{{ dashboard.summary.productionDays ?? 0 }} 个生产日</small></div>
            <div class="metric-card"><span>估算收入</span><strong>{{ money(dashboard.summary.revenue) }}</strong><small>沿用旧系统计价公式</small></div>
            <div class="metric-card"><span>总成本</span><strong>{{ money(dashboard.summary.totalCost) }}</strong><small>材料、电费、人工及维护</small></div>
            <div class="metric-card"><span>结余</span><strong>{{ money(dashboard.summary.balance) }}</strong><small>当前筛选期间</small></div>
          </div>
        </section>

        <section v-else-if="activeTab === 'records'" class="space-y-5">
          <form v-if="canOperate" class="panel-card p-5" @submit.prevent="submitRecord">
            <div class="section-heading"><div><h2>{{ recordForm.id ? '编辑生产记录' : '新增生产记录' }}</h2><p>选择产品后自动带出材料、重量、时间与报价，可继续调整。</p></div><button v-if="recordForm.id" class="action-button secondary" type="button" @click="resetRecordForm">取消编辑</button></div>
            <div class="form-grid">
              <label>日期<input v-model="recordForm.business_date" required type="date"></label>
              <label>机号<input v-model.number="recordForm.machine_no" required min="1" max="100" type="number"></label>
              <label>状态<select v-model="recordForm.status"><option value="running">生产</option><option value="idle">空闲</option><option value="fault">故障</option></select></label>
              <label>产品<select v-model="recordForm.product_id" @change="chooseRecordProduct"><option value="">手工填写</option><option v-for="item in dashboard.products" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
              <label>产品名称<input v-model="recordForm.product_name" maxlength="255"></label>
              <label>材料<input v-model="recordForm.material_name" maxlength="255"></label>
              <label>单件重量(g)<input v-model.number="recordForm.weight_g" min="0" step="0.01" type="number"></label>
              <label>数量<input v-model.number="recordForm.quantity" min="0" type="number"></label>
              <label>单件时间(h)<input v-model.number="recordForm.duration_hours" min="0" step="0.01" type="number"></label>
              <label>设计费<input v-model.number="recordForm.design_fee" min="0" step="0.01" type="number"></label>
              <label>报价<input v-model.number="recordForm.quoted_price" min="0" step="0.01" type="number"></label>
              <label>客户<input v-model="recordForm.customer" maxlength="255"></label>
              <label class="md:col-span-2 xl:col-span-4">备注<input v-model="recordForm.remark" maxlength="4000"></label>
            </div>
            <button class="action-button mt-4" type="submit" :disabled="saving"><Save class="size-4" />{{ saving ? '保存中…' : '保存记录' }}</button>
          </form>
          <div class="panel-card p-5">
            <div class="section-heading">
              <div><h2>历史生产记录</h2><p>旧系统记录、自动记录与云端新增记录统一保留。</p></div>
              <div class="flex gap-2"><input v-model="dateFrom" class="compact-input" type="date"><input v-model="dateTo" class="compact-input" type="date"><button class="action-button secondary" type="button" @click="loadDashboard()">筛选</button></div>
            </div>
            <div class="table-wrap"><table><thead><tr><th>日期</th><th>机台</th><th>产品</th><th>客户</th><th>材料</th><th>数量</th><th>时间</th><th>来源</th><th v-if="canOperate">操作</th></tr></thead><tbody><tr v-for="record in dashboard.records" :key="record.id"><td>{{ record.business_date }}</td><td>{{ record.machine_no }}号</td><td><strong>{{ record.product_name || record.gcode_file || '—' }}</strong><small>{{ record.remark }}</small></td><td>{{ record.customer || '—' }}</td><td>{{ record.material_name || '—' }}</td><td>{{ record.quantity }}</td><td>{{ record.duration_hours }}h</td><td><span class="tag">{{ record.auto_record ? '设备自动' : record.legacy_id ? '旧系统' : '云端手工' }}</span></td><td v-if="canOperate"><div class="row-actions"><button type="button" @click="editRecord(record)">编辑</button><button class="danger" type="button" @click="removeRecord(record)">撤销</button></div></td></tr></tbody></table></div>
          </div>
        </section>

        <section v-else-if="activeTab === 'products'" class="space-y-5">
          <form v-if="canOperate" class="panel-card p-5" @submit.prevent="submitProduct">
            <div class="section-heading"><div><h2>{{ productForm.id ? '编辑产品' : '新增产品' }}</h2><p>产品资料先保存到数据库；选中的图片上传成功后才会结束本次保存。</p></div><button v-if="productForm.id" class="action-button secondary" type="button" @click="resetProductForm">取消编辑</button></div>
            <div class="form-grid">
              <label>产品名称<input v-model="productForm.name" required maxlength="255"></label>
              <label>客户<input v-model="productForm.customer" maxlength="255"></label>
              <label>材料<select v-model="productForm.material_name"><option value="">未指定</option><option v-for="item in dashboard.materials" :key="item.id" :value="item.name">{{ item.name }}</option></select></label>
              <label>单件重量(g)<input v-model.number="productForm.weight_g" min="0" step="0.01" type="number"></label>
              <label>单件时间(h)<input v-model.number="productForm.duration_hours" min="0" step="0.01" type="number"></label>
              <label>默认数量<input v-model.number="productForm.default_quantity" min="1" type="number"></label>
              <label>报价<input v-model.number="productForm.quoted_price" min="0" step="0.01" type="number"></label>
              <label v-if="canUploadImage">产品图片<input :key="imageInputKey" accept="image/jpeg,image/png,image/webp" type="file" @change="selectProductImage"><small>JPEG / PNG / WebP，最大 5MB；云端会压缩为安全尺寸。</small></label>
            </div>
            <button class="action-button mt-4" type="submit" :disabled="saving"><Save class="size-4" />{{ saving ? '正在保存产品和图片…' : '保存产品' }}</button>
          </form>
          <div class="panel-card p-5">
            <div class="section-heading"><div><h2>产品库</h2><p>{{ dashboard.products.length }} 个有效产品，历史图片已迁移为独立文件。</p></div><input v-model="productSearch" class="compact-input" placeholder="搜索产品、客户或材料"></div>
            <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              <article v-for="product in visibleProducts" :key="product.id" class="overflow-hidden rounded-xl border border-slate-200 bg-white">
                <div class="aspect-[4/3] bg-slate-100"><img v-if="product.image_url" :src="product.image_url" :alt="product.name" class="size-full object-cover" loading="lazy"><div v-else class="flex size-full items-center justify-center text-slate-400"><ImagePlus class="size-8" /></div></div>
                <div class="p-4"><h3 class="truncate font-semibold text-slate-950">{{ product.name }}</h3><p class="mt-1 truncate text-xs text-slate-500">{{ product.customer || '未登记客户' }} · {{ product.material_name || '未登记材料' }}</p><div class="mt-3 flex justify-between text-xs text-slate-600"><span>{{ product.weight_g }}g / {{ product.duration_hours }}h</span><strong>{{ money(product.quoted_price) }}</strong></div><div v-if="canOperate" class="row-actions mt-4"><button type="button" @click="editProduct(product)">编辑</button><button class="danger" type="button" @click="archiveProduct(product)">停用</button></div></div>
              </article>
            </div>
          </div>
        </section>

        <section v-else-if="activeTab === 'materials'" class="space-y-5">
          <div v-if="canOperate" class="grid gap-5 xl:grid-cols-2">
            <form class="panel-card p-5" @submit.prevent="submitMaterial"><div class="section-heading"><div><h2>新增物料</h2><p>物料价格参与旧系统兼容计价。</p></div></div><div class="form-grid"><label>名称<input v-model="materialForm.name" required></label><label>类型<input v-model="materialForm.material_type"></label><label>单价(元/kg)<input v-model.number="materialForm.price_per_kg" min="0" step="0.01" type="number"></label></div><button class="action-button mt-4" type="submit" :disabled="saving"><PackagePlus class="size-4" />新增物料</button></form>
            <form class="panel-card p-5" @submit.prevent="submitStockIn"><div class="section-heading"><div><h2>登记入库</h2><p>入库同时更新库存并生成不可丢失的流水。</p></div></div><div class="form-grid"><label>日期<input v-model="stockInForm.business_date" required type="date"></label><label>物料<select v-model="stockInForm.material_name" required><option value="">请选择</option><option v-for="item in dashboard.materials" :key="item.id" :value="item.name">{{ item.name }}</option></select></label><label>数量(g)<input v-model.number="stockInForm.amount_g" required min="0.01" step="0.01" type="number"></label><label>供应商<input v-model="stockInForm.vendor"></label><label>成本<input v-model.number="stockInForm.cost" min="0" step="0.01" type="number"></label><label>备注<input v-model="stockInForm.remark"></label></div><button class="action-button mt-4" type="submit" :disabled="saving"><PackagePlus class="size-4" />确认入库</button></form>
          </div>
          <div class="panel-card p-5"><div class="section-heading"><div><h2>库存</h2><p>库存快照与历史流水分别保存，迁移时不会重复累加入库历史。</p></div></div><div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3"><article v-for="item in dashboard.inventory" :key="item.id" class="rounded-xl border p-4" :class="item.is_low ? 'border-amber-300 bg-amber-50' : 'border-slate-200 bg-white'"><div class="flex justify-between"><strong>{{ item.material_name }}</strong><span v-if="item.is_low" class="tag bg-amber-100 text-amber-700">低库存</span></div><p class="mt-3 text-2xl font-bold">{{ (item.stock_g / 1000).toFixed(2) }} kg</p><p class="text-xs text-slate-500">预警线 {{ (item.min_stock_g / 1000).toFixed(2) }} kg</p><button v-if="canOperate" class="action-button secondary mt-3" type="button" @click="adjustStock(item.material_name, item.stock_g, item.min_stock_g)">盘点调整</button></article></div></div>
          <div class="panel-card p-5"><div class="section-heading"><div><h2>物料主数据</h2><p>{{ dashboard.materials.length }} 项有效物料</p></div></div><div class="table-wrap"><table><thead><tr><th>名称</th><th>类型</th><th>价格</th><th v-if="canOperate">操作</th></tr></thead><tbody><tr v-for="item in dashboard.materials" :key="item.id"><td><strong>{{ item.name }}</strong></td><td>{{ item.material_type || '—' }}</td><td>{{ money(item.price_per_kg) }}/kg</td><td v-if="canOperate"><button class="text-rose-600" type="button" @click="archiveMaterial(item)">停用</button></td></tr></tbody></table></div></div>
          <div class="panel-card p-5"><div class="section-heading"><div><h2>最近库存流水</h2><p>显示最近 500 条库存变动。</p></div></div><div class="table-wrap"><table><thead><tr><th>日期</th><th>物料</th><th>类型</th><th>变动(g)</th><th>结存(g)</th><th>供应商 / 备注</th></tr></thead><tbody><tr v-for="item in dashboard.inventory_movements" :key="item.id"><td>{{ item.business_date }}</td><td>{{ item.material_name }}</td><td><span class="tag">{{ item.movement_type }}</span></td><td :class="item.delta_g >= 0 ? 'text-emerald-700' : 'text-rose-700'">{{ item.delta_g }}</td><td>{{ item.balance_after_g }}</td><td>{{ item.vendor || item.remark || '—' }}</td></tr></tbody></table></div></div>
        </section>

        <section v-else-if="activeTab === 'schedules'" class="space-y-5">
          <form v-if="canOperate" class="panel-card p-5" @submit.prevent="submitSchedule"><div class="section-heading"><div><h2>新增生产计划</h2><p>计划可分配机台并按待排、打印、完成、取消流转。</p></div></div><div class="form-grid"><label>日期<input v-model="scheduleForm.business_date" required type="date"></label><label>产品<select v-model="scheduleForm.product_id" @change="chooseScheduleProduct"><option value="">手工填写</option><option v-for="item in dashboard.products" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>产品名称<input v-model="scheduleForm.product_name" required></label><label>客户<input v-model="scheduleForm.customer"></label><label>材料<input v-model="scheduleForm.material_name" required></label><label>单件重量(g)<input v-model.number="scheduleForm.weight_g" min="0.01" step="0.01" type="number"></label><label>数量<input v-model.number="scheduleForm.quantity" min="1" type="number"></label><label>机号(0=待分配)<input v-model.number="scheduleForm.machine_no" min="0" max="100" type="number"></label><label>优先级<select v-model="scheduleForm.priority"><option value="high">高</option><option value="normal">普通</option><option value="low">低</option></select></label><label class="md:col-span-2">备注<input v-model="scheduleForm.remark"></label></div><button class="action-button mt-4" type="submit" :disabled="saving"><CalendarDays class="size-4" />新增计划</button></form>
          <div class="panel-card p-5"><div class="section-heading"><div><h2>计划队列</h2><p>按日期与优先级排列。</p></div></div><div class="table-wrap"><table><thead><tr><th>日期</th><th>产品</th><th>材料 / 数量</th><th>机台</th><th>优先级</th><th>状态</th><th v-if="canOperate">操作</th></tr></thead><tbody><tr v-for="item in dashboard.schedules" :key="item.id"><td>{{ item.business_date }}</td><td><strong>{{ item.product_name }}</strong><small>{{ item.customer }}</small></td><td>{{ item.material_name }} · {{ item.quantity }}</td><td>{{ item.machine_no ? `${item.machine_no}号` : '待分配' }}</td><td>{{ item.priority }}</td><td><span class="tag">{{ item.status }}</span></td><td v-if="canOperate"><div class="row-actions"><button v-if="item.status === 'pending'" type="button" @click="changeScheduleStatus(item, 'printing')">开始</button><button v-if="item.status === 'printing'" type="button" @click="changeScheduleStatus(item, 'done')">完成</button><button v-if="!['done','cancelled'].includes(item.status)" class="danger" type="button" @click="changeScheduleStatus(item, 'cancelled')">取消</button><button class="danger" type="button" @click="removeSchedule(item)"><Trash2 class="size-3" /></button></div></td></tr></tbody></table></div></div>
        </section>

        <section v-else-if="activeTab === 'maintenance'" class="space-y-5">
          <form v-if="canOperate" class="panel-card p-5" @submit.prevent="submitMaintenance"><div class="section-heading"><div><h2>新增维护记录</h2><p>保养、维修和耗材更换统一纳入成本。</p></div></div><div class="form-grid"><label>日期<input v-model="maintenanceForm.business_date" required type="date"></label><label>机号(0=公共)<input v-model.number="maintenanceForm.machine_no" min="0" max="100" type="number"></label><label>类型<input v-model="maintenanceForm.maintenance_type" required></label><label>费用<input v-model.number="maintenanceForm.cost" min="0" step="0.01" type="number"></label><label>供应商<input v-model="maintenanceForm.vendor"></label><label class="md:col-span-2">维护内容<input v-model="maintenanceForm.description" required></label><label class="md:col-span-2">备注<input v-model="maintenanceForm.remark"></label></div><button class="action-button mt-4" type="submit" :disabled="saving"><Wrench class="size-4" />保存维护记录</button></form>
          <div class="panel-card p-5"><div class="section-heading"><div><h2>维护历史</h2><p>共 {{ dashboard.maintenance.length }} 条</p></div></div><div class="table-wrap"><table><thead><tr><th>日期</th><th>机台</th><th>类型</th><th>内容</th><th>供应商</th><th>费用</th><th v-if="canOperate">操作</th></tr></thead><tbody><tr v-for="item in dashboard.maintenance" :key="item.id"><td>{{ item.business_date }}</td><td>{{ item.machine_no ? `${item.machine_no}号` : '公共' }}</td><td>{{ item.maintenance_type }}</td><td>{{ item.description }}<small>{{ item.remark }}</small></td><td>{{ item.vendor || '—' }}</td><td>{{ money(item.cost) }}</td><td v-if="canOperate"><button class="text-rose-600" type="button" @click="removeMaintenance(item)">删除</button></td></tr></tbody></table></div></div>
        </section>

        <section v-else class="grid gap-5 xl:grid-cols-[420px_1fr]">
          <form class="panel-card p-5" @submit.prevent="saveSettings"><div class="section-heading"><div><h2>计费设置</h2><p>继续使用旧系统的机器、电费、人工、损耗和利润参数。</p></div><Settings2 class="size-5 text-slate-400" /></div><div class="space-y-3"><label>机器数量<input v-model.number="settingsForm.machine_count" :disabled="!canOperate" min="1" max="100" type="number"></label><label>单机每日电费<input v-model.number="settingsForm.electricity_per_machine_day" :disabled="!canOperate" min="0" step="0.01" type="number"></label><label>每日人工<input v-model.number="settingsForm.labor_per_day" :disabled="!canOperate" min="0" step="0.01" type="number"></label><label>材料损耗系数<input v-model.number="settingsForm.material_loss_rate" :disabled="!canOperate" min="0.01" step="0.01" type="number"></label><label>利润率(%)<input v-model.number="settingsForm.profit_rate_percent" :disabled="!canOperate" min="0" step="0.1" type="number"></label></div><button v-if="canOperate" class="action-button mt-4" type="submit" :disabled="saving"><Save class="size-4" />保存设置</button></form>
          <div class="panel-card p-5"><div class="section-heading"><div><h2>审计记录</h2><p>远程控制、图片、库存和业务变更均保留操作人及时间。</p></div><History class="size-5 text-slate-400" /></div><div v-if="!canReadAudit" class="rounded-xl bg-slate-50 p-6 text-sm text-slate-500">当前岗位无审计查看权限。</div><div v-else class="table-wrap"><table><thead><tr><th>时间</th><th>操作人</th><th>对象</th><th>动作</th><th>详情</th></tr></thead><tbody><tr v-for="event in auditEvents" :key="event.id"><td>{{ event.created_at }}</td><td>{{ event.actor_name || event.actor_type }}</td><td>{{ event.entity_type }}<small>{{ event.entity_id }}</small></td><td><span class="tag">{{ event.action }}</span></td><td class="max-w-md"><pre class="whitespace-pre-wrap text-xs">{{ JSON.stringify(event.detail, null, 2) }}</pre></td></tr></tbody></table></div></div>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
@reference "../style.css";

.panel-card { @apply rounded-2xl border border-slate-200 bg-white shadow-sm; }
.metric-card { @apply rounded-2xl border border-slate-200 bg-white p-5 shadow-sm; }
.metric-card span { @apply text-xs font-semibold uppercase tracking-wide text-slate-500; }
.metric-card strong { @apply mt-2 block text-2xl font-bold text-slate-950; }
.metric-card small { @apply mt-1 block text-xs text-slate-500; }
.action-button { @apply inline-flex min-h-9 items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50; }
.action-button.secondary { @apply border border-slate-200 bg-white text-slate-700 shadow-none hover:bg-slate-50; }
.action-button.warning { @apply bg-amber-600 hover:bg-amber-700; }
.section-heading { @apply mb-5 flex flex-wrap items-start justify-between gap-3; }
.section-heading h2 { @apply text-lg font-bold text-slate-950; }
.section-heading p { @apply mt-1 text-sm text-slate-500; }
.form-grid { @apply grid gap-4 md:grid-cols-2 xl:grid-cols-4; }
label { @apply block text-xs font-semibold text-slate-600; }
input, select { @apply mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/10 disabled:bg-slate-100; }
input[type="file"] { @apply h-auto py-2; }
label small { @apply mt-1 block font-normal text-slate-400; }
.compact-input { @apply mt-0 w-auto min-w-36; }
.table-wrap { @apply overflow-x-auto; }
table { @apply w-full min-w-[760px] border-collapse text-left text-sm; }
th { @apply border-b border-slate-200 bg-slate-50 px-3 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500; }
td { @apply border-b border-slate-100 px-3 py-3 align-top text-slate-700; }
td strong { @apply block text-slate-900; }
td small { @apply mt-1 block max-w-xs truncate text-xs text-slate-400; }
.tag { @apply inline-flex rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600; }
.row-actions { @apply flex items-center gap-3 text-xs font-semibold text-teal-700; }
.row-actions button { @apply inline-flex items-center gap-1 hover:underline; }
.row-actions .danger { @apply text-rose-600; }
</style>
