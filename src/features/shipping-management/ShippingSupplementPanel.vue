<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Download, Plus, Trash2 } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  draftSupplementSheet,
  exportSupplementSheet,
  type SupplementDraft,
  type SupplementLine,
} from '@/api/shippingMail'
import { listShippingTasks, type ShippingScheduleTask } from '@/api/shippingTasks'

const props = defineProps<{ factoryId: string }>()
const emit = defineEmits<{ notify: [message: string]; back: [] }>()

const tasks = ref<ShippingScheduleTask[]>([])
const selectedTaskId = ref('')
const draft = ref<SupplementDraft | null>(null)
const loading = ref(false)
const exporting = ref(false)
const message = ref('')

const totals = computed(() => {
  const sum = (key: keyof SupplementLine) => (draft.value?.lines ?? [])
    .reduce((total, line) => total + (Number(line[key]) || 0), 0)
  const gw = sum('gw')
  const tare = sum('tare')
  return { ctns: sum('ctns'), pallet: sum('pallet'), qty: sum('qty'), cbm: sum('cbm'), gw, tare, vgm: gw + tare }
})

const summary = computed(() => {
  const map = new Map<string, { itemNo: string; salesConf: string; pcs: number; ctns: number }>()
  for (const line of draft.value?.lines ?? []) {
    const key = `${line.itemNo}-${line.salesConf}`
    const entry = map.get(key) ?? { itemNo: line.itemNo, salesConf: line.salesConf, pcs: 0, ctns: 0 }
    entry.pcs += Number(line.qty) || 0
    entry.ctns += Number(line.ctns) || 0
    map.set(key, entry)
  }
  return [...map.values()]
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
    draft.value = await draftSupplementSheet(props.factoryId, selectedTaskId.value)
  } catch (error) {
    message.value = `生成补料单失败：${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

function recalc(line: SupplementLine) {
  if (line.cbmPerCarton != null && line.ctns != null) {
    line.cbm = Math.round(line.ctns * line.cbmPerCarton * 1000) / 1000
  }
  if (line.gwPerCarton != null && line.ctns != null) {
    line.gw = Math.round(line.ctns * line.gwPerCarton * 1000) / 1000
  }
  line.vgm = (Number(line.gw) || 0) + (Number(line.tare) || 0)
}

function addLine() {
  if (!draft.value) return
  draft.value.lines.push({
    id: crypto.randomUUID(), mixNo: '', containerNo: '', sealNo: '', size: draft.value.lines[0]?.size ?? '',
    itemNo: '', description: '', salesConf: '', po: '', ctns: null, pallet: '', qty: null,
    booking: '', deliveryDate: '', cbmPerCarton: null, cbm: null, gwPerCarton: null, gw: null,
    pack: '', tare: null, vgm: null,
  })
}

async function download() {
  if (!draft.value) return
  exporting.value = true
  try {
    const blob = await exportSupplementSheet(props.factoryId, draft.value)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${draft.value.header.to || 'PLAYMATE'}补料单.xlsx`
    link.click()
    URL.revokeObjectURL(url)
    emit('notify', '补料单已生成并下载。')
  } catch (error) {
    message.value = `导出失败：${getApiErrorMessage(error)}`
  } finally {
    exporting.value = false
  }
}

onMounted(loadTasks)
</script>

