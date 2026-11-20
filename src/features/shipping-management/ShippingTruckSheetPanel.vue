<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Download, Plus, Trash2 } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  draftTruckSheet,
  exportTruckSheet,
  searchScheduleProducts,
  type TruckDraft,
  type TruckLine,
} from '@/api/shippingMail'
import { listShippingTasks, type ShippingScheduleTask } from '@/api/shippingTasks'
import ShippingTruckExportHistory from './ShippingTruckExportHistory.vue'

const props = defineProps<{ factoryId: string; initialTaskId?: string }>()
const emit = defineEmits<{ notify: [message: string]; back: [] }>()

const tasks = ref<ShippingScheduleTask[]>([])
const selectedTaskId = ref('')
const search = ref('')
const searchField = ref<'all' | 'contract' | 'filing'>('all')
const searching = ref(false)
const historyVersion = ref(0)
const draft = ref<TruckDraft | null>(null)
const loading = ref(false)
const exporting = ref(false)
const message = ref('')

const totals = computed(() => {
  const sum = (key: keyof TruckLine) => (draft.value?.lines ?? [])
    .reduce((total, line) => total + (Number(line[key]) || 0), 0)
  return {
    quantity: sum('quantity'), pieces: sum('pieces'), grossWeight: sum('grossWeight'),
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
    draft.value = await draftTruckSheet(props.factoryId, selectedTaskId.value)
  } catch (error) {
    message.value = `生成车货表失败：${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

function addLine() {
  if (!draft.value) return
  draft.value.lines.push({
    id: crypto.randomUUID(), department: '', tradingHouse: 'Buzzbee', contract: '', filingCode: '',
    declareCode: '', name: '', country: draft.value.lines[0]?.country ?? '', category: '',
    quantity: null, coefficient: null, pieces: null, grossWeight: null, netWeight: null, cbm: null,
    cartonMark: '', totalCartons: '', grossPerCarton: null, netPerCarton: null, remark: '',
  })
}

function recalc(line: TruckLine) {
  const quantity = Number(line.quantity)
  const coefficient = Number(line.coefficient)
  if (!Number.isFinite(quantity) || !Number.isFinite(coefficient) || coefficient <= 0) return
  line.pieces = Math.round((quantity / coefficient) * 1000) / 1000
  if (line.grossPerCarton != null) line.grossWeight = Math.round(line.pieces * line.grossPerCarton * 1000) / 1000
  if (line.netPerCarton != null) line.netWeight = Math.round(line.pieces * line.netPerCarton * 1000) / 1000
}

async function runSearch() {
  const query = search.value.trim()
  if (!query) return
  searching.value = true
  message.value = ''
  try {
    const items = await searchScheduleProducts(props.factoryId, query)
    if (!draft.value) {
      message.value = '请先选择工厂排期'
      return
    }
    let added = 0
    for (const item of items) {
      const code = String(item.product_code || '').trim()
      if (!code) continue
      const cartons = Number(item.cartons) || 0
      const mapped: TruckLine = {
        id: crypto.randomUUID(),
        department: 'DK',
        tradingHouse: 'Buzzbee',
        contract: String(item.contract_no || ''),
        filingCode: code,
        declareCode: code,
        name: String(item.product_name || ''),
        country: String(item.country || draft.value.lines[0]?.country || ''),
        category: '',
        quantity: Number(item.quantity) || 0,
        coefficient: Number(item.coefficient) || (cartons ? (Number(item.quantity) || 0) / cartons : null),
        pieces: cartons,
        grossWeight: Number(item.gross_weight) || 0,
        netWeight: Number(item.net_weight) || 0,
        cbm: Number(item.cbm) || 0,
        cartonMark: '',
        totalCartons: String(cartons || ''),
        grossPerCarton: cartons && item.gross_weight ? Number(item.gross_weight) / cartons : null,
        netPerCarton: cartons && item.net_weight ? Number(item.net_weight) / cartons : null,
        remark: '',
      }
      const blankIndex = draft.value.lines.findIndex((line) => !line.filingCode?.trim() && (line.quantity == null || Number(line.quantity) === 0))
      if (blankIndex >= 0) {
        const blank = draft.value.lines[blankIndex]!
        draft.value.lines.splice(blankIndex, 1, { ...mapped, id: blank.id })
      } else {
        draft.value.lines.push(mapped)
      }
      added += 1
    }
    message.value = added ? `已找到备案号 ${query} 并填入 ${added} 行` : `未找到备案号 ${query} 对应的业务排期`
  } catch (error) {
    message.value = `搜索失败：${getApiErrorMessage(error)}`
  } finally {
    searching.value = false
  }
}

async function download() {
  if (!draft.value) return
  exporting.value = true
  try {
    const blob = await exportTruckSheet(props.factoryId, draft.value)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${draft.value.header.tableName || '客上车'}.xls`
    link.click()
    URL.revokeObjectURL(url)
    emit('notify', `已生成 ${draft.value.header.tableName} 车货表。`)
    historyVersion.value += 1
  } catch (error) {
    message.value = `导出失败：${getApiErrorMessage(error)}`
  } finally {
    exporting.value = false
  }
}

onMounted(loadTasks)
watch(() => props.initialTaskId, (taskId) => {
  if (!taskId) return
  selectedTaskId.value = taskId
  void loadDraft()
}, { immediate: true })
</script>

<template>
  <section class="space-y-4" aria-label="车的出货单">
    <div class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4">
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 class="text-[16px] font-bold text-emerald-950">车的出货单</h2>
          <p class="mt-0.5 text-[11px] text-slate-500">盐田仓 CFS 客上车（B 线车货）；W 车次手动填写，表格按 CFS + 车次命名。</p>
        </div>
        <button type="button" class="text-[13px] font-semibold text-emerald-800 hover:underline" @click="emit('back')">← 返回工厂排期单</button>
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <select v-model="searchField" aria-label="搜索字段" class="h-9 rounded-lg border border-emerald-200 bg-white px-2 text-[12px]">
          <option value="all">全部</option>
          <option value="contract">合同号</option>
          <option value="filing">备案货号</option>
        </select>
        <input
          v-model="search"
          type="search"
          aria-label="搜索合同号或备案货号"
          placeholder="搜索合同号 / 备案货号"
          class="h-9 w-[200px] rounded-lg border border-emerald-200 bg-white px-2.5 text-[12px]"
          @keyup.enter="runSearch"
        >
        <button type="button" class="h-9 rounded-lg bg-emerald-700 px-3 text-[12px] font-semibold text-white disabled:opacity-60" :disabled="searching" @click="runSearch">{{ searching ? '搜索中…' : '搜索' }}</button>
        <select v-model="selectedTaskId" aria-label="选择工厂排期" class="h-9 rounded-lg border border-emerald-200 bg-white px-2 text-[12px]" @change="loadDraft">
          <option value="">选择工厂排期</option>
          <option v-for="task in tasks" :key="task.id" :value="task.id">
            {{ task.so_number || task.id }} · {{ task.port || '-' }} · {{ task.planned_ship_date || '-' }}
          </option>
        </select>
        <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-700 px-4 text-[12px] font-semibold text-white disabled:opacity-60" :disabled="!draft || exporting" @click="download">
          <Download class="size-3.5" />{{ exporting ? '生成中…' : '导出车货表 Excel' }}
        </button>
      </div>
      <p v-if="message" class="mt-2 text-[11px] text-rose-600">{{ message }}</p>
      <p v-if="loading" class="mt-2 text-[11px] text-slate-500">正在生成…</p>
    </div>

    <template v-if="draft">
      <div class="rounded-xl border border-emerald-100/80 bg-white p-4">
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label class="text-[11px] text-slate-500">收货商（手动）
            <input v-model="draft.header.consignee" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">参考号（手动）
            <input v-model="draft.header.reference" placeholder="PXR8V6T2F2ZD" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">车次（手动）
            <input v-model="draft.header.vehicle" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">CFS / 发车说明（邮件）
            <input v-model="draft.header.cfs" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">成交方式
            <select v-model="draft.header.tradeTerm" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
              <option value="EXW">EXW</option>
              <option value="FOB">FOB</option>
            </select>
          </label>
          <label class="text-[11px] text-slate-500">拼车信息（手动）
            <input v-model="draft.header.consolidator" placeholder="华兴与新际拼车" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">装车/交仓（手动）
            <input v-model="draft.header.scheduleText" placeholder="2/26装车，2/27交仓" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">品牌备注（手动）
            <input v-model="draft.header.brandNote" placeholder="1票ADVENTURE FORCE品牌" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">车牌
            <input v-model="draft.header.plate" placeholder="粤BE7959" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">截数期（邮件）
            <input v-model="draft.header.cutoff" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">表格名称
            <input v-model="draft.header.tableName" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
        </div>
      </div>

      <div class="overflow-x-auto rounded-xl border border-emerald-100/80 bg-white">
        <table class="w-full min-w-[1500px] text-left text-[11px]">
          <thead class="bg-emerald-50 text-emerald-900/70">
            <tr>
              <th class="px-2 py-2">部门</th><th class="px-2 py-2">序号</th><th class="px-2 py-2">洋行</th>
              <th class="px-2 py-2">合同</th><th class="px-2 py-2">备案货号</th><th class="px-2 py-2">走货申报货号</th>
              <th class="px-2 py-2">货名</th><th class="px-2 py-2">国家</th><th class="px-2 py-2">玩具类别</th>
              <th class="px-2 py-2">数量</th><th class="px-2 py-2">出箱数</th><th class="px-2 py-2">件数</th>
              <th class="px-2 py-2">毛重</th><th class="px-2 py-2">净重</th><th class="px-2 py-2">体积CBM</th>
              <th class="px-2 py-2">箱唛</th><th class="px-2 py-2">每单总件数</th>
              <th class="px-2 py-2">每箱毛重</th><th class="px-2 py-2">每箱净重</th><th class="px-2 py-2">备注</th><th></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50">
            <tr v-for="(line, index) in draft.lines" :key="line.id">
              <td class="px-1 py-1"><input v-model="line.department" class="h-7 w-9 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1 text-center">{{ index + 1 }}</td>
              <td class="px-1 py-1"><input v-model="line.tradingHouse" class="h-7 w-16 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.contract" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.filingCode" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.declareCode" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.name" class="h-7 w-36 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.country" class="h-7 w-16 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.category" class="h-7 w-14 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model.number="line.quantity" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model.number="line.coefficient" type="number" class="h-7 w-14 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model.number="line.pieces" type="number" class="h-7 w-14 rounded border border-emerald-100 bg-slate-50 px-1 text-right" readonly></td>
              <td class="px-1 py-1"><input v-model.number="line.grossWeight" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-1 py-1"><input v-model.number="line.netWeight" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-1 py-1"><input v-model.number="line.cbm" type="number" class="h-7 w-12 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-1 py-1"><input v-model="line.cartonMark" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model="line.totalCartons" class="h-7 w-16 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1"><input v-model.number="line.grossPerCarton" type="number" class="h-7 w-14 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model.number="line.netPerCarton" type="number" class="h-7 w-14 rounded border border-emerald-100 px-1 text-right" @input="recalc(line)"></td>
              <td class="px-1 py-1"><input v-model="line.remark" class="h-7 w-24 rounded border border-emerald-100 px-1"></td>
              <td class="px-1 py-1 text-center">
                <button type="button" class="text-rose-500" aria-label="删除明细" @click="draft.lines.splice(index, 1)"><Trash2 class="size-3.5" /></button>
              </td>
            </tr>
            <tr class="bg-emerald-50/60 font-semibold text-emerald-950">
              <td class="px-2 py-2" colspan="9">合计</td>
              <td class="px-2 py-2 text-right">{{ totals.quantity }}</td>
              <td class="px-2 py-2"></td>
              <td class="px-2 py-2 text-right">{{ totals.pieces }}</td>
              <td class="px-2 py-2 text-right">{{ totals.grossWeight.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.netWeight.toFixed(2) }}</td>
              <td class="px-2 py-2 text-right">{{ totals.cbm.toFixed(2) }}</td>
              <td colspan="5"></td>
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

    <ShippingTruckExportHistory :factory-id="factoryId" :refresh-key="historyVersion" @notify="emit('notify', $event)" />
  </section>
</template>
