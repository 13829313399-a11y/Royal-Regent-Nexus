<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Download, Plus, RefreshCw, Trash2 } from '@lucide/vue'

type GroupKey = 'ownCabinet' | 'toOutsource' | 'fromOutsource' | 'borui' | 'stock'

interface PalletRow {
  id: string
  date: string
  so: string
  code: string
  name: string
  contract: string
  po: string
  pieces: number
  boards: number
  factory: string
  category: string
}

const groups: Array<{
  key: GroupKey
  title: string
  head: string
  border: string
  hasAdd: boolean
  hasAction: boolean
  showPo: boolean
}> = [
  { key: 'ownCabinet', title: '本厂做柜卡板（兴信做柜）', head: 'bg-blue-50 text-blue-900', border: 'border-blue-200', hasAdd: false, hasAction: false, showPo: true },
  { key: 'toOutsource', title: '送外厂卡板（兴信→外厂拼柜）', head: 'bg-amber-50 text-amber-900', border: 'border-amber-200', hasAdd: false, hasAction: false, showPo: true },
  { key: 'fromOutsource', title: '外厂送来卡板（外厂→兴信拼柜）', head: 'bg-emerald-50 text-emerald-900', border: 'border-emerald-200', hasAdd: false, hasAction: false, showPo: true },
  { key: 'borui', title: '送博锐手填', head: 'bg-rose-50 text-rose-900', border: 'border-rose-200', hasAdd: true, hasAction: true, showPo: false },
  { key: 'stock', title: '送库有手填', head: 'bg-emerald-50 text-emerald-900', border: 'border-emerald-200', hasAdd: true, hasAction: true, showPo: false },
]

const rows = reactive<Record<GroupKey, PalletRow[]>>({
  ownCabinet: [],
  toOutsource: [],
  fromOutsource: [],
  borui: [],
  stock: [],
})

const filters = reactive({ month: '2026-10', from: '2026-10-01', to: '2026-10-31', factory: '全部', category: '全部' })
const factories = ['全部', '兴信', '华兴', '华登', '华康A', '华康B', '华康D']
const categories = ['全部', '做柜', '拼柜', '手填']
const lastUpdated = ref('')
const refreshing = ref(false)

function filtered(key: GroupKey) {
  return rows[key].filter((row) => {
    if (filters.from && row.date < filters.from) return false
    if (filters.to && row.date > filters.to) return false
    if (filters.factory !== '全部' && row.factory !== filters.factory) return false
    if (filters.category !== '全部' && row.category !== filters.category) return false
    return true
  })
}

function subtotal(key: GroupKey) {
  return filtered(key).reduce((sum, row) => sum + row.boards, 0)
}

const kpis = computed(() => [
  { label: '本厂做柜卡板数', value: subtotal('ownCabinet') },
  { label: '送外厂卡板数', value: subtotal('toOutsource') },
  { label: '外厂送来卡板数', value: subtotal('fromOutsource') },
  { label: '总卡板数', value: groups.reduce((sum, group) => sum + subtotal(group.key), 0) },
])

function showTable(key: GroupKey) {
  return filtered(key).length > 0 || (key !== 'toOutsource' && key !== 'fromOutsource')
}

function addRow(key: GroupKey) {
  rows[key].push({
    id: crypto.randomUUID(),
    date: `${filters.month}-01`,
    so: '',
    code: '',
    name: '',
    contract: '',
    po: '',
    pieces: 0,
    boards: 0,
    factory: filters.factory === '全部' ? '兴信' : filters.factory,
    category: '手填',
  })
}

function removeRow(key: GroupKey, id: string) {
  rows[key] = rows[key].filter((row) => row.id !== id)
}

function refresh() {
  refreshing.value = true
  lastUpdated.value = new Date().toLocaleString('zh-CN', { hour12: false })
  window.setTimeout(() => { refreshing.value = false }, 400)
}

