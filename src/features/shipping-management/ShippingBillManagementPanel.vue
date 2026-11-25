<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search, RotateCcw } from '@lucide/vue'

const tabs = ['预提单', '核对提单', '从邮件识别提单'] as const
const activeTab = ref<(typeof tabs)[number]>('预提单')

const filters = ref({ account: '', contract: '', subject: '', pieces: '', cbm: '' })
const applied = ref({ ...filters.value })

const rows = [
  { id: 1, account: 'ZURU-SZ', contract: 'CT-TRK-001', subject: 'Booking Confirmation WKFSO202611', pieces: 80, cbm: 3.2, status: '待核对' },
  { id: 2, account: 'BUZZBEE', contract: 'CT-BZ-001', subject: 'Truck Booking BZSO202612', pieces: 120, cbm: 4.8, status: '已核对' },
  { id: 3, account: 'PLAYMATES', contract: 'SE-2026-018', subject: 'SO 822 出货明细更新', pieces: 1760, cbm: 24.64, status: '待核对' },
  { id: 4, account: 'ZURU-SZ', contract: 'CT-WKF-002', subject: 'Booking Confirmation WKFSO202612', pieces: 75, cbm: 3.0, status: '已核对' },
  { id: 5, account: 'MOOSE', contract: 'CT-MOOSE-006', subject: '提单补料 2026-11', pieces: 240, cbm: 8.6, status: '已识别' },
]

const filteredRows = computed(() => rows.filter((row) => {
  const f = applied.value
  return (!f.account || row.account.toLowerCase().includes(f.account.toLowerCase()))
    && (!f.contract || row.contract.toLowerCase().includes(f.contract.toLowerCase()))
    && (!f.subject || row.subject.toLowerCase().includes(f.subject.toLowerCase()))
    && (!f.pieces || row.pieces === Number(f.pieces))
    && (!f.cbm || row.cbm === Number(f.cbm))
}))

function search() {
  applied.value = { ...filters.value }
}

function reset() {
  filters.value = { account: '', contract: '', subject: '', pieces: '', cbm: '' }
  applied.value = { ...filters.value }
}
</script>

<template>
  <section class="space-y-4" aria-label="提单管理">
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 class="text-[18px] font-bold text-slate-900">提单管理</h2>
      <div class="mt-3 flex flex-wrap gap-1 border-b border-slate-100">
        <button
          v-for="tab in tabs"
          :key="tab"
          type="button"
          class="rounded-t-lg px-3 py-2 text-[12px] font-semibold"
          :class="activeTab === tab ? 'border-b-2 border-blue-600 bg-blue-50 text-blue-700' : 'text-slate-500 hover:text-slate-800'"
          @click="activeTab = tab"
        >
          {{ tab }}
        </button>
      </div>

      <div class="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-7">
        <input v-model="filters.account" placeholder="账号（模糊）" class="h-9 rounded-lg border border-slate-200 bg-slate-50 px-2.5 text-[12px]">
        <input v-model="filters.contract" placeholder="合同号（模糊）" class="h-9 rounded-lg border border-slate-200 bg-slate-50 px-2.5 text-[12px]">
        <input v-model="filters.subject" placeholder="邮件主题（关键词）" class="h-9 rounded-lg border border-slate-200 bg-slate-50 px-2.5 text-[12px]">
        <input v-model="filters.pieces" placeholder="件数（精确）" class="h-9 rounded-lg border border-slate-200 bg-slate-50 px-2.5 text-[12px]">
        <input v-model="filters.cbm" placeholder="CBM（精确）" class="h-9 rounded-lg border border-slate-200 bg-slate-50 px-2.5 text-[12px]">
        <button type="button" class="inline-flex h-9 items-center justify-center gap-1 rounded-lg bg-blue-600 px-3 text-[12px] font-semibold text-white" @click="search">
          <Search class="size-3.5" />搜索
        </button>
        <button type="button" class="inline-flex h-9 items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-700" @click="reset">
          <RotateCcw class="size-3.5" />重置
        </button>
      </div>

      <div class="mt-3 overflow-x-auto rounded-lg border border-slate-200">
        <table class="w-full min-w-[860px] text-left text-[12px]">
          <thead class="bg-slate-50 text-slate-500">
            <tr>
              <th class="px-3 py-2">账号</th>
              <th class="px-3 py-2">合同号</th>
              <th class="px-3 py-2">邮件主题</th>
              <th class="px-3 py-2 text-right">件数</th>
              <th class="px-3 py-2 text-right">CBM</th>
              <th class="px-3 py-2">状态</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="row in filteredRows" :key="row.id" class="hover:bg-slate-50">
              <td class="px-3 py-2 font-semibold text-slate-800">{{ row.account }}</td>
              <td class="px-3 py-2">{{ row.contract }}</td>
              <td class="px-3 py-2 text-slate-600">{{ row.subject }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.pieces }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.cbm.toFixed(2) }}</td>
              <td class="px-3 py-2">
                <span class="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-700">{{ row.status }}</span>
              </td>
            </tr>
            <tr v-if="!filteredRows.length"><td colspan="6" class="px-3 py-8 text-center text-slate-400">暂无数据</td></tr>
          </tbody>
        </table>
      </div>
      <p class="mt-2 text-[11px] text-slate-400">当前页签：{{ activeTab }} · 共 {{ filteredRows.length }} 条</p>
    </div>
  </section>
</template>
