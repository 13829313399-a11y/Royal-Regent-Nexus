<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Download, Plus, Trash2 } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  draftZuruSheet,
  exportZuruSheet,
  type ZuruDraft,
  type ZuruLine,
} from '@/api/shippingMail'
import { listShippingTasks, type ShippingScheduleTask } from '@/api/shippingTasks'

const props = defineProps<{ factoryId: string; initialDraft?: ZuruDraft | null }>()
const emit = defineEmits<{ notify: [message: string] }>()

const tasks = ref<ShippingScheduleTask[]>([])
const selectedTaskId = ref('')
const search = ref('')
const draft = ref<ZuruDraft | null>(null)
const loading = ref(false)
const exporting = ref(false)
const message = ref('')

const filteredTasks = computed(() => {  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return tasks.value
  return tasks.value.filter((task) => [
    task.so_number, task.customer, task.port, task.planned_ship_date, task.id,
  ].some((value) => String(value || '').toLowerCase().includes(keyword)))
})

const selectedTask = computed(() => tasks.value.find((task) => task.id === selectedTaskId.value) ?? null)
const scheduleProducts = computed(() => selectedTask.value?.items ?? [])

const toText = computed({
  get: () => draft.value?.header.toNames.join('、') ?? '',
  set: (value: string) => {
    if (draft.value) draft.value.header.toNames = value.split(/[、,，/]/).map((item) => item.trim()).filter(Boolean)
  },
})

const totals = computed(() => {
  const sum = (key: keyof ZuruLine) => (draft.value?.lines ?? [])
    .reduce((total, line) => total + (Number(line[key]) || 0), 0)
  return {
    quantity: sum('quantity'), cartons: sum('cartons'), grossWeight: sum('grossWeight'),
    netWeight: sum('netWeight'), cbm: sum('cbm'),
  }
})

async function loadTasks() {
  try {
    tasks.value = await listShippingTasks(props.factoryId)
  } catch (error) {
    message.value = `无法读取工厂排期：${getApiErrorMessage(error)}`
  }
}

