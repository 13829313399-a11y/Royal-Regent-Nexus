<script setup lang="ts">
import { computed, ref } from 'vue'
import { masterPaperOptions, masterDueRules, type MasterRecord, type MasterWorkspace, type NumberRule } from '@/api/cartonMaster'
import type { CartonCustomerResponse } from '@/api/cartonProcurement'
import type { CartonLocation } from '@/api/cartonPositions'
import { describeNumberTemplate } from '@/lib/cartonNumberPatterns'

const props = defineProps<{ workspace: MasterWorkspace; customers: CartonCustomerResponse[] }>()
const emit = defineEmits<{
  paper: [];
  rule: [code: string]; edit: [row: MasterRecord]; create: [kind: MasterRecord['kind'], code?: string]
  location: [row?: CartonLocation, warehouse?: string]; warehouse: [name?: string]; customer: [row?: CartonCustomerResponse]; source: [row: MasterRecord]
}>()
const query = ref(''), placeQuery = ref('')
const matches = (values: unknown[], term: string) => values.join(' ').toLowerCase().includes(term.trim().toLowerCase())
const rules = (code: string) => masterDueRules(props.workspace.records, code)
const savedRule = (code: string) => props.workspace.records.find(r => r.kind === 'RULE' && r.customer_code === code)
const factoryRule = computed(() => savedRule(''))
const factoryDates = computed(() => rules(''))
const contracts = (code: string) => props.workspace.records.filter(r => r.kind === 'CONTRACT' && r.customer_code === code)
const matchingContracts = (code: string) => contracts(code).filter(r => matches([r.code, ...(r.data.item_nos || [])], query.value))
const contractsShown = (code: string) => query.value.trim() && matchingContracts(code).length ? matchingContracts(code) : contracts(code)
const customersShown = computed(() => props.customers.filter(c => matches([c.customer_name, c.customer_code, c.contact_name, c.contact_phone, ...contracts(c.customer_code).flatMap(r => [r.code, ...(r.data.item_nos || [])])], query.value)))
const workshops = computed(() => props.workspace.records.filter(r => r.kind === 'WORKSHOP'))
const grants = computed(() => props.workspace.records.filter(r => r.kind === 'ACCESS'))
const warehouseGroups = computed(() => [...new Set(props.workspace.locations.map(p => p.warehouse))].map(warehouse => ({
  warehouse, places: props.workspace.locations.filter(p => p.warehouse === warehouse && matches([p.warehouse, p.bin_code], placeQuery.value)),
})).filter(g => g.places.length))
const canPlace = (warehouse: string) => props.workspace.can_manage || props.workspace.warehouses.includes(warehouse)
const formatText = (rule: NumberRule) => rule.mode === 'OFF' ? '不检查' : rule.frozen && rule.templates?.length
  ? rule.templates.map(describeNumberTemplate).join('；') : rule.mode === 'AUTO' ? '未设置格式'
  : `前缀 ${rule.prefix || '不限'} · ${rule.min_length}–${rule.max_length} 字 · ${rule.characters === 'DIGITS' ? '纯数字' : rule.characters === 'ALNUM_DASH' ? '字母数字及 -_' : '合法字符'}`
const modeText = (rule: NumberRule) => rule.mode === 'OFF' ? '' : rule.mode === 'BLOCK' ? '强制检查' : rule.mode === 'AUTO' && !rule.templates?.length ? '' : '软提醒'
</script>

