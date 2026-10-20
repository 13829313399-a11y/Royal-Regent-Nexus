<script setup lang="ts">
import CartonFilterBar from '@/components/CartonFilterBar.vue'
import type { SettlementLineFilter, SettlementBusinessKind } from '@/features/carton-procurement/queryFilters'
defineProps<{ dirty?: boolean; shown: number; total: number; hideSearch?: boolean }>()
const query = defineModel<string>('query', { required: true })
const lines = defineModel<SettlementLineFilter>('lines', { required: true })
const businessKind = defineModel<SettlementBusinessKind>('businessKind', { default: '' })
const stage = defineModel<string>('stage', { required: true })
</script>
<template>
  <CartonFilterBar label="月结查询" >
<label v-if="!hideSearch" class="min-w-52 flex-1">明细关键字<input v-model="query" aria-label="月结明细关键字" placeholder="客户 / 合同 / 货号 / 送货单 / 依据" class="mt-1 h-9 w-full rounded-lg border px-3"></label>
<label>业务类型<select v-model="businessKind" aria-label="月结业务类型" class="mt-1 block h-9 rounded-lg border px-3"><option value="">全部类型</option><option value="SAMPLE">样板</option><option value="MISC">杂单</option><option value="OTHER">其他（正单及历史）</option></select></label>
<label>明细<select v-model="lines" aria-label="月结明细筛选" class="mt-1 block h-9 rounded-lg border px-3"><option value="ALL">全部明细</option><option value="CARD">配卡专项（平卡 / 刀卡 / 压线卡 / 啤卡等）</option><option value="NON_CARD">非配卡纸品</option><option value="DIFFERENCE">只看差异 / 缺项</option><option value="UNMATCHED">未关联送货凭证</option></select></label>
<label>版本状态<select v-model="stage" aria-label="月结版本状态" class="mt-1 block h-9 rounded-lg border px-3"><option value="ALL">全部版本</option><option value="SUPPLIER_PENDING">供应商待确认</option><option value="INTERNAL_PENDING">本厂待确认</option><option value="DISPUTED">供应商有异议</option><option value="STALE">来源已变化</option><option value="CONFIRMED">双方已确认</option><option value="HISTORY">历史版本</option></select></label>

<template #actions><button type="button" class="h-9 rounded-lg border px-3" @click="query = ''; lines = 'ALL'; stage = 'ALL'; businessKind = ''">清除筛选</button></template>
<template #footer><span class="pb-2 text-slate-500">显示 {{ shown }} / {{ total }} 条；总额按全部明细计算</span>
<p v-if="dirty" class="w-full text-amber-800">修改尚未保存，保存后重新计算差异；当前仅显示已知来源问题。</p>
<p v-if="stage !== 'ALL'" class="w-full text-slate-500">状态筛选用于查找版本，当前查看的版本仍保留在版本列表中。</p></template>
</CartonFilterBar>
</template>