async function loadDraft() {
  if (!selectedTaskId.value) { draft.value = null; return }
  loading.value = true
  message.value = ''
  try {
    draft.value = await draftZuruSheet(props.factoryId, selectedTaskId.value)
    ensureEditableLine()
  } catch (error) {
    message.value = `生成失败：${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

function blankLine(): ZuruLine {
  return {
    id: crypto.randomUUID(), tradingHouse: '', contract: '', filingCode: '', declareCode: '', brand: '',
    coefficient: null, quantity: null, cartons: null, grossWeight: null, netWeight: null, cbm: null,
    cbmPerCarton: null, country: draft.value?.header.destinationCountry ?? '', grossPerCarton: null,
    netPerCarton: null, remark: '', po: '',
  }
}

function ensureEditableLine() {
  if (draft.value && draft.value.lines.length === 0) draft.value.lines.push(blankLine())
}

function addLine() {
  if (!draft.value) return
  draft.value.lines.push(blankLine())
}

function addScheduleProduct(index: number) {
  if (!draft.value) return
  const item = scheduleProducts.value[index]
  if (!item) return
  const quantity = Number(item.quantity) || null
  const cartons = Number(item.cartons) || null
  const coefficient = Number(item.coefficient) || (quantity && cartons ? quantity / cartons : null)
  draft.value.lines.push({
    id: crypto.randomUUID(),
    tradingHouse: '',
    contract: String(item.contract_no || ''),
    filingCode: String(item.product_code || ''),
    declareCode: String(item.product_code || ''),
    brand: '',
    coefficient,
    quantity,
    cartons,
    grossWeight: Number(item.gross_weight) || null,
    netWeight: Number(item.net_weight) || null,
    cbm: Number(item.cbm) || null,
    cbmPerCarton: null,
    country: draft.value.header.destinationCountry,
    grossPerCarton: cartons && Number(item.gross_weight) ? Number(item.gross_weight) / cartons : null,
    netPerCarton: cartons && Number(item.net_weight) ? Number(item.net_weight) / cartons : null,
    remark: '',
    po: String(item.customer_po || ''),
  })
}

function onScheduleProductChange(event: Event) {
  const select = event.target as HTMLSelectElement
  const index = Number(select.value)
  select.value = ''
  if (Number.isFinite(index)) addScheduleProduct(index)
}

function recalc(line: ZuruLine) {
  const cartons = Number(line.cartons)
  if (!Number.isFinite(cartons)) return
  if (line.coefficient != null) line.quantity = Math.round(cartons * line.coefficient * 1000) / 1000
  if (line.grossPerCarton != null) line.grossWeight = Math.round(cartons * line.grossPerCarton * 1000) / 1000
  if (line.netPerCarton != null) line.netWeight = Math.round(cartons * line.netPerCarton * 1000) / 1000
}

async function download() {
  if (!draft.value) return
  exporting.value = true
  try {
    const blob = await exportZuruSheet(props.factoryId, draft.value)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const transport = String(draft.value.header.transportCompany || '建联派')
    const carrier = transport.endsWith('运输') ? transport : `${transport}运输`
    const port = draft.value.header.originPort || '盐田'
    const so = String(draft.value.header.soNo || '')
    link.download = `${carrier}出${port}${so ? `_${so}` : ''}.xlsx`
    link.click()
    URL.revokeObjectURL(url)
    emit('notify', `柜货单 ${draft.value.header.number} 已下载。`)
  } catch (error) {
    message.value = `导出失败：${getApiErrorMessage(error)}`
  } finally {
    exporting.value = false
  }
}

onMounted(loadTasks)

watch(() => props.initialDraft, (value) => {
  if (!value) return
  draft.value = JSON.parse(JSON.stringify(value)) as ZuruDraft
  ensureEditableLine()
  selectedTaskId.value = value.taskId
  message.value = ''
}, { immediate: true })
</script>

<template>
  <section class="space-y-4" aria-label="ZURU柜货单">
    <div class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-[16px] font-bold text-emerald-950">柜货单</h2>
          <p class="mt-0.5 text-[11px] text-slate-500">按 ZURU 盐田柜货模板生成；数量 = 箱数 × 装箱数，毛重/净重 = 每箱重量 × 箱数。</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="search"
            type="search"
            aria-label="搜索工厂排期"
            placeholder="搜索 SO / 客户 / 港口"
            class="h-9 w-[190px] rounded-lg border border-emerald-200 bg-white px-2.5 text-[12px] text-slate-800 outline-none placeholder:text-slate-400 focus:border-emerald-500"
          >
          <select v-model="selectedTaskId" aria-label="选择工厂排期" class="h-9 max-w-[320px] rounded-lg border border-emerald-200 bg-white px-2 text-[12px]" @change="loadDraft">
            <option value="">选择工厂排期</option>
            <option v-for="task in filteredTasks" :key="task.id" :value="task.id">
              {{ task.so_number || task.id }} · {{ task.port || '-' }} · {{ task.planned_ship_date || '-' }}
            </option>
          </select>
          <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-700 px-4 text-[12px] font-semibold text-white disabled:opacity-60" :disabled="!draft || exporting" @click="download">
            <Download class="size-3.5" />{{ exporting ? '生成中…' : '导出柜货单' }}
          </button>
        </div>
      </div>
      <p v-if="message" class="mt-2 text-[11px] text-rose-600">{{ message }}</p>
      <p v-if="loading" class="mt-2 text-[11px] text-slate-500">正在生成…</p>
    </div>

    <template v-if="draft">
      <div class="overflow-hidden rounded-xl border border-emerald-100/80 bg-white">
        <div class="p-4">
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label class="text-[11px] text-slate-500">TO（收件人）
            <input v-model="toText" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">FROM（发件人）
            <input v-model="draft.header.fromName" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">制表日期
            <input v-model="draft.header.sheetDate" type="date" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">到货截止日期（邮件）
            <input v-model="draft.header.cutoff" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">车头注明（柜号）
            <input v-model="draft.header.number" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">柜S/O（邮件）
            <input v-model="draft.header.soNo" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">船名航次（邮件）
            <input v-model="draft.header.vesselVoyage" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">提单号（邮件）
            <input v-model="draft.header.blNo" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">运输公司（手动）
            <input v-model="draft.header.transportCompany" placeholder="建联派" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">柜型（邮件）
            <input v-model="draft.header.containerType" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">成交方式
            <select v-model="draft.header.tradeTerm" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
              <option value="FOB">FOB</option>
              <option value="EXW">EXW</option>
            </select>
          </label>
          <label class="text-[11px] text-slate-500">出口国家（邮件）
            <input v-model="draft.header.destinationCountry" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
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
          <label class="text-[11px] text-slate-500">柜重
            <input v-model="draft.header.tareWeight" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
        </div>
        </div>

        <div class="overflow-x-auto border-t border-emerald-100">
        <table class="w-full min-w-[1320px] text-left text-[11px]">
          <thead class="bg-emerald-50 text-emerald-900/70">
            <tr>
              <th class="px-2 py-2">序号</th><th class="px-2 py-2">洋行</th><th class="px-2 py-2">合约</th>
              <th class="px-2 py-2">工厂备案货号</th><th class="px-2 py-2">出货申报货号</th><th class="px-2 py-2">品牌</th>
              <th class="px-2 py-2">装箱数</th><th class="px-2 py-2">数量</th><th class="px-2 py-2">箱数</th>
              <th class="px-2 py-2">毛重</th><th class="px-2 py-2">净重</th><th class="px-2 py-2">CBM</th>
              <th class="px-2 py-2">出口国家</th><th class="px-2 py-2">每箱毛重</th><th class="px-2 py-2">每箱净重</th><th class="px-2 py-2">每箱体积</th>
              <th class="px-2 py-2">备注</th><th class="px-2 py-2">PO</th><th class="px-2 py-2"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50">
            <tr v-for="(line, index) in draft.lines" :key="line.id">
              <td class="px-2 py-1 text-center">{{ index + 1 }}</td>
              <td class="px-2 py-1"><input v-model="line.tradingHouse" class="h-7 w-16 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model="line.contract" class="h-7 w-36 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model="line.filingCode" class="h-7 w-28 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model="line.declareCode" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model="line.brand" class="h-7 w-32 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model.number="line.coefficient" type="number" class="h-7 w-14 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model.number="line.quantity" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model.number="line.cartons" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-2 py-1"><input v-model.number="line.grossWeight" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model.number="line.netWeight" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model.number="line.cbm" type="number" class="h-7 w-14 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model="line.country" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model.number="line.grossPerCarton" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model.number="line.netPerCarton" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model.number="line.cbmPerCarton" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model="line.remark" class="h-7 w-28 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model="line.po" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1 text-center">
                <button type="button" class="text-rose-500" aria-label="删除明细" @click="draft.lines.splice(index, 1)"><Trash2 class="size-3.5" /></button>
              </td>
            </tr>
            <tr class="bg-emerald-50/60 font-semibold text-emerald-950">
              <td class="px-2 py-2" colspan="6">合计</td>
              <td class="px-2 py-2"></td>
              <td class="px-2 py-2 text-right">{{ totals.quantity }}</td>
              <td class="px-2 py-2 text-right">{{ totals.cartons }}</td>
              <td class="px-2 py-2 text-right">{{ totals.grossWeight.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.netWeight.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.cbm.toFixed(2) }}</td>
              <td colspan="7"></td>
            </tr>
          </tbody>
        </table>
        <div class="flex flex-wrap items-center gap-2 p-3">
          <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 px-3 text-[12px] font-semibold text-emerald-800" @click="addLine">
            <Plus class="size-3.5" />添加明细
          </button>
          <select
            v-if="scheduleProducts.length"
            class="h-8 max-w-[320px] rounded-lg border border-emerald-200 bg-white px-2 text-[11px] text-emerald-900"
            aria-label="从工厂排期添加产品编号"
            @change="onScheduleProductChange"
          >
            <option value="">从工厂排期添加产品编号</option>
            <option v-for="(item, index) in scheduleProducts" :key="`${item.product_code}-${index}`" :value="index">
              {{ item.product_code || '未命名货号' }} · {{ item.product_name || '' }} · {{ item.quantity ?? 0 }} pcs
            </option>
          </select>
        </div>
      </div>
      </div>
    </template>
  </section>
</template>
