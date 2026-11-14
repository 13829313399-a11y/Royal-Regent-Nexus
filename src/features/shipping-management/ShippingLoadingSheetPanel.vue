<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Download, Plus, Trash2 } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  draftLoadingSheet,
  exportLoadingSheet,
  type LoadingDraft,
  type LoadingLine,
} from '@/api/shippingMail'
import { listShippingTasks, type ShippingScheduleTask } from '@/api/shippingTasks'

const props = defineProps<{ factoryId: string }>()
const emit = defineEmits<{ notify: [message: string] }>()

const tasks = ref<ShippingScheduleTask[]>([])
const selectedTaskId = ref('')
const draft = ref<LoadingDraft | null>(null)
const loading = ref(false)
const exporting = ref(false)
const message = ref('')

const preparers = ['农建壮', '小美']

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
    tasks.value = await listShippingTasks(props.factoryId)
  } catch (error) {
    message.value = `无法读取工厂排期：${getApiErrorMessage(error)}`
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
    cbm: null, category: '', grossPerCarton: null, netPerCarton: null, description: '', department: 'W',
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
    link.download = `${draft.value.header.originPort || '待定港口'}SO出货表.xls`
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
</script>

<template>
  <section class="space-y-4" aria-label="装柜单">
    <div class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-[16px] font-bold text-emerald-950">装柜单</h2>
          <p class="mt-0.5 text-[11px] text-slate-500">选择工厂排期生成 DK 柜单；单号按当天顺序从 W11 起递增。</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <select v-model="selectedTaskId" aria-label="选择工厂排期" class="h-9 rounded-lg border border-emerald-200 bg-white px-2 text-[12px]" @change="loadDraft">
            <option value="">选择工厂排期</option>
            <option v-for="task in tasks" :key="task.id" :value="task.id">
              {{ task.so_number || task.id }} · {{ task.port || '-' }} · {{ task.planned_ship_date || '-' }}
            </option>
          </select>
          <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-700 px-4 text-[12px] font-semibold text-white transition hover:bg-emerald-800 disabled:opacity-60" :disabled="!draft || exporting" @click="download">
            <Download class="size-3.5" />{{ exporting ? '生成中…' : '导出柜单 Excel' }}
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
          <label class="text-[11px] text-slate-500">柜S/O
            <input v-model="draft.header.soNo" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
          <label class="text-[11px] text-slate-500">船名
            <input v-model="draft.header.vessel" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
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
          <label class="text-[11px] text-slate-500">品牌备注（手动）
            <input v-model="draft.header.brandNote" placeholder="DICKIE TOYS" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
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
          <label class="text-[11px] text-slate-500">空柜重量
            <input v-model="draft.header.tareWeight" class="mt-1 h-9 w-full rounded-lg border border-emerald-100 px-2 text-[12px]">
          </label>
        </div>
      </div>

      <div class="overflow-x-auto rounded-xl border border-emerald-100/80 bg-white">
        <table class="w-full min-w-[1180px] text-left text-[11px]">
          <thead class="bg-emerald-50 text-emerald-900/70">
            <tr>
              <th class="px-2 py-2">洋行</th><th class="px-2 py-2">合同</th><th class="px-2 py-2">备案货号</th>
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
              <td class="px-2 py-1"><input v-model="line.filingCode" class="h-7 w-28 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model="line.declareCode" class="h-7 w-28 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model.number="line.coefficient" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right" @input="recalcLine(line)"></td>
              <td class="px-2 py-1"><input v-model.number="line.quantity" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right" @input="recalcLine(line)"></td>
              <td class="px-2 py-1"><input v-model.number="line.cartons" type="number" class="h-7 w-16 rounded border border-emerald-100 bg-slate-50 px-1 text-right" readonly title="件数 = 数量 ÷ 出箱数"></td>
              <td class="px-2 py-1"><input v-model.number="line.grossWeight" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model.number="line.netWeight" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model.number="line.cbm" type="number" class="h-7 w-16 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model="line.category" class="h-7 w-16 rounded border border-emerald-100 px-1"></td>
              <td class="px-2 py-1"><input v-model.number="line.grossPerCarton" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right"></td>
              <td class="px-2 py-1"><input v-model.number="line.netPerCarton" type="number" class="h-7 w-20 rounded border border-emerald-100 px-1 text-right"></td>
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
