<script setup lang="ts">
import { computed, ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { X, ArrowUpRight, ChevronRight, CircleCheck, Circle } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import { useSprayWorkspace } from '../workspace'
import { SPRAY_BASE, number, type Demand, type DemandLine, type RouteVersion, type Entity } from '../contracts'
const w = useSprayWorkspace()
const panel=ref<HTMLDialogElement|null>(null),wide=window.matchMedia('(min-width:1680px)')
let trigger:HTMLElement|null=null
async function syncPanel(){await nextTick();const element=panel.value;if(!element)return;element.close();if(w.passportId.value){if(wide.matches)element.show();else element.showModal()}else trigger?.focus()}
watch(()=>w.passportId.value,(id,old)=>{if(id&&!old)trigger=document.activeElement as HTMLElement;void syncPanel()},{immediate:true})
wide.addEventListener('change',syncPanel)
onBeforeUnmount(()=>{wide.removeEventListener('change',syncPanel);panel.value?.close();trigger?.focus()})
const demand = ref<Demand | null>(null), selectedLine = ref(''), events = ref<Entity[]>([]), failed = ref('')
const line = computed(() => demand.value?.lines.find(item => item.id === selectedLine.value) ?? demand.value?.lines[0])
const route = computed(() => w.items<RouteVersion>('routes').find(item => item.id === line.value?.route_id))
watch(() => [w.passportId.value, w.factory.value] as const, async ([id]) => {
  demand.value = null; failed.value = ''; events.value = []
  if (!id) return
  try {
    const result = await w.query<Demand>('demands/' + id, {}, 'passport')
    if (id !== w.passportId.value) return
    demand.value = result.data
    selectedLine.value = result.data.lines[0]?.id ?? ''
    if (!w.items('routes').length) await w.load(['routes'])
    const activity = await w.query<Entity[]>('activity', { page_size: 200 })
    const ids = new Set([id, ...result.data.lines.map(item => item.id)])
    events.value = activity.data.filter(event => ids.has(String(event.entity_id)))
  } catch (error) { if (id === w.passportId.value) failed.value = w.explain(error) }
}, { immediate: true })
const progress = (stepId:string) => demand.value?.journey?.find(row=>row.line_id===line.value?.id&&row.step_id===stepId)
const stats = computed(() => {
  if (!line.value) return []
  const value = line.value
  const balance = (state:string) => Object.entries(value.balances_by_unit?.[state]??{}).map(([unit,qty])=>`${number(qty)} ${unit}`).join(' · ') || `0 ${value.unit}`
  return [{label:'需求',text:`${number(value.quantity)} ${value.unit}`},{label:'已收白件',text:`${number(value.received)} ${value.unit}`},{label:'期初结余',text:`${number(value.opening_balance??'0')} ${value.unit}`},{label:'合格成品',text:balance('finished')},{label:'质量待判',text:balance('hold')}]
})
</script>
<template>
  <dialog ref="panel" class="spray-passport spray-workspace" aria-label="订单追踪" @cancel.prevent="w.passportId.value=null">
    <header><span class="spray-eyebrow">订单追踪</span><button class="spray-icon-button" aria-label="关闭订单追踪" @click="w.passportId.value = null"><X :size="18" /></button></header>
    <p v-if="failed" class="spray-alert" role="alert">{{ failed }}</p>
    <div v-else-if="!demand" class="spray-empty">读取订单…</div>
    <template v-else>
      <h2>{{ line?.item_no }} <span>{{ line?.part }}</span></h2><p class="spray-muted">{{ demand.document_no }} · {{ demand.counterparty }}</p>
      <div v-if="demand.lines.length > 1" class="spray-tabs"><button v-for="part in demand.lines" :key="part.id" :class="{ active: part.id === line?.id }" @click="selectedLine = part.id">{{ part.part }}</button></div>
      <dl class="spray-passport__facts"><div><dt>承诺交期</dt><dd>{{ line?.due_date }}</dd></div><div><dt>颜色 / 版本</dt><dd>{{ line?.color }}</dd></div><div><dt>订单版本</dt><dd>V{{ demand.version }}</dd></div><div v-if="w.can('cost_read')"><dt>交收单价</dt><dd>{{ number(line?.commercial_price) }} {{ line?.currency }}</dd></div></dl>
      <div class="spray-passport__numbers"><div v-for="stat in stats" :key="stat.label"><small>{{ stat.label }}</small><strong>{{ stat.text }}</strong></div></div>
      <section><h3>工序旅程 <small>{{ route?.status === 'confirmed' ? '已确认路线' : '待确认工艺' }}</small></h3><ol class="spray-journey"><li v-for="step in route?.steps" :key="step.id"><CircleCheck v-if="progress(step.id)" :size="15"/><Circle v-else :size="15" /><div><strong>{{ step.name }}</strong><span>{{ step.predecessors.length ? `前置 ${step.predecessors.length} 道工序` : '从合格来料开始' }} · {{ step.input_unit }} → {{ step.output_unit }}</span><span v-if="progress(step.id)">已报加工 {{number(progress(step.id)?.processed)}} {{step.input_unit}} · 合格产出 {{number(progress(step.id)?.good)}} {{step.output_unit}} · 其中返工投入 {{number(progress(step.id)?.rework_processed)}}</span><span v-else>尚无已确认实绩</span></div></li></ol><p v-if="!route" class="spray-muted">尚未关联可用工艺版本。</p></section>
      <section><h3>关联事项</h3><RouterLink v-for="item in [{ path: 'planning', label: '准备与排期' }, { path: 'execution', label: '实绩与质量' }, { path: 'handover', label: '来料与交收' }, { path: 'finance/settlements', label: '月结来源' }]" :key="item.path" :to="{ path: `${SPRAY_BASE}/${item.path}`, query: { factory: w.factory.value, demand: demand.id } }" class="spray-passport__link" @click="w.passportId.value=null">{{ item.label }}<ArrowUpRight :size="15" /></RouterLink></section>
      <section><h3>来源与变更</h3><p class="spray-muted">{{ demand.source_ref || '手工登记 · 来源单号待补充' }}</p><p v-if="demand.note">{{ demand.note }}</p><ul class="spray-events"><li v-for="event in events.slice(0, 8)" :key="event.id"><time>{{ String(event.business_date) }}</time><span>{{ String(event.summary) }}</span></li></ul></section>
    </template>
  </dialog>
</template>
