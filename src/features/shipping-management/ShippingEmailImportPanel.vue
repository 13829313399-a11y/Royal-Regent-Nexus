<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ChevronDown, CloudUpload, RefreshCw, UserRound } from '@lucide/vue'
import {
  confirmShippingMailBatch,
  createShippingMailBatch,
  getShippingMailAccount,
  listShippingMailBatches,
  previewShippingMail,
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
const emit = defineEmits<{ notify: [message: string] }>()

const selectedFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const recordsOpen = ref(false)
const mailServer = ref('')
const mailAddress = ref('')
const mailPassword = ref('')
const parsing = ref(false)
const confirming = ref(false)
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
  contractNo: '',
  contractTails: '',
  bookingDate: '',
})

const summaryFields = [
  { key: 'terminal', label: '码头' },
  { key: 'fromPort', label: 'FROM' },
  { key: 'toPort', label: 'TO' },
  { key: 'country', label: '国家' },
  { key: 'voyageNo', label: '航次号' },
  { key: 'bookingNo', label: '订仓号' },
  { key: 'contractNo', label: '合同号' },
  { key: 'contractTails', label: '合同后四位' },
  { key: 'bookingDate', label: '订仓日期' },
] as const

const demoPackingList: ShippingMailLine[] = [
  { product_code: '15754', product_name: '链条枪', quantity: 12, cartons: 4, cbm: 2.4, gross_weight: 18.5 },
  { product_code: '92107', product_name: '泡泡棒', quantity: 24, cartons: 6, cbm: 3.1, gross_weight: 22.0 },
  { product_code: '88123', product_name: '户外水壶', quantity: 8, cartons: 2, cbm: 1.2, gross_weight: 9.6 },
  { product_code: '77201', product_name: '折叠椅', quantity: 6, cartons: 2, cbm: 1.8, gross_weight: 14.2 },
]

const demoRecords = [
  { subject: 'SHZ8265013 出货通知', from: 'shipping@customer.com', time: '11/13 09:42', status: '已确认', tone: 'blue' },
  { subject: 'SO 822 出货明细更新', from: 'ops@forwarder.com', time: '11/13 09:15', status: '已解析', tone: 'blue' },
  { subject: 'Fwd: 柜号 C260304887 装柜照片', from: 'warehouse@example.com', time: '11/13 08:51', status: '待确认', tone: 'orange' },
  { subject: 'SO 823 附件缺失', from: 'ops@forwarder.com', time: '11/13 08:20', status: '解析失败', tone: 'red' },
]

const statusDot: Record<string, string> = {
  blue: 'bg-blue-500',
  orange: 'bg-amber-500',
  red: 'bg-rose-500',
}

const items = computed<ShippingMailLine[]>(() => {
  const parsed = previews.value.flatMap((preview) => preview.items ?? [])
  return parsed.length ? parsed : demoPackingList
})

const recordRows = computed(() => {
  if (!batches.value.length) return demoRecords
  return batches.value.map((batch) => ({
    subject: batch.filename ?? batch.file_name ?? batch.id,
    from: `解析 ${batch.parsed_count}/${batch.total_count} 条`,
    time: batch.created_at,
    status: batch.status === 'confirmed' ? '已确认' : batch.status === 'failed' ? '解析失败' : '待确认',
    tone: batch.status === 'confirmed' ? 'blue' : batch.status === 'failed' ? 'red' : 'orange',
  }))
})

const tableName = computed(() => `${summary.terminal || '待定码头'}SO排期表`)

const warnings = computed(() => [...new Set(previews.value.flatMap((preview) => preview.warnings ?? []))])

const canConfirm = computed(() => selectedFiles.value.some((file) => file.name.toLowerCase().endsWith('.eml')))

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

function setFiles(files: File[]) {
  selectedFiles.value = files
  previews.value = []
  loadError.value = ''
  if (files.length) {
    emit('notify', `已选择 ${files.length} 个文件，正在自动解析…`)
    void parseSelected()
  }
}

function openFilePicker() {
  fileInput.value?.click()
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
  if (!summary.contractNo) summary.contractNo = str('contract_no')
  if (!summary.contractTails) summary.contractTails = Array.isArray(tails) ? tails.join(' / ') : ''
  if (!summary.bookingDate) summary.bookingDate = str('booking_date')
}

