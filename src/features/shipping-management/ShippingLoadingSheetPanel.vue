<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Download, Plus, Trash2 } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  draftLoadingSheet,
  exportLoadingSheet,
  lookupScheduleLines,
  type LoadingDraft,
  type LoadingLine,
} from '@/api/shippingMail'
import { listShippingTasks, type ShippingScheduleTask } from '@/api/shippingTasks'

const props = defineProps<{ factoryId: string; initialDraft?: LoadingDraft | null; searchQuery?: string }>()
const emit = defineEmits<{ notify: [message: string] }>()

const tasks = ref<ShippingScheduleTask[]>([])
const selectedTaskId = ref('')
const search = ref('')
const draft = ref<LoadingDraft | null>(null)
const loading = ref(false)
const exporting = ref(false)
const recognizing = ref(false)
const message = ref('')

const preparers = ['农建壮', '小美']

const filteredTasks = computed(() => {
  const keyword = (props.searchQuery?.trim() || search.value).trim().toLowerCase()
  if (!keyword) return tasks.value
  return tasks.value.filter((task) => {
    const base = [task.so_number, task.customer, task.port, task.planned_ship_date]
    const items = (task.items ?? []).flatMap((item) => [item.contract_no, item.product_code, item.customer_po])
    return [...base, ...items].some((value) => String(value || '').toLowerCase().includes(keyword))
  })
})

const totals = computed(() => {
  const sum = (key: keyof LoadingLine) => (draft.value?.lines ?? [])
    .reduce((total, line) => total + (Number(line[key]) || 0), 0)
  return {
    quantity: sum('quantity'),
    cartons: sum('cartons'),
    grossWeight: sum('grossWeight'),
    netWeight: sum('netWeight'),
    cbm: sum('cbm'),
  }
})

async function loadTasks() {
  try {
    const all = await listShippingTasks(props.factoryId)
    const today = new Date().toISOString().slice(0, 10)
    const valid = all
      .filter((task) => task.source === 'schedule')
      .filter((task) => (task.items?.length ?? 0) > 0)
      .filter((task) => Boolean(task.planned_ship_date) && task.planned_ship_date >= today)
      .sort((a, b) => String(b.planned_ship_date).localeCompare(String(a.planned_ship_date)))
    const bySo = new Map<string, ShippingScheduleTask>()
    for (const task of valid) {
      if (!bySo.has(task.so_number)) bySo.set(task.so_number, task)
    }
    tasks.value = [...bySo.values()].sort((a, b) => String(b.planned_ship_date).localeCompare(String(a.planned_ship_date)))
  } catch (error) {
    message.value = `无法读取工厂排期：${getApiErrorMessage(error)}`
  }
}

function lineFromSchedule(item: Record<string, unknown>): LoadingLine {
  const quantity = Number(item.quantity) || null
  const cartons = Number(item.cartons) || null
  return {
    id: crypto.randomUUID(),
    tradingCompany: 'DK',
    contract: String(item.contract_no || ''),
    filingCode: String(item.product_code || ''),
    declareCode: String(item.product_code || ''),
    coefficient: Number(item.coefficient) || (quantity && cartons ? quantity / cartons : null),
    quantity,
    cartons,
    grossWeight: Number(item.gross_weight) || null,
    netWeight: Number(item.net_weight) || null,
    cbm: Number(item.cbm) || null,
    category: '塑胶',
    grossPerCarton: cartons && Number(item.gross_weight) ? Number(item.gross_weight) / cartons : null,
    netPerCarton: cartons && Number(item.net_weight) ? Number(item.net_weight) / cartons : null,
    description: String(item.product_name || ''),
    department: 'W',
  }
}