<template>
  <section class="space-y-4" aria-label="补料单">
    <div class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4">
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 class="text-[16px] font-bold text-emerald-950">补料单 / SHIPMENT ADVICE</h2>
          <p class="mt-0.5 text-[11px] text-slate-500">按船务排期生成补料单；船名、港口、ETD、箱数等来自邮件/排期，合计自动汇总。</p>
        </div>
        <button type="button" class="text-[11px] font-semibold text-emerald-800 hover:underline" @click="emit('back')">← 返回工厂排期单</button>
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <select v-model="selectedTaskId" aria-label="选择工厂排期" class="h-9 rounded-lg border border-emerald-200 bg-white px-2 text-[12px]" @change="loadDraft">
          <option value="">选择工厂排期</option>
          <option v-for="task in tasks" :key="task.id" :value="task.id">
            {{ task.so_number || task.id }} · {{ task.port || '-' }} · {{ task.planned_ship_date || '-' }}
          </option>
        </select>
        <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-700 px-4 text-[12px] font-semibold text-white disabled:opacity-60" :disabled="!draft || exporting" @click="download">
          <Download class="size-3.5" />{{ exporting ? '生成中…' : '导出补料单' }}
        </button>
      </div>
      <p v-if="message" class="mt-2 text-[11px] text-rose-600">{{ message }}</p>
      <p v-if="loading" class="mt-2 text-[11px] text-slate-500">正在生成…</p>
    </div>

    <template v-if="draft">
      <div class="rounded-xl border border-emerald-100/80 bg-white p-4">
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label class="text-[11px] text-slate-500">To
            <input v-model="draft.header.to" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">From
            <input v-model="draft.header.from" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Subject
            <input v-model="draft.header.subject" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">REF#
            <input v-model="draft.header.ref" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Date
            <input v-model="draft.header.date" type="date" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Customer / Market
            <input v-model="draft.header.customerMarket" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Name of Vessel
            <input v-model="draft.header.vessel" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Port of Loading
            <input v-model="draft.header.portOfLoading" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Port of Discharge
            <input v-model="draft.header.portOfDischarge" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">E.T.D.
            <input v-model="draft.header.etd" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Invoice No./Date
            <input v-model="draft.header.invoice" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Country of Origin
            <input v-model="draft.header.origin" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Place of receipt
            <input v-model="draft.header.receipt" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">Total no. of cartons
            <input :value="totals.ctns" readonly class="mt-1 h-9 w-full rounded-lg border border-emerald-100 bg-slate-50 px-2 text-[12px]">
          </label>
        </div>
      </div>

      <div class="overflow-x-auto rounded-xl border border-emerald-100/80 bg-white">
        <table class="w-full min-w-[1700px] text-left text-[11px]">
          <thead class="bg-emerald-50 text-emerald-900/70">
            <tr>
              <th class="px-2 py-2">No.</th><th class="px-2 py-2">Mix#</th><th class="px-2 py-2">Container#</th>
              <th class="px-2 py-2">Seal#</th><th class="px-2 py-2">Size</th><th class="px-2 py-2">Item#</th>
              <th class="px-2 py-2">Description</th><th class="px-2 py-2">Sales Conf#</th><th class="px-2 py-2">P.O. No.#</th>
              <th class="px-2 py-2">Ctns</th><th class="px-2 py-2">pallet</th><th class="px-2 py-2">Qty (Pcs)</th>
              <th class="px-2 py-2">Booking#</th><th class="px-2 py-2">Delivery Date</th><th class="px-2 py-2">cbm</th>
              <th class="px-2 py-2">G.W (kgs)</th><th class="px-2 py-2">pack (pcs)</th>
              <th class="px-2 py-2">Tare (kgs)</th><th class="px-2 py-2">VGM (kgs)</th><th></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50">
            <tr v-for="(line, index) in draft.lines" :key="line.id">
              <td class="px-1 py-1 text-center">{{ index + 1 }}</td>
              <td class="px-1 py-1"><input v-model="line.mixNo" class="h-7 w-12 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.containerNo" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.sealNo" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.size" class="h-7 w-14 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.itemNo" class="h-7 w-20 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.description" class="h-7 w-52 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.salesConf" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.po" class="h-7 w-20 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model.number="line.ctns" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model="line.pallet" class="h-7 w-10 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model.number="line.qty" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-1 py-1"><input v-model="line.booking" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.deliveryDate" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model.number="line.cbm" type="number" class="h-7 w-14 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-1 py-1"><input v-model.number="line.gw" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model="line.pack" class="h-7 w-10 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model.number="line.tare" type="number" class="h-7 w-14 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model.number="line.vgm" type="number" class="h-7 w-16 rounded border border-emerald-100 bg-slate-50 px-1 text-right" readonly></td>
              <td class="px-1 py-1 text-center">
                <button type="button" class="text-rose-500" aria-label="删除明细" @click="draft.lines.splice(index, 1)"><Trash2 class="size-3.5" /></button>
              </td>
            </tr>
            <tr class="bg-emerald-50/60 font-semibold text-emerald-950">
              <td class="px-2 py-2" colspan="9">合计</td>
              <td class="px-2 py-2 text-right">{{ totals.ctns }}</td>
              <td class="px-2 py-2 text-right">{{ totals.pallet }}</td>
              <td class="px-2 py-2 text-right">{{ totals.qty }}</td>
              <td colspan="2"></td>
              <td class="px-2 py-2 text-right">{{ totals.cbm.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.gw.toFixed(2) }}</td>
              <td></td>
              <td class="px-2 py-2 text-right">{{ totals.tare.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.vgm.toFixed(2) }}</td>
              <td></td>
            </tr>
          </tbody>
        </table>
        <div class="p-3">
          <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 px-3 text-[12px] font-semibold text-emerald-800" @click="addLine">
            <Plus class="size-3.5" />添加明细
          </button>
        </div>
      </div>

      <div v-if="summary.length" class="rounded-xl border border-emerald-100/80 bg-white p-4">
        <h3 class="text-[13px] font-bold text-slate-800">Item 汇总</h3>
        <table class="mt-2 w-full max-w-2xl text-left text-[11px]">
          <thead class="bg-slate-50 text-slate-500">
            <tr><th class="px-2 py-1.5">Item#</th><th class="px-2 py-1.5 text-right">Pcs</th><th class="px-2 py-1.5 text-right">Ctns</th><th class="px-2 py-1.5">Sales Conf#</th></tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="entry in summary" :key="`${entry.itemNo}-${entry.salesConf}`">
              <td class="px-2 py-1.5 font-semibold text-slate-800">{{ entry.itemNo }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ entry.pcs }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ entry.ctns }}</td>
              <td class="px-2 py-1.5">{{ entry.salesConf }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>