async function parseSelected() {
  if (!selectedFiles.value.length) {
    emit('notify', '请先选择 .eml 邮件或扫描件（PDF / Word / Excel）。')
    return
  }
  parsing.value = true
  loadError.value = ''
  const results: ShippingMailPreview[] = []
  try {
    for (const file of selectedFiles.value) {
      results.push(await previewShippingMail(props.factoryId, file))
    }
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

async function confirmCreate() {
  if (!canConfirm.value) {
    emit('notify', '确认建单目前仅支持 .eml 邮件；扫描件请人工补录后再建单。')
    return
  }
  if (!previews.value.length) {
    emit('notify', '请先点击「解析邮件」预览字段，再确认创建出货单。')
    return
  }
  confirming.value = true
  try {
    const emlFiles = selectedFiles.value.filter((file) => file.name.toLowerCase().endsWith('.eml'))
    const created = await createShippingMailBatch(props.factoryId, emlFiles)
    const pending = created.items.filter((item) => item.status === 'pending').map((item) => item.id)
    if (!pending.length) throw new Error('没有可确认的邮件')
    await confirmShippingMailBatch(created.batch.id, props.factoryId, pending)
    emit('notify', `已创建 ${pending.length} 条 SO 排期（${tableName.value}）。`)
    await loadBatches()
  } catch (error) {
    emit('notify', `创建失败：${getApiErrorMessage(error)}`)
  } finally {
    confirming.value = false
  }
}

async function loadBatches() {
  try {
    batches.value = await listShippingMailBatches(props.factoryId)
    loadError.value = ''
  } catch (error) {
    loadError.value = getApiErrorMessage(error)
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
          class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-100 px-4 text-[12px] font-semibold text-emerald-900 shadow-sm transition hover:bg-emerald-200"
          @click="previewMessage('AI自动解析')"
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
          <span class="w-20 shrink-0 text-right text-[12px] text-slate-600">密码</span>
          <input v-model="mailPassword" type="password" :placeholder="account?.has_password ? '已保存，留空不修改' : '••••••••'" class="h-9 min-w-0 flex-1 rounded-lg border border-emerald-100 bg-white px-3 text-[12px] text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-3 focus:ring-emerald-500/15">
        </label>
      </div>
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
      </p>
      <p class="mt-1 text-[11px] text-slate-500">{{ scheduleLabel }}</p>
    </section>

    <section class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50" aria-label="解析记录">
      <div class="flex items-center justify-between gap-2 px-4 py-2.5">
        <button type="button" class="flex min-w-0 items-center gap-1.5 text-[13px] font-bold text-emerald-950" :aria-expanded="recordsOpen" @click="toggleRecords">
          <ChevronDown class="size-4 transition" :class="recordsOpen ? 'rotate-180' : ''" aria-hidden="true" />
          解析记录（4780）
        </button>
        <div class="flex items-center gap-2">
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
              <th scope="col" class="py-1.5 font-medium">邮件主题</th>
              <th scope="col" class="py-1.5 font-medium">发件人 / 条数</th>
              <th scope="col" class="py-1.5 font-medium">解析时间</th>
              <th scope="col" class="py-1.5 text-right font-medium">状态</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50 text-slate-600">
            <tr v-for="record in recordRows" :key="record.subject">
              <td class="max-w-[280px] truncate py-1.5 font-medium text-slate-800">{{ record.subject }}</td>
              <td class="py-1.5">{{ record.from }}</td>
              <td class="py-1.5 tabular-nums">{{ record.time }}</td>
              <td class="py-1.5 text-right">
                <span class="inline-flex items-center gap-1.5">
                  <span class="size-1.5 rounded-full" :class="statusDot[record.tone]" aria-hidden="true" />
                  {{ record.status }}
                </span>
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

      <div class="mt-3 overflow-x-auto">
        <table class="w-full min-w-[560px] text-left text-[11px]">
          <caption class="pb-1.5 text-left text-[12px] font-bold text-emerald-950">Packing List 明细</caption>
          <thead class="bg-emerald-50/80 text-emerald-800/70">
            <tr>
              <th scope="col" class="px-2 py-1.5 font-medium">货号</th>
              <th scope="col" class="px-2 py-1.5 font-medium">品名</th>
              <th scope="col" class="px-2 py-1.5 text-right font-medium">数量</th>
              <th scope="col" class="px-2 py-1.5 text-right font-medium">箱数</th>
              <th scope="col" class="px-2 py-1.5 text-right font-medium">CBM</th>
              <th scope="col" class="px-2 py-1.5 text-right font-medium">毛重（KG）</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50 text-slate-600">
            <tr v-for="item in items" :key="`${item.product_code}-${item.source_file || ''}`">
              <td class="px-2 py-1.5 font-semibold tabular-nums text-emerald-950">{{ item.product_code }}</td>
              <td class="px-2 py-1.5">{{ item.product_name || '-' }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ item.quantity ?? '-' }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ item.cartons ?? '-' }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ item.cbm ?? '-' }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ item.gross_weight ?? '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="mt-3 flex justify-end">
        <button
          type="button"
          class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-700 px-4 text-[12px] font-semibold text-white shadow-sm transition hover:bg-emerald-800 disabled:opacity-60"
          :disabled="confirming"
          @click="confirmCreate"
        >
          {{ confirming ? '创建中…' : '确认创建出货单' }}
        </button>
      </div>
    </section>
  </div>
</template>