async function recognizeContract() {
  if (!draft.value) return
  const query = draft.value.header.contractNo?.trim() || draft.value.header.soNo.trim()
  if (!query) return
  recognizing.value = true
  message.value = ''
  try {
    const items = await lookupScheduleLines(props.factoryId, query)
    if (!items.length) {
      message.value = `没有找到合同号/ SO ${query} 对应的工厂排期产品`
      return
    }
    const existing = new Set(draft.value.lines.map((line) => `${line.contract}|${line.filingCode}`))
    let added = 0
    for (const item of items) {
      const key = `${String(item.contract_no || '')}|${String(item.product_code || '')}`
      if (existing.has(key)) continue
      draft.value.lines.push(lineFromSchedule(item))
      existing.add(key)
      added += 1
    }
    if (!draft.value.header.contractNo && items[0].contract_no) {
      draft.value.header.contractNo = String(items[0].contract_no)
    }
    if (!draft.value.header.soNo && items[0].so_number) {
      draft.value.header.soNo = String(items[0].so_number)
    }
    message.value = added ? `已从工厂排期识别并填入 ${added} 行产品` : '对应产品已在明细中'
  } catch (error) {
    message.value = `识别失败：${getApiErrorMessage(error)}`
  } finally {
    recognizing.value = false
  }
}

