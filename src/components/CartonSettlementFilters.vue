<script setup lang="ts">
import type { SettlementLineFilter } from '@/features/carton-procurement/queryFilters'
defineProps<{ dirty?: boolean; shown: number; total: number }>()
const query = defineModel<string>('query', { required: true })
const lines = defineModel<SettlementLineFilter>('lines', { required: true })
const stage = defineModel<string>('stage', { required: true })
</script>
<template>
  <div class="flex flex-wrap items-end gap-2 border-b bg-slate-50 p-3 text-xs" aria-label="月结查询">
    <label class="min-w-52 flex-1">明细关键字<input v-model="query" aria-label="月结明细关键字" placeholder="客户 / 合同 / 货号 / 送货单 / 依据" class="mt-1 h-9 w-full rounded-lg border px-3"></label>
    <label>明细<select v-model="lines" aria-label="月结明细筛选" class="mt-1 block h-9 rounded-lg border px-3"><option value="ALL">全部明细</option><option value="DIFFERENCE">只看差异 / 缺项</option><option value="UNMATCHED">未关联送货凭证</option></select></label>
    <label>版本状态<select v-model="stage" aria-label="月结版本状态" class="mt-1 block h-9 rounded-lg border px-3"><option value="ALL">全部版本</option><option value="SUPPLIER_PENDING">供应商待确认</option><option value="INTERNAL_PENDING">本厂待确认</option><option value="DISPUTED">供应商有异议</option><option value="STALE">来源已变化</option><option value="CONFIRMED">双方已确认</option><option value="HISTORY">历史版本</option></select></label>
    <button type="button" class="h-9 rounded-lg border px-3" @click="query = ''; lines = 'ALL'; stage = 'ALL'">清除筛选</button><span class="pb-2 text-slate-500">显示 {{ shown }} / {{ total }} 条；总额按全部明细计算</span>
    <p v-if="dirty" class="w-full text-amber-800">修改尚未保存，保存后重新计算差异；当前仅显示已知来源问题。</p>
    <p v-if="stage !== 'ALL'" class="w-full text-slate-500">状态筛选用于查找版本，当前查看的版本仍保留在版本列表中。</p>
  </div>
</template>