function exportExcel() {
  const esc = (value: unknown) => String(value ?? '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c] || c))
  const html = `<html><head><meta charset="utf-8"></head><body><h2>卡板统计 ${esc(filters.month)}</h2>`
    + `<p>${kpis.value.map((kpi) => `${esc(kpi.label)}：${kpi.value}`).join('　')}</p>`
    + groups.map((group) => {
      const list = filtered(group.key)
      return `<h3>${esc(group.title)}（小计 ${subtotal(group.key)}）</h3><table border="1"><tr><th>时间</th><th>SO号</th><th>货号</th><th>货名</th><th>合同号</th>${group.showPo ? '<th>客PO</th>' : ''}<th>件数</th><th>卡板数</th></tr>`
        + list.map((row) => `<tr><td>${esc(row.date)}</td><td>${esc(row.so)}</td><td>${esc(row.code)}</td><td>${esc(row.name)}</td><td>${esc(row.contract)}</td>${group.showPo ? `<td>${esc(row.po)}</td>` : ''}<td>${row.pieces}</td><td>${row.boards}</td></tr>`).join('')
        + '</table>'
    }).join('')
    + '</body></html>'
  const blob = new Blob(['\ufeff', html], { type: 'application/vnd.ms-excel' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `卡板统计_${filters.month || '全部'}.xls`
  link.click()
  URL.revokeObjectURL(link.href)
}
</script>

<template>
  <section class="space-y-4" aria-label="卡板统计">
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-[18px] font-bold text-slate-900">卡板统计</h2>
        <div class="flex items-center gap-2">
          <span v-if="lastUpdated" class="text-[10px] text-slate-400">刷新：{{ lastUpdated }}</span>
          <button type="button" class="inline-flex h-8 items-center gap-1 rounded bg-blue-500 px-3 text-[11px] font-semibold text-white" @click="refresh">
            <RefreshCw class="size-3.5" :class="refreshing ? 'animate-spin' : ''" />刷新
          </button>
          <button type="button" class="inline-flex h-8 items-center gap-1 rounded bg-green-500 px-3 text-[11px] font-semibold text-white" @click="exportExcel">
            <Download class="size-3.5" />导出 Excel
          </button>
        </div>
      </div>

      <div class="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-slate-600">
        <label class="flex items-center gap-2">月份
          <input v-model="filters.month" type="month" class="h-8 rounded border border-slate-200 px-2 text-[11px]">
        </label>
        <label class="flex items-center gap-2">日期范围
          <input v-model="filters.from" type="date" class="h-8 rounded border border-slate-200 px-2 text-[11px]">
          <span class="text-slate-400">~</span>
          <input v-model="filters.to" type="date" class="h-8 rounded border border-slate-200 px-2 text-[11px]">
        </label>
        <label class="flex items-center gap-2">工厂
          <select v-model="filters.factory" class="h-8 w-32 rounded border border-slate-200 px-2 text-[11px]">
            <option v-for="item in factories" :key="item">{{ item }}</option>
          </select>
        </label>
        <label class="flex items-center gap-2">分类
          <select v-model="filters.category" class="h-8 w-32 rounded border border-slate-200 px-2 text-[11px]">
            <option v-for="item in categories" :key="item">{{ item }}</option>
          </select>
        </label>
      </div>

      <div class="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div v-for="kpi in kpis" :key="kpi.label" class="px-1">
          <p class="text-[11px] text-slate-500">{{ kpi.label }}</p>
          <p class="mt-1 text-[24px] font-semibold tabular-nums text-slate-900">{{ kpi.value }}</p>
        </div>
      </div>
    </div>

    <div v-for="group in groups" :key="group.key" class="overflow-hidden rounded-lg border" :class="group.border">
      <div class="flex items-center justify-between px-4 py-2 text-[12px] font-semibold" :class="group.head">
        <span>{{ group.title }}</span>
        <div class="flex items-center gap-2">
          <span>小计：{{ subtotal(group.key) }} 卡板</span>
          <button v-if="group.hasAdd" type="button" class="inline-flex h-7 items-center gap-1 rounded bg-blue-500 px-2 text-[11px] font-semibold text-white" @click="addRow(group.key)">
            <Plus class="size-3" />新增
          </button>
        </div>
      </div>
      <div v-if="showTable(group.key)" class="overflow-x-auto bg-white">
        <table class="w-full min-w-[920px] text-left text-[11px]">
          <thead class="bg-slate-50 text-slate-500">
            <tr>
              <th class="px-3 py-1.5">时间</th>
              <th class="px-3 py-1.5">SO号</th>
              <th class="px-3 py-1.5">货号</th>
              <th class="px-3 py-1.5">货名</th>
              <th class="px-3 py-1.5">合同号</th>
              <th v-if="group.showPo" class="px-3 py-1.5">客PO</th>
              <th class="px-3 py-1.5 text-right">件数</th>
              <th class="px-3 py-1.5 text-right">卡板数</th>
              <th v-if="group.hasAction" class="px-3 py-1.5 text-right">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="row in filtered(group.key)" :key="row.id">
              <td class="px-3 py-1.5">{{ row.date }}</td>
              <td class="px-3 py-1.5">{{ row.so }}</td>
              <td class="px-3 py-1.5">{{ row.code }}</td>
              <td class="px-3 py-1.5 text-slate-700">{{ row.name }}</td>
              <td class="px-3 py-1.5">{{ row.contract }}</td>
              <td v-if="group.showPo" class="px-3 py-1.5">{{ row.po }}</td>
              <td class="px-3 py-1.5 text-right tabular-nums">{{ row.pieces }}</td>
              <td class="px-3 py-1.5 text-right tabular-nums">{{ row.boards }}</td>
              <td v-if="group.hasAction" class="px-3 py-1.5 text-right">
                <button type="button" class="inline-flex text-rose-500" aria-label="删除" @click="removeRow(group.key, row.id)"><Trash2 class="size-3.5" /></button>
              </td>
            </tr>
            <tr v-if="!filtered(group.key).length">
              <td :colspan="group.showPo ? (group.hasAction ? 9 : 8) : (group.hasAction ? 8 : 7)" class="px-3 py-6 text-center text-slate-400">暂无数据</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