async function loadDraft() {
  if (!selectedTaskId.value) {
    draft.value = null
    return
  }
  loading.value = true
  message.value = ''
  try {
    draft.value = await draftLoadingSheet(props.factoryId, selectedTaskId.value)
    if (draft.value.lines.length === 0) await recognizeContract()
    if (draft.value.lines.length === 0) addLine()
    if (!draft.value.header.contractNo && draft.value.lines[0]?.contract) {
      draft.value.header.contractNo = draft.value.lines[0].contract
    }
  } catch (error) {
    message.value = `生成柜单失败：${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

function addLine() {
  if (!draft.value) return
  draft.value.lines.push({
    id: crypto.randomUUID(), tradingCompany: 'DK', contract: draft.value.lines[0]?.contract ?? '',
    filingCode: '', declareCode: '', coefficient: null, quantity: null, cartons: null, grossWeight: null, netWeight: null,
    cbm: null, category: '塑胶', grossPerCarton: null, netPerCarton: null, description: '', department: 'W',
  })
}

function removeLine(index: number) {
  draft.value?.lines.splice(index, 1)
}

function recalcLine(line: LoadingLine) {
  const quantity = Number(line.quantity)
  const coefficient = Number(line.coefficient)
  if (!Number.isFinite(quantity) || !Number.isFinite(coefficient) || coefficient <= 0) return
  line.cartons = Math.round((quantity / coefficient) * 1000) / 1000
  if (line.grossPerCarton != null) line.grossWeight = Math.round(line.cartons * line.grossPerCarton * 1000) / 1000
  if (line.netPerCarton != null) line.netWeight = Math.round(line.cartons * line.netPerCarton * 1000) / 1000
}

function recalcWeights(line: LoadingLine) {
  const cartons = Number(line.cartons)
  if (!Number.isFinite(cartons)) return
  if (line.grossPerCarton != null) {
    line.grossWeight = Math.round(cartons * Number(line.grossPerCarton) * 1000) / 1000
  }
  if (line.netPerCarton != null) {
    line.netWeight = Math.round(cartons * Number(line.netPerCarton) * 1000) / 1000
  }
}

async function download() {
  if (!draft.value) return
  exporting.value = true
  try {
    const blob = await exportLoadingSheet(props.factoryId, {
      ...draft.value,
      lines: draft.value.lines,
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const transport = String(draft.value.header.transportCompany || '成隆达')
    const carrier = transport.endsWith('运输') ? transport : `${transport}运输`
    const port = draft.value.header.originPort || '盐田'
    const so = String(draft.value.header.soNo || '')
    link.download = `${carrier}出${port}${so ? `_${so}` : ''}.xls`
    link.click()
    URL.revokeObjectURL(url)
    emit('notify', `柜单 ${draft.value.number} 已生成并下载。`)
    await loadTasks()
  } catch (error) {
    message.value = `导出失败：${getApiErrorMessage(error)}`
  } finally {
    exporting.value = false
  }
}

onMounted(loadTasks)

watch(() => props.initialDraft, (value) => {
  if (!value) return
  draft.value = JSON.parse(JSON.stringify(value)) as LoadingDraft
  selectedTaskId.value = value.taskId
  message.value = ''
  void recognizeContract().then(() => {
    if (draft.value && draft.value.lines.length === 0) addLine()
  })
}, { immediate: true })
</script>

<template>
  <section class="space-y-4" aria-label="柜货单">
    <div class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-[16px] font-bold text-emerald-950">柜货单</h2>
          <p class="mt-0.5 text-[11px] text-slate-500">选择工厂排期生成柜货单；单号按当天顺序从 W11 起递增。</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="search"
            type="search"
            aria-label="搜索合同号或备案货号"
            placeholder="搜索合同号 / 备案货号"
            class="h-9 w-[190px] rounded-lg border border-emerald-200 bg-white px-2.5 text-[12px] text-slate-800 outline-none placeholder:text-slate-400 focus:border-emerald-500"
          >
          <select v-model="selectedTaskId" aria-label="选择工厂排期" class="h-9 max-w-[320px] rounded-lg border border-emerald-200 bg-white px-2 text-[12px]" @change="loadDraft">
            <option value="">选择工厂排期</option>
            <option v-for="task in filteredTasks" :key="task.id" :value="task.id">
              {{ task.so_number || task.id }} · {{ task.port || '-' }} · {{ task.planned_ship_date || '-' }}
            </option>
          </select>
          <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-700 px-4 text-[12px] font-semibold text-white transition hover:bg-emerald-800 disabled:opacity-60" :disabled="!draft || exporting" @click="download">
            <Download class="size-3.5" />{{ exporting ? '生成中…' : '导出柜货单' }}
          </button>
        </div>
      </div>
      <p v-if="message" class="mt-2 text-[11px] text-rose-600">{{ message }}</p>
      <p v-if="loading" class="mt-2 text-[11px] text-slate-500">正在按排期生成…</p>
    </div>

    <template v-if="draft">
      <div class="rounded-xl border border-emerald-100/80 bg-white p-4">
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label class="text-[11px] text-slate-500">柜号序列
            <input v-model="draft.header.number" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px] font-semibold" readonly>
          </label>
          <label class="text-[11px] text-slate-500">收货商（手动填写）
            <input v-model="draft.header.consignee" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">合同号
            <span class="mt-1 flex gap-1">
              <input v-model="draft.header.contractNo" class="h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]" @change="recognizeContract">
              <button type="button" class="shrink-0 rounded-lg border border-emerald-200 px-2 text-[10px] font-semibold text-emerald-700 disabled:opacity-50" :disabled="recognizing" @click="recognizeContract">
                {{ recognizing ? '识别中…' : '识别填入' }}
              </button>
            </span>
          </label>
          <label class="text-[11px] text-slate-500">航次
            <input v-model="draft.header.voyage" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">柜型
            <input v-model="draft.header.containerType" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">截数期（邮件）
            <input v-model="draft.header.cutoff" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">出港口（邮件 FROM）
            <input v-model="draft.header.originPort" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">运输公司（手动）
            <input v-model="draft.header.transportCompany" placeholder="成隆达" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">目的国家（邮件）
            <input v-model="draft.header.destinationCountry" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">制表人
            <select v-model="draft.header.preparer" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
              <option v-for="name in preparers" :key="name" :value="name">{{ name }}</option>
            </select>
          </label>
          <label class="text-[11px] text-slate-500">柜S/O
            <input v-model="draft.header.soNo" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">车牌
            <input v-model="draft.header.plate" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">柜号
            <input v-model="draft.header.containerNo" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">封条号
            <input v-model="draft.header.sealNo" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">备案货号
            <input v-model="draft.header.filingCode" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">空柜重量
            <input v-model="draft.header.tareWeight" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
        </div>
      </div>

      <div class="overflow-x-auto rounded-xl border border-emerald-100/80 bg-white">
        <table class="w-full min-w-[1180px] text-left text-[11px]">
          <thead class="bg-emerald-50 text-emerald-900/70">
            <tr>
              <th class="px-2 py-2">洋行</th><th class="px-2 py-2">合同号</th><th class="px-2 py-2">备案货号</th>
              <th class="px-2 py-2">走货申报货号</th><th class="px-2 py-2">出箱数</th><th class="px-2 py-2">数量</th><th class="px-2 py-2">件数</th>
              <th class="px-2 py-2">毛重</th><th class="px-2 py-2">净重</th><th class="px-2 py-2">体积CBM</th>
              <th class="px-2 py-2">玩具类别</th><th class="px-2 py-2">KG/箱（毛重）</th><th class="px-2 py-2">KG/箱（净重）</th>
              <th class="px-2 py-2">品名/备注</th><th class="px-2 py-2">部门</th><th class="px-2 py-2"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50">
            <tr v-for="(line, index) in draft.lines" :key="line.id">
              <td class="px-2 py-1"><input v-model="line.tradingCompany" class="h-7 w-14 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model="line.contract" class="h-7 w-40 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model="line.filingCode" class="h-7 w-28 rounded border border-emerald-100 px-1" @input="line.declareCode = line.filingCode"></td>
              <td class="px-2 py-1"><input v-model="line.declareCode" class="h-7 w-28 rounded border border-emerald-100 px-1" @input="line.filingCode = line.declareCode"></td>
              <td class="px-2 py-1"><input v-model.number="line.coefficient" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right" @input="recalcLine(line)"></td>
              <td class="px-2 py-1"><input v-model.number="line.quantity" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right" @input="recalcLine(line)"></td>
              <td class="px-2 py-1"><input v-model.number="line.cartons" type="number" class="h-7 w-16 rounded border border-emerald-100 bg-slate-50 px-1 text-right" readonly title="件数 = 数量 ÷ 出箱数"></td>
              <td class="px-2 py-1"><input v-model.number="line.grossWeight" type="number" class="h-7 w-20 rounded border border-emerald-100 bg-slate-50 px-1 text-right" readonly title="毛重 = KG/箱毛重 × 件数"></td>
              <td class="px-2 py-1"><input v-model.number="line.netWeight" type="number" class="h-7 w-20 rounded border border-emerald-100 bg-slate-50 px-1 text-right" readonly title="净重 = KG/箱净重 × 件数"></td>
              <td class="px-2 py-1"><input v-model.number="line.cbm" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model="line.category" class="h-7 w-16 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model.number="line.grossPerCarton" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right" @input="recalcWeights(line)"></td>
              <td class="px-2 py-1"><input v-model.number="line.netPerCarton" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right" @input="recalcWeights(line)"></td>
              <td class="px-2 py-1"><input v-model="line.description" class="h-7 w-40 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model="line.department" class="h-7 w-10 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1 text-center">
                <button type="button" class="text-rose-500 hover:text-rose-700" aria-label="删除明细" @click="removeLine(index)"><Trash2 class="size-3.5" /></button>
              </td>
            </tr>
            <tr class="bg-emerald-50/60 font-semibold text-emerald-950">
              <td class="px-2 py-2" colspan="4">合计</td>
              <td class="px-2 py-2"></td>
              <td class="px-2 py-2 text-right">{{ totals.quantity }}</td>
              <td class="px-2 py-2 text-right">{{ totals.cartons }}</td>
              <td class="px-2 py-2 text-right">{{ totals.grossWeight.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.netWeight.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.cbm.toFixed(2) }}</td>
              <td colspan="6"></td>
            </tr>
          </tbody>
        </table>
        <div class="p-3">
          <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 px-3 text-[12px] font-semibold text-emerald-800" @click="addLine">
            <Plus class="size-3.5" />添加明细
          </button>
        </div>
      </div>
    </template>
  </section>
</template>
