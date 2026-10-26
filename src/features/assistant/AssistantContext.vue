<script setup lang="ts">
import { computed, ref } from 'vue'
import { X, ChevronDown } from '@lucide/vue'
import { factoryContexts } from '@/data/enterpriseMock'
import type { DraftScope } from './types'
const props = defineProps<{ scope: DraftScope; changed: boolean; currentTitle: string; currentFactory?: string | null }>()
const emit = defineEmits<{ adopt: []; remove: []; removeSelection: [index?: number]; inspect: [] }>()
const expanded = ref(false)
const factory = computed(() => {
  const id = props.scope.selection?.filters.factory_id || props.scope.page?.factory_id
  return id === 'authorized' ? '本人全部授权范围' : factoryContexts.find(f => f.id === id)?.name || '授权范围'
})
const currentLabel = computed(() => [factoryContexts.find(f => f.id === props.currentFactory)?.name,props.currentTitle].filter(Boolean).join(' · '))
const filters = computed(() => Object.entries(props.scope.selection?.filters || {}).filter(([key]) => key !== 'public_query' && !['filter_json','search_json','sort_json'].includes(key)))
const filterLabels: Record<string,string> = {factory_id:'厂区',view:'视图',module:'业务模块',q:'搜索词',due:'期限',unread_only:'仅未读',status:'状态',query_summary:'列表范围',
  task_scope:'执行范围',demand_id:'关联需求编号',
  responsibility_scope:'客户责任范围',kind:'订单类型',customer_name:'客户',customer_code:'客户编号',status_filter:'订单状态',
  collaboration_filter:'协同状态',due_filter:'交期范围',sort:'排序',search:'搜索词',date_from:'开始日期',date_to:'结束日期',scope_error:'范围提示',keyword:'搜索词',customer:'客户',scope_note:'版本说明'}
const cartonValues: Record<string, Record<string,string>> = {
  view: { orders:'订单管理', inventory:'库存汇总' }, responsibility_scope: { OWN:'本人负责', ALL:'全部可见' },
  kind: { ALL:'全部类型', PURCHASE:'正单', SAMPLE:'样板', WORKSHOP_MISC:'杂单', SUPPLIER_GIFT:'供应商赠送' },
  status_filter: { CONFIRMED:'正单：待发送', PENDING_SUPPLIER:'正单：已确认锁定', SUBMITTED:'待确认锁定', SENT:'已发送 · 待送货', QUOTED:'已报价 · 待送货', READY:'可送货', PARTIALLY_RECEIVED:'部分收料', COMPLETED:'已完成', CANCELLED:'已取消' },
  collaboration_filter: { NOT_ISSUED:'尚未发送供应商', PENDING_CHANGE:'变更待生成', PENDING:'供应商待接单', PARTIAL:'供应商部分接单', ACCEPTED:'供应商已接单', NOT_REQUIRED:'无需接单', LATE_PROMISE:'承诺晚于计划', CANCELLED:'订单已取消' },
  due_filter: { OVERDUE:'已逾期', TODAY:'今日交期', DUE_SOON:'3 天内', UPCOMING:'后续交期' },
  sort: { DUE_ASC:'交期由近到远', DUE_DESC:'交期由远到近', ORDER_DESC:'下单日期最新' },
}
const recordLabels: Record<string,string> = {demand:'需求',printer:'机台',entry:'事项',order:'订单',inventory:'库存记录',quote:'报价版本',task:'任务'}
function filterValue(key: string, value: unknown) {
  if (key === 'factory_id') return factoryContexts.find(f => f.id === value)?.name || (value === 'authorized' ? '本人授权范围' : String(value ?? '未指定'))
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (props.scope.page?.module_id === 'uv-operations' && key === 'view' && value === 'tasks') return props.scope.selection?.resources.length ? '选中UV任务' : '全部UV任务清单'
  if (props.scope.page?.module_id === 'spray-production') {
    if(key==='view')return value==='tasks'?'喷油工序任务':'喷油需求与实体库存'
    if(key==='task_scope')return value==='active'?'待开工、执行中和暂停':'全部执行任务'
  }
  if (props.scope.page?.module_id === 'internal-quote' && key === 'view' && value === 'compare') return '原报价版本比较（基准在前）'
  if (props.scope.page?.module_id === 'carton-procurement' && typeof value === 'string') return cartonValues[key]?.[value] || (value === 'ALL' ? '全部' : value || '未限定')
  return value === '' || value == null ? '未限定' : String(value)
}
</script>
<template>
  <div class="yl-scope-tray">
    <div class="yl-context">
      <button class="yl-scope-summary" :aria-expanded="expanded" aria-label="查看本轮范围" @click="expanded=!expanded; emit('inspect')"><span>{{ scope.page ? `${factory} · ${scope.title}` : '自由交流' }}</span><small v-if="scope.selection">{{ scope.selection.resources.length }} 条记录<span v-if="filters.length"> · {{ filters.length }} 项筛选</span></small><ChevronDown :size="14"/></button>
      <button v-if="scope.page" aria-label="移除页面上下文" @click="emit('remove')"><X :size="16"/></button>
      <button v-else-if="currentTitle" @click="emit('adopt')">带上本页</button>
    </div>
    <div v-if="changed" class="yl-scope-change"><span>仍使用原问题范围</span><button @click="emit('adopt')">改用 {{ currentLabel || '自由交流' }}</button></div>
    <div v-if="expanded" class="yl-scope-details">
      <p>{{ scope.page ? `${factory} · ${scope.title}` : '不带页面或业务记录，自由提问。' }}</p>
      <p v-if="scope.page" class="yl-muted">范围用于本轮提问；数据由服务端按当前权限重新查询。</p>
      <p v-if="scope.selection" class="yl-muted">可在本页选中其他记录，再从添加菜单带入；同一范围最多 10 条。</p>
      <p v-if="filters.length">已带入以下范围条件；选中记录按编号重新查询。</p>
      <dl v-if="filters.length" class="yl-scope-filters"><template v-for="([key,value]) in filters" :key="key"><dt>{{ filterLabels[key] || key }}</dt><dd>{{ filterValue(key,value) }}</dd></template></dl>
      <div v-for="(record,index) in scope.selection?.resources" :key="`${record.module_id}:${record.resource_type}:${record.resource_id}`"><span class="yl-scope-record">选中{{ recordLabels[record.resource_type] || '记录' }} {{ index + 1 }}</span><button :aria-label="`移除第 ${index + 1} 条选中记录`" @click="emit('removeSelection', index)"><X :size="16"/></button></div>
      <button v-if="scope.selection" @click="emit('removeSelection')">移除选中记录和筛选</button>
    </div>
  </div>
</template>