<template>
  <div class="space-y-4" aria-label="基础设置">
    <article class="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-teal-200 bg-teal-50/40 p-4" aria-label="本厂通用交期">
      <div><h3 class="font-bold text-slate-900">本厂通用交期</h3><p class="mt-1 text-xs text-slate-500">客户未单独设置时沿用；只影响新单，旧单与追加保留原提前量。</p></div>
      <div class="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs"><span>采购安全提前量 <b class="ml-1 text-base text-teal-800">{{ factoryDates.lead_days }}</b> 天</span><span>客户交期建议 <b class="ml-1">{{ factoryDates.customer_days == null ? '不提供' : `下单后 ${factoryDates.customer_days} 天` }}</b></span><span v-if="factoryRule?.status === 'INACTIVE'" class="text-amber-700">独立设置已停用，采用系统默认</span><button v-if="workspace.can_manage" type="button" class="rounded-lg border border-teal-200 bg-white px-3 py-2 text-teal-700" @click="emit('rule', '')">设置通用交期</button></div>
    </article>

    <article class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm" aria-label="客户与规则">
      <div class="flex flex-wrap items-center justify-between gap-3 border-b p-4"><div><h3 class="font-bold">客户与规则</h3><p class="mt-1 text-xs text-slate-500">客户资料、编号格式、交期与关联合同集中维护。停用保留历史。</p></div><div class="flex gap-2"><input v-model="query" aria-label="查找客户与合同" placeholder="客户 / 合同 / 货号" class="h-9 w-52 max-w-full rounded-lg border px-3 text-xs"><button v-if="query" type="button" class="text-xs text-teal-700" @click="query = ''">清空筛选</button><button v-if="workspace.can_manage" type="button" class="whitespace-nowrap rounded-lg bg-teal-700 px-3 py-2 text-xs font-bold text-white" @click="emit('customer')">新增客户</button></div></div>
      <div class="overflow-x-auto"><table class="w-full min-w-[960px] text-left text-xs">
        <thead class="bg-slate-50 text-slate-500"><tr><th class="p-3">客户 / 联系人</th><th class="p-3">合同号格式</th><th class="p-3">货号格式</th><th class="p-3">当前交期规则</th><th class="p-3">状态</th><th class="p-3 text-right">操作</th></tr></thead>
        <tbody v-for="c in customersShown" :key="c.id" class="border-b border-slate-100 last:border-0">
          <tr class="align-top hover:bg-slate-50/60"><td class="p-3"><b>{{ c.customer_name }}</b><p class="mt-1 text-slate-500">{{ c.contact_name || '未填写联系人' }} {{ c.contact_phone }}</p></td>
            <td v-for="key in (['contract_rule', 'item_rule'] as const)" :key="key" class="max-w-64 p-3"><p class="break-words leading-5">{{ formatText(rules(c.customer_code)[key]) }}</p><span class="text-[10px]" :class="rules(c.customer_code)[key].mode === 'BLOCK' ? 'text-amber-700' : 'text-teal-700'">{{ modeText(rules(c.customer_code)[key]) }}</span></td>
            <td class="whitespace-nowrap p-3 leading-5"><p>提前 {{ rules(c.customer_code).lead_days }} 天</p><p class="text-slate-500">{{ rules(c.customer_code).customer_days == null ? '不提供客户交期建议' : `建议下单后 ${rules(c.customer_code).customer_days} 天` }}</p><p v-if="savedRule(c.customer_code)?.status === 'INACTIVE'" class="text-amber-700">客户规则停用，交期沿用本厂</p></td>
            <td class="p-3"><span :class="c.status === 'ACTIVE' ? 'text-teal-700' : 'text-slate-400'">{{ c.status === 'ACTIVE' ? '启用' : '停用' }}</span></td>
            <td class="p-3"><div v-if="workspace.can_manage" class="flex justify-end gap-2 whitespace-nowrap"><button type="button" :aria-label="`编辑客户 ${c.customer_name}`" class="rounded-lg border px-3 py-2" @click="emit('customer', c)">资料</button><button type="button" :aria-label="`设置客户规则 ${c.customer_name}`" class="rounded-lg border border-teal-200 px-3 py-2 text-teal-700" @click="emit('rule', c.customer_code)">规则</button></div><span v-else class="block text-right text-slate-400">只读</span></td>
          </tr>
          <tr><td colspan="6" class="px-3 pb-3"><details :open="Boolean(query.trim() && matchingContracts(c.customer_code).length)"><summary class="w-fit cursor-pointer text-xs text-slate-500">关联合同 · {{ contractsShown(c.customer_code).length }} / {{ contracts(c.customer_code).length }} 份</summary><div class="mt-2 rounded-lg border border-slate-100 bg-slate-50/50 p-3"><div class="mb-2 flex items-center justify-between gap-3"><span class="text-slate-500">正式订单自动补充；可核对关联货号。</span><button v-if="workspace.can_manage" type="button" :aria-label="`新增 ${c.customer_name} 合同`" class="rounded-lg border bg-white px-3 py-1.5 text-teal-700" @click="emit('create', 'CONTRACT', c.customer_code)">新增合同</button></div><div v-for="r in contractsShown(c.customer_code)" :key="r.id" class="flex items-center gap-3 border-t border-slate-100 py-2"><b class="w-48 shrink-0 break-all font-mono">{{ r.code }}</b><span class="flex-1 break-all">{{ r.data.item_nos?.join('、') || '未关联货号' }}</span><span :class="r.status === 'ACTIVE' ? 'text-teal-700' : 'text-slate-400'">{{ r.status === 'ACTIVE' ? '启用' : '停用' }}</span><button v-if="r.sources.length" type="button" class="text-teal-700" @click="emit('source', r)">来源</button><button v-if="workspace.can_manage" type="button" class="rounded border bg-white px-2 py-1" @click="emit('edit', r)">修改</button></div><p v-if="!contracts(c.customer_code).length" class="py-2 text-slate-400">暂无关联合同</p></div></details></td></tr>
        </tbody>
        <tbody v-if="!customersShown.length"><tr><td colspan="6" class="p-10 text-center text-slate-400">{{ query ? '没有符合条件的客户' : '暂无客户，新增后可设置对应规则。' }}</td></tr></tbody>
      </table></div>
    </article>

    <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" aria-label="纸品选项设置">
      <div class="flex items-center justify-between gap-3"><div><h3 class="font-bold">纸品选项</h3><p class="mt-1 text-xs text-slate-500">落单时可选或输入相似内容；保存订单后自动积累；可在此添加、修改选项。</p></div><button v-if="workspace.can_manage" type="button" class="rounded-lg border border-teal-200 px-3 py-2 text-xs text-teal-700" @click="emit('paper')">添加 / 修改纸品选项</button></div>
      <div class="mt-3 grid gap-3 sm:grid-cols-3"><div v-for="field in (['packaging_type', 'paper_quality', 'specification'] as const)" :key="field" class="rounded-lg bg-slate-50 p-3 text-xs"><b>{{ { packaging_type: '纸品类型', paper_quality: '纸质', specification: '规格' }[field] }}</b><p class="mt-2 max-h-24 overflow-auto break-words leading-6 text-slate-600">{{ masterPaperOptions(workspace.records, field, workspace.paper_history).join('、') || '暂无选项，可添加或保存订单后自动积累。' }}</p></div></div>
    </article>

    <article class="rounded-xl border border-slate-200 bg-white shadow-sm" aria-label="车间与仓位">
      <div class="border-b p-4"><h3 class="font-bold">车间与仓位</h3><p class="mt-1 text-xs text-slate-500">车间用于领用去向；仓位用于存放库存，按所属仓库分别维护。</p></div>
      <div class="space-y-4 p-4 text-xs">
        <div><div class="mb-2 flex items-center justify-between"><b>车间</b><button v-if="workspace.can_manage" type="button" class="rounded-lg border border-teal-200 px-3 py-1.5 text-teal-700" @click="emit('create', 'WORKSHOP')">新增车间</button></div><div class="flex flex-wrap gap-2"><button v-for="r in workshops" :key="r.id" type="button" :disabled="!workspace.can_manage" :aria-label="`修改车间 ${r.code}`" class="rounded-lg border px-3 py-2 disabled:cursor-default" :class="r.status === 'ACTIVE' ? 'border-teal-100 bg-teal-50/50 text-teal-800' : 'border-slate-200 bg-slate-50 text-slate-400'" @click="emit('edit', r)">{{ r.code }}<span class="ml-2 text-[10px]">{{ r.status === 'INACTIVE' ? '已停用' : workspace.can_manage ? '修改' : '' }}</span></button><span v-if="!workshops.length" class="py-2 text-slate-400">尚未设置车间</span></div></div>
        <div class="border-t pt-4"><div class="mb-3 flex flex-wrap items-center justify-between gap-2"><b>仓库与仓位</b><div class="flex gap-2"><input v-model="placeQuery" aria-label="查找仓库仓位" placeholder="查找仓库 / 仓位" class="h-8 w-44 rounded-lg border px-2"><button v-if="workspace.can_manage" type="button" class="whitespace-nowrap rounded-lg border border-teal-200 px-3 py-1.5 text-teal-700" @click="emit('warehouse')">添加仓库</button></div></div>
          <div v-for="g in warehouseGroups" :key="g.warehouse" class="mb-3 flex flex-wrap items-start gap-3">
            <b class="w-24 shrink-0 break-words py-2">{{ g.warehouse }}</b>
            <div class="flex min-w-0 flex-1 flex-wrap gap-2">
              <button v-for="p in g.places" :key="p.id" type="button" :disabled="!canPlace(p.warehouse) || p.id.startsWith('CL-UNKNOWN-')" :aria-label="`修改仓位 ${p.warehouse} ${p.bin_code}`" class="rounded-lg border px-3 py-2 disabled:cursor-default" :class="p.status === 'INACTIVE' ? 'bg-slate-50 text-slate-400' : 'border-slate-200 text-slate-700 hover:border-teal-300'" @click="emit('location', p)">{{ p.bin_code || '未分仓位' }}<span class="ml-2 text-[10px]">{{ p.status === 'INACTIVE' ? '已停用' : p.id.startsWith('CL-UNKNOWN-') ? '系统保留' : canPlace(p.warehouse) ? '修改' : '' }}</span></button>
            </div>
            <div v-if="canPlace(g.warehouse) && g.warehouse !== '待核仓位'" class="ml-auto flex shrink-0 gap-2">
              <button type="button" :aria-label="`添加 ${g.warehouse} 仓位`" class="whitespace-nowrap rounded-lg border border-teal-200 bg-white px-3 py-2 text-teal-700 hover:bg-teal-50" @click="emit('location', undefined, g.warehouse)">添加仓位</button>
              <button v-if="workspace.can_manage" type="button" :aria-label="`修改仓库 ${g.warehouse}`" class="whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 py-2 text-slate-600 hover:bg-slate-50" @click="emit('warehouse', g.warehouse)">修改</button>
            </div>
          </div><p v-if="!warehouseGroups.length" class="py-2 text-slate-400">暂无匹配的仓库仓位</p><p class="mt-2 text-[11px] text-slate-500">停用保留历史，更名不移动库存；实际转移库存请使用调仓。</p>
        </div>
      </div>
    </article>

    <details v-if="workspace.can_manage" class="rounded-xl border border-slate-200 bg-white p-4" aria-label="仓库维护权限设置"><summary class="cursor-pointer text-sm font-bold">权限设置 <span class="ml-2 text-xs font-normal text-slate-500">仓库维护授权 · {{ grants.length }} 条</span></summary><div class="mt-3 text-xs"><div class="mb-3 flex justify-end"><button type="button" class="rounded-lg border px-3 py-2 text-teal-700" @click="emit('create', 'ACCESS')">新增仓库维护授权</button></div><div v-for="r in grants" :key="r.id" class="flex flex-wrap items-center gap-3 border-t py-3"><b>{{ workspace.users.find(u => u.id === r.code)?.name || r.code }}</b><span class="flex-1">{{ r.data.warehouses?.join('、') || '未指定仓库' }}</span><span>{{ r.status === 'ACTIVE' ? '启用' : '停用' }}</span><button type="button" class="rounded border px-3 py-1.5" @click="emit('edit', r)">修改授权</button></div><p v-if="!grants.length" class="text-slate-400">尚未单独授权仓库维护人员</p></div></details>
  </div>
</template>
