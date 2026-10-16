<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button } from '@/components/ui/button'
import { cuttingDestination } from './location'
import type { ClosingPreview, TraceScope } from './closingApi'
import { reportLabels } from './reportingApi'
const props = defineProps<{ value: ClosingPreview }>()
const filter = ref<'all' | 'opening' | 'period'>('all')
const filters = { all: '全部关联历史', opening: '期初形成依据', period: '本期发生及更正' } as const
const actions: Record<string, string> = { save: '保存草稿', post: '提交生效', void: '作废', review: '抽查', discard: '放弃草稿' }
const warehouseLabels: Record<string, string> = { REQUEST: '领料申请', ISSUE: '仓库实发', CUTTING_RECEIPT: '裁床签收', CUTTING_RECEIPT_VOID: '撤销签收', RETURN: '余料退仓', CORRECTION: '仓库冲销', REQUEST_CLOSE: '申请关闭', CUTTING_REQUEST_REUSE: '计划续用' }
function matches(scope?: TraceScope) { return filter.value === 'all' || !!(filter.value === 'opening' ? scope?.earlier_history : scope?.period_history) }
function scopeLabel(scope?: TraceScope) { return scope?.opening ? '取数时生效数量计入期初' : scope?.period ? '取数时生效数量计入本期' : '取数时数量不计入本期或期初；保留原单及更正依据' }
const production = computed(() => props.value.production_documents.filter(d => matches(d.scope)))
const usage = computed(() => props.value.usage_documents.filter(d => matches(d.scope)))
const warehouse = computed(() => props.value.warehouse_documents.filter(d => filter.value === 'all' || d.scope === filter.value))
</script>
<template>
  <div class="closing-trace">
    <nav aria-label="追溯期间"><Button v-for="(label,key) in filters" :key="key" variant="outline" :aria-pressed="filter===key" @click="filter=key">{{ label }}</Button></nav>
    <p>期初依据包含月初前的生产、耗用、签收和退仓，以及取数时已有的关联更正。已作废版本和草稿仅供追溯；数量按取数时生效记录及业务日期计算，历史明细不再次相加。</p>
    <h3>生产记录及更正</h3>
    <details v-for="document in production" :key="document.document_id">
      <summary>{{ document.history[0]?.data.context.task_name }} · {{ document.history[0]?.data.context.resource_name }} · {{ document.document_id }}{{ document.draft?' · 有草稿':'' }}</summary>
      <p>{{ scopeLabel(document.scope) }} · {{ document.posted?'有生效记录':'未生效／已作废' }} · <RouterLink :to="cuttingDestination(value.line_id,value.month,'reporting','report',document.document_id)">查看生产原单</RouterLink></p>
      <article v-for="event in document.history" :key="event.id">
        <p>V{{ event.version }} · {{ actions[event.action] }} · 业务日期 {{ event.data.entry.day }} · {{ reportLabels[event.data.entry.kind] }} · {{ event.data.context.task_name }}／{{ event.data.context.resource_name }}</p>
        <template v-if="event.action==='post'||event.action==='save'">
          <p v-if="event.action==='save'">草稿数量尚未生效。</p>
          <p v-if="event.data.entry.mode!=='parts'||event.data.entry.kind!=='daily'">数量 {{ event.data.entry.sets }} 套 · 不良 {{ event.data.entry.rejected }} 套 · 报废 {{ event.data.entry.scrap }} 套</p>
          <p v-for="part in event.data.entry.parts" :key="part.code">{{ part.code }}：合格 {{ part.good }} 片、不良 {{ part.rejected }} 片、报废 {{ part.scrap }} 片</p>
        </template>
        <p v-else>本次为{{ actions[event.action] }}操作，不新增产量。</p>
        <p>操作人 ID：{{ event.actor_id }} · 登记 {{ event.created_at }} · {{ event.reason }}</p>
      </article>
    </details>
    <h3>耗用记录及关联更正</h3>
    <details v-for="document in usage" :key="document.document_id">
      <summary>{{ document.context?.task_name }} · {{ document.context?.item_name }} · {{ document.document_id }} · {{ document.effective?'生效':'已作废' }}</summary>
      <p>{{ scopeLabel(document.scope) }} · 执行方 {{ document.context?.resource_name }} · 原实发 {{ document.context?.issue_id }} · 原单位 {{ document.context?.unit }} · <RouterLink :to="cuttingDestination(value.line_id,value.month,'materials','usage',document.document_id)">查看耗用原单</RouterLink></p>
      <article v-for="event in document.history" :key="event.id">
        <p>V{{ event.version }} · {{ actions[event.action]??event.action }} · 业务日期 {{ event.day }} · {{ event.actor }} · 登记 {{ event.date }} · {{ event.reason }}</p>
        <p v-if="event.action==='post'">正常耗用 {{ event.entry.consumed_quantity }} · 损耗 {{ event.entry.loss_quantity }} · 登记时盘余 {{ event.entry.counted_remaining }} {{ document.context?.unit }}</p>
        <p v-else>本次为{{ actions[event.action]??event.action }}操作，不新增耗用或盘余。</p>
        <p v-if="event.replaces_document_id">替代原单 <RouterLink :to="cuttingDestination(value.line_id,value.month,'materials','usage',event.replaces_document_id)">{{ event.replaces_document_id }}</RouterLink></p>
        <p v-if="event.replaced_by_document_id">后续更正单 <RouterLink :to="cuttingDestination(value.line_id,value.month,'materials','usage',event.replaced_by_document_id)">{{ event.replaced_by_document_id }}</RouterLink></p>
      </article>
    </details>
    <h3>仓库关联来源</h3>
    <p>全部历史保留跨月原申请、实发、签收及冲销；期初／本期筛选按各流水业务日期展示。关联单的完整更正链可从原单查看。</p>
    <details v-for="document in warehouse" :key="document.id">
      <summary>{{ document.day }} · {{ warehouseLabels[document.kind]||document.kind }} · {{ document.context?.item_name }} · {{ document.id }} {{ document.reversed?'（已冲销）':'' }}</summary>
      <p>{{ document.context?.task_name }}／{{ document.context?.resource_name }} · 原实发 {{ document.context?.issue_id||'尚无实发' }} · 来源 {{ document.original_id||'无' }}</p>
      <p>数量 {{ document.quantity??'本操作不涉及数量' }} {{ document.quantity?(document.unit||document.context?.unit):'' }} · {{ document.actor }} · 登记 {{ document.date }} · {{ document.reason }}</p>
      <RouterLink :to="cuttingDestination(value.line_id,value.month,'materials','warehouse',document.id)">查看领料关联原单</RouterLink>
    </details>
    <p v-if="!production.length&&!usage.length&&!warehouse.length" class="cutting-no-records">所选范围暂无关联记录。</p>
  </div>
</template>
<style scoped>.closing-trace{display:grid;gap:16px}.closing-trace nav{display:flex;gap:8px;flex-wrap:wrap}.closing-trace article{margin-top:12px}.closing-trace p{font-size:13px;line-height:1.8;overflow-wrap:anywhere}</style>
