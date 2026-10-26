<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { X, ArrowUpRight, CircleCheck, Circle } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import { useSprayWorkspace } from '../workspace'
import { SPRAY_BASE, number, dateTime, type Demand, type RouteVersion, type Entity } from '../contracts'
import { usePassportPanel } from '../usePassportPanel'
const w = useSprayWorkspace()
const {panel,focus}=usePassportPanel(w.passportId)
const demand = ref<Demand | null>(null), selectedLine = ref(''), events = ref<Entity[]>([]), failed = ref('')
const loading=ref(false), asOf=ref(''), eventsFailed=ref(''), routeFailed=ref(''), route=ref<RouteVersion|null>(null)
let sequence=0, routeSequence=0
const line = computed(() => demand.value?.lines.find(item => item.id === selectedLine.value) ?? demand.value?.lines[0])
async function load(refocus=false) {
  const id=w.passportId.value, factory=w.factory.value, context=w.contextVersion.value, current=++sequence
  demand.value = null; failed.value = ''; events.value = []; eventsFailed.value=''; asOf.value=''; w.verifiedDemandId.value=null
  if(id)w.assistantRecord.value=null
  if (!id || !w.ready.value) {loading.value=false;return}
  loading.value=true
  const valid=()=>current===sequence && context===w.contextVersion.value && id===w.passportId.value && w.ready.value
  try {
    const result = await w.query<Demand>('demands/' + encodeURIComponent(id), {}, 'passport')
    if (!valid()) return
    if(result.data.id!==id || result.data.factory_id!==factory) throw new Error('返回的需求与所选来源不一致，请重试。')
    demand.value = result.data; asOf.value=result.meta.as_of; w.verifiedDemandId.value=id
    w.assistantRecord.value={id,kind:'demand',label:result.data.document_no}
    selectedLine.value = result.data.lines[0]?.id ?? ''
    const ids = new Set([id, ...result.data.lines.map(item => item.id)])
    void w.query<Entity[]>('activity', {page_size:200}, 'passport-activity').then(activity=>{
      if(valid()) events.value=activity.data.filter(event=>ids.has(String(event.entity_id)))
    }).catch(cause=>{if(valid())eventsFailed.value=w.explain(cause)})
  } catch (cause) { if (valid()) failed.value = w.explain(cause) }
  finally {if(valid()){loading.value=false;if(refocus)void focus()}}
}
async function loadRoute() {
  const id=line.value?.route_id, context=w.contextVersion.value, current=++routeSequence
  route.value=null; routeFailed.value=''
  if(!id || !w.ready.value)return
  try {
    const result=await w.query<RouteVersion>('routes/'+encodeURIComponent(id),{},'passport-route')
    if(current!==routeSequence || context!==w.contextVersion.value)return
    if(result.data.id!==id)throw new Error('工艺来源不一致')
    route.value=result.data
  } catch(cause){if(current===routeSequence && context===w.contextVersion.value)routeFailed.value=w.explain(cause)}
}
watch([w.passportId,w.ready,w.contextVersion],()=>void load(),{immediate:true,flush:'sync'})
watch([()=>line.value?.route_id,w.contextVersion],()=>void loadRoute(),{flush:'sync'})
onBeforeUnmount(()=>{sequence++;routeSequence++;demand.value=null;w.verifiedDemandId.value=null})
const relatedLinks=computed(()=>[{path:'planning',label:'准备与排期'},{path:'execution',label:'实绩与质量'},{path:'handover',label:'来料与交收'},...(w.can('settle')&&w.can('cost_read')?[{path:'finance/settlements',label:'月结来源'}]:[])])
const progress = (stepId:string) => demand.value?.journey?.find(row=>row.line_id===line.value?.id&&row.step_id===stepId)
const stats = computed(() => {
  if (!line.value) return []
  const value = line.value
  const balance = (state:string) => Object.entries(value.balances_by_unit?.[state]??{}).map(([unit,qty])=>`${number(qty)} ${unit}`).join(' · ') || `0 ${value.unit}`
  return [{label:'需求',text:`${number(value.quantity)} ${value.unit}`},{label:'已收白件',text:`${number(value.received)} ${value.unit}`},{label:'期初结余',text:`${number(value.opening_balance??'0')} ${value.unit}`},{label:'白胚在库',text:balance('white')},{label:'工序在制',text:balance('wip')},{label:'合格在库',text:balance('finished')},{label:'质量待判',text:balance('hold')}]
})
</script>
<template>
  <dialog ref="panel" class="spray-passport spray-workspace" tabindex="-1" aria-label="订单追踪" :aria-busy="loading" @keydown.esc.prevent="w.passportId.value=null" @cancel.prevent="w.passportId.value=null">
    <header><span class="spray-eyebrow">订单追踪</span><button class="spray-icon-button" aria-label="关闭订单追踪" @click="w.passportId.value = null"><X :size="18" /></button></header>
    <div v-if="failed" class="spray-alert" role="alert"><p>{{ failed }}</p><button class="spray-secondary" @click="load(true)">重试读取需求</button></div>
    <div v-else-if="loading" class="spray-empty" role="status">读取订单…</div>
    <template v-else-if="demand">
      <h2>{{ line?.item_no }} <span>{{ line?.part }}</span></h2><p class="spray-muted">{{ demand.document_no }} · {{ demand.counterparty }}</p>
      <div v-if="demand.lines.length > 1" class="spray-tabs"><button v-for="part in demand.lines" :key="part.id" :class="{ active: part.id === line?.id }" @click="selectedLine = part.id">{{ part.part }}</button></div>
      <dl class="spray-passport__facts"><div><dt>承诺交期</dt><dd>{{ line?.due_date }}</dd></div><div><dt>颜色 / 版本</dt><dd>{{ line?.color }}</dd></div><div><dt>订单版本</dt><dd>V{{ demand.version }}</dd></div><div v-if="w.can('cost_read')"><dt>交收单价</dt><dd>{{ number(line?.commercial_price) }} {{ line?.currency }}</dd></div></dl>
      <div class="spray-passport__numbers"><div v-for="stat in stats" :key="stat.label"><small>{{ stat.label }}</small><strong>{{ stat.text }}</strong></div></div>
      <p class="spray-source-note spray-muted">合格在库不包含已发出的成品；工序处理量不能累加为最终产量。源记录更新 {{dateTime(demand.updated_at)}} · 本次读取 {{dateTime(asOf)}}（上海）。</p>
      <p v-if="routeFailed" class="spray-alert" role="alert">工艺暂不可用：{{routeFailed}} <button class="spray-text-button" @click="loadRoute">重试工艺</button></p>
      <section><h3>工序旅程 <small>{{ route?.status === 'confirmed' ? '已确认路线' : '待确认工艺' }}</small></h3><ol class="spray-journey"><li v-for="step in route?.steps" :key="step.id"><CircleCheck v-if="progress(step.id)" :size="15"/><Circle v-else :size="15" /><div><strong>{{ step.name }}</strong><span>{{ step.predecessors.length ? `前置 ${step.predecessors.length} 道工序` : '从合格来料开始' }} · {{ step.input_unit }} → {{ step.output_unit }}</span><span v-if="progress(step.id)">已报加工 {{number(progress(step.id)?.processed)}} {{step.input_unit}} · 合格产出 {{number(progress(step.id)?.good)}} {{step.output_unit}} · 其中返工投入 {{number(progress(step.id)?.rework_processed)}}</span><span v-else>尚无已确认实绩</span></div></li></ol><p v-if="!route" class="spray-muted">尚未关联可用工艺版本。</p></section>
      <section><h3>关联事项</h3><RouterLink v-for="item in relatedLinks" :key="item.path" :to="{ path: `${SPRAY_BASE}/${item.path}`, query: { factory: w.factory.value, demand: demand.id } }" class="spray-passport__link" @click="w.passportId.value=null">{{ item.label }}<ArrowUpRight :size="15" /></RouterLink></section>
      <section><h3>来源与近期变更</h3><p v-if="eventsFailed" class="spray-alert">变更记录暂不可用：{{eventsFailed}}</p><p class="spray-muted">{{ demand.source_ref || '手工登记 · 来源单号待补充' }}</p><p v-if="demand.note">{{ demand.note }}</p><ul class="spray-events"><li v-for="event in events.slice(0, 8)" :key="event.id"><time>{{ String(event.business_date) }}</time><span>{{ String(event.summary) }}</span></li></ul></section>
    </template>
  </dialog>
</template>
