<script setup lang="ts">
import { computed, reactive, ref, watch, onBeforeUnmount } from 'vue'
import { RouterLink } from 'vue-router'
import { Plus, CalendarDays, List, PanelLeftClose, PanelLeftOpen, Sparkles, ChevronLeft, ChevronRight, ArrowUpRight, Undo2, X, Check, GripVertical } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useSprayPage } from '../usePage'
import { SPRAY_BASE, number, dateTime, utc, type Demand, type DemandLine, type Stock, type Task, type TaskDraft, type Resource, type RouteVersion, type Scenario } from '../contracts'
import WorkspaceDialog from '../components/WorkspaceDialog.vue'
import ConditionalPlans from '../components/ConditionalPlans.vue'
import WorkspaceState from '../components/WorkspaceState.vue'
const w = useSprayPage(['resources', 'routes', 'demands', 'stock', 'preparations', 'forecasts'])
const view = ref('timeline'), span = ref(5), zoom = ref(360), railOpen = ref(window.matchMedia('(min-width:1280px)').matches), railWidth = ref(264), filter = ref('')
const compactScreen=window.matchMedia('(max-width:1279px)')
const compactChanged=()=>{if(compactScreen.matches)railOpen.value=false}
compactScreen.addEventListener('change',compactChanged)
onBeforeUnmount(()=>compactScreen.removeEventListener('change',compactChanged))
const scenario = ref<Scenario | null>(null), history = ref<(Scenario | null)[]>([]), compare = ref(false), working = ref(false), error = ref('')
const resources = computed(() => w.items<Resource>('resources').filter(resource => ['manual','automatic','pad'].includes(resource.kind)))
const routes = computed(() => w.items<RouteVersion>('routes')), orders = computed(() => w.items<Demand>('demands'))
const lines = computed(() => orders.value.flatMap(order => order.lines.map(line => ({ ...line, order }))))
const filtered = computed(() => lines.value.filter(line => `${line.item_no} ${line.part} ${line.order.document_no}`.includes(filter.value)).sort((a,b) => b.priority - a.priority || a.due_date.localeCompare(b.due_date)))
const stocks = computed(() => w.items<Stock>('stock')), tasks = computed(() => w.items<Task>('tasks'))
const startMs = computed(() => Date.parse(w.businessDate.value + 'T00:00:00+08:00'))
const endMs = computed(() => startMs.value + span.value * 86400000)
const days = computed(() => Array.from({ length: span.value }, (_, i) => new Date(startMs.value + i * 86400000)))
const railCollapsed = computed(() => !railOpen.value || !!w.passportId.value)
const dateLabel = (date: Date) => date.toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', weekday: 'short' })
const lineForTask = (task: Task | TaskDraft) => lines.value.find(line => task.allocations.some(a => ('line_id' in a ? a.line_id : stocks.value.find(stock => stock.id === a.stock_id)?.line_id) === line.id))
const stepName = (id: string) => routes.value.flatMap(route => route.steps).find(step => step.id === id)?.name ?? '工序'
function band(task: { start_at: string; end_at: string }) { const start = Math.max(startMs.value, Date.parse(task.start_at)), end = Math.min(endMs.value, Date.parse(task.end_at)); return { left: `${(start - startMs.value) / 86400000 * zoom.value}px`, width: `${Math.max(8,(end-start)/86400000*zoom.value)}px` } }
const taskTitle = (task: Task | TaskDraft) => `${lineForTask(task)?.item_no ?? '订单'} / ${lineForTask(task)?.part ?? ''} · ${stepName(task.step_id)} · ${number(task.allocations.reduce((sum,a)=>sum+Number(a.quantity),0))} 件 · ${dateTime(task.start_at)} — ${dateTime(task.end_at)}`
const affected = computed(() => new Set(scenario.value?.snapshot.tasks.map(task => lineForTask(task)?.demand_id).filter(Boolean)).size)
async function loadTasks() {
  if (!w.ready.value) return
  const context = w.contextVersion.value
  try {
    const query = { start_at: new Date(startMs.value).toISOString(), end_at: new Date(endMs.value).toISOString(), page_size: 200 }
    const first = await w.query<Task[]>('schedule/window', query, 'schedule-window')
    const all = [...first.data]
    const total = first.pagination?.total ?? all.length
    for (let page=2; all.length < total; page++) { if(context !== w.contextVersion.value) return; const more = await w.query<Task[]>('schedule/window', {...query,page}, 'schedule-window'); all.push(...more.data); if (!more.data.length) break }
    if(context !== w.contextVersion.value) return
    w.data.value = { ...w.data.value, tasks: all }
  } catch (cause) { if (!(cause instanceof Error && cause.message.includes('上下文'))) error.value = w.explain(cause) }
}
watch(() => [w.ready.value,w.businessDate.value,span.value,w.relatedDemand.value], () => { void loadTasks() }, { immediate: true })
function moveDate(delta: number) { w.businessDate.value = new Date(startMs.value + delta * 86400000 + 8*3600000).toISOString().slice(0,10) }
function remember(next: Scenario) { history.value.push(scenario.value); scenario.value = next; w.dirty.value = true }
async function suggest() {
  working.value = true; error.value = ''
  try { remember(await w.command<Scenario>('scenarios/preview', { label: '按优先级与交期生成', start_at: new Date(startMs.value).toISOString(), end_at: new Date(endMs.value).toISOString(), line_ids: filtered.value.map(line=>line.id) })) } catch (cause) { error.value = w.explain(cause) } finally { working.value = false }
}
async function publish() {
  if (!scenario.value) return
  working.value = true; error.value = ''
  try { await w.command(`scenarios/${scenario.value.id}/publish`, { base_revision: scenario.value.base_revision }, scenario.value.version); scenario.value = null; history.value = []; compare.value = false; await Promise.all([loadTasks(),w.load(['stock','demands'])]) } catch (cause) { error.value = w.explain(cause) } finally { working.value = false }
}
function undo() { if (history.value.length) scenario.value = history.value.pop() ?? null; w.dirty.value = !!scenario.value }
function discard() { scenario.value = null; history.value = []; compare.value = false; w.dirty.value = false }
function keyboard(event: KeyboardEvent) { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && !(event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement)) { event.preventDefault(); undo() } }
window.addEventListener('keydown', keyboard)
onBeforeUnmount(() => window.removeEventListener('keydown', keyboard))
const assignOpen = ref(false), selectedTask = ref<Task | null>(null), selectedLine = ref(''), selections = reactive<Record<string,string>>({})
const assignmentDirty=ref(false)
async function closeAssignment(){if(assignmentDirty.value&&!(await w.confirmDiscard('放弃尚未预览的任务分配？')))return;assignOpen.value=false;assignmentDirty.value=false;w.dirty.value=!!scenario.value}
const assignment = reactive({ step_id: '', resource_id: '', start: '', end: '', note: '' })
const selectedRoute = computed(() => routes.value.find(route => route.id === lines.value.find(line=>line.id === selectedLine.value)?.route_id))
const availableStock = computed(() => stocks.value.filter(stock => stock.line_id === selectedLine.value && ['white','wip'].includes(stock.state) && Number(stock.quantity) > 0))
function localInput(iso: string) { return new Date(Date.parse(iso)+8*3600000).toISOString().slice(0,16) }
function assign(line?: DemandLine, task?: Task) {
  selectedTask.value = task ?? null; selectedLine.value = line?.id ?? lineForTask(task ?? { allocations: [] } as unknown as Task)?.id ?? lines.value[0]?.id ?? ''
  Object.keys(selections).forEach(key=>delete selections[key])
  if (task) task.allocations.forEach(a=>{ selections[a.stock_id] = a.quantity })
  assignment.step_id = task?.step_id ?? selectedRoute.value?.steps[0]?.id ?? ''
  assignment.resource_id = task?.resource_id ?? resources.value[0]?.id ?? ''
  assignment.start = task ? localInput(task.start_at) : `${w.businessDate.value}T08:00`
  assignment.end = task ? localInput(task.end_at) : ''
  assignmentDirty.value=false; assignment.note = task?.note ?? ''; error.value = ''; assignOpen.value = true
}
watch(selectedLine, () => { if (!selectedTask.value) assignment.step_id = selectedRoute.value?.steps[0]?.id ?? '' })
async function previewAssignment() {
  const candidate: TaskDraft = { step_id: assignment.step_id, resource_id: assignment.resource_id, start_at: utc(assignment.start), end_at: utc(assignment.end), allocations: Object.entries(selections).filter(([,qty])=>Number(qty)>0).map(([stock_id,quantity])=>({stock_id,quantity})), note: assignment.note }
  working.value = true; error.value = ''
  try {
    const prior = scenario.value?.snapshot.tasks ?? []
    const replaced = new Set(scenario.value?.snapshot.replace_task_ids ?? [])
    if (selectedTask.value) replaced.add(selectedTask.value.id)
    remember(await w.command<Scenario>('scenarios/preview', { label: '本次手工调整', start_at: new Date(startMs.value).toISOString(), end_at: new Date(endMs.value).toISOString(), tasks: [...prior,candidate], replace_task_ids: [...replaced] }))
    assignOpen.value = false
  } catch (cause) { error.value = w.explain(cause) } finally { working.value = false }
}
let dragged: Task | null = null
function beginDrag(task: Task) { dragged = task }
function clearDrag() { dragged = null }
function dropTask(event: DragEvent, resource: Resource) {
  if (!dragged || dragged.status !== 'planned') return
  const row = event.currentTarget as HTMLElement
  const hours = Math.round((event.clientX - row.getBoundingClientRect().left) / zoom.value * 24 * 2) / 2
  const at = startMs.value + hours * 3600000
  assign(undefined, dragged)
  assignment.resource_id = resource.id
  assignment.start = localInput(new Date(at).toISOString())
  assignment.end = localInput(new Date(at + Date.parse(dragged.end_at) - Date.parse(dragged.start_at)).toISOString())
  dragged = null
}
function changeRail(event: KeyboardEvent) { if (event.key === 'ArrowLeft') railWidth.value = Math.max(240,railWidth.value-8); if (event.key === 'ArrowRight') railWidth.value = Math.min(320,railWidth.value+8) }
function resizeRail(event: PointerEvent) {
  const initial = event.clientX, width = railWidth.value, target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)
  const move = (ev: PointerEvent) => { railWidth.value = Math.min(320,Math.max(240,width+ev.clientX-initial)) }
  const end = () => { target.removeEventListener('pointermove',move); target.removeEventListener('pointerup',end); target.removeEventListener('pointercancel',end) }
  target.addEventListener('pointermove',move); target.addEventListener('pointerup',end); target.addEventListener('pointercancel',end)
}
</script>
<template>
  <div class="spray-page spray-page--flush">
    <header class="spray-schedule-toolbar"><h1>计划调度</h1><div class="spray-tabs"><button :class="{ active:view === 'timeline' }" @click="view='timeline'"><CalendarDays :size="14" />时间轴</button><button :class="{ active:view === 'list' }" @click="view='list'"><List :size="14" />计划表</button></div><div class="spray-actions spray-schedule-dates"><button class="spray-icon-button" aria-label="前一天" @click="moveDate(-1)"><ChevronLeft :size="16" /></button><input v-model="w.businessDate.value" type="date" aria-label="排期起始日期" /><button class="spray-icon-button" aria-label="后一天" @click="moveDate(1)"><ChevronRight :size="16" /></button><select v-model="span" aria-label="排期窗口"><option :value="5">5 日</option><option :value="14">2 周</option></select></div><div class="spray-actions"><ConditionalPlans/><Button v-if="w.can('plan')" variant="outline" @click="assign()"><Plus :size="15" />分配任务</Button><Button v-if="w.can('plan')" :disabled="working" @click="suggest"><Sparkles :size="15" />排期建议</Button></div></header>
    <div v-if="error" class="spray-alert" role="alert">{{ error }}</div>
    <WorkspaceState />
    <div class="spray-planning-body" :style="{'--demand-width': `${railCollapsed ? 46 : railWidth}px`}">
      <aside class="spray-demand-rail" :class="{ collapsed: railCollapsed }"><header><button class="spray-icon-button" :aria-label="railCollapsed ? '展开需求池' : '收起需求池'" @click="railOpen=!railOpen; if(railOpen) w.passportId.value=null"><PanelLeftOpen v-if="railCollapsed" :size="17" /><PanelLeftClose v-else :size="17" /></button><template v-if="!railCollapsed"><strong>待排需求</strong><span>{{ filtered.length }}</span><RouterLink :to="{path: `${SPRAY_BASE}/planning/demands`,query:{factory:w.factory.value}}" aria-label="打开完整需求池"><ArrowUpRight :size="16" /></RouterLink></template></header>
        <template v-if="!railCollapsed"><input v-model="filter" class="spray-rail-search" placeholder="筛选货号、部件、单号" aria-label="筛选待排需求" /><div class="spray-demand-list"><article v-for="line in filtered" :key="line.id" :class="{'urgent':line.priority>0}"><button class="spray-demand-title" @click="w.passportId.value=line.demand_id"><strong>{{ line.item_no }}</strong><span>{{ line.part }}</span><ArrowUpRight :size="13" /></button><p>{{ line.order.counterparty }} · {{ line.color }}</p><div><span>需求 <b>{{ number(line.quantity) }}</b></span><time>{{ line.due_date.slice(5) }} 交期</time></div><div class="spray-demand-progress"><i :style="{width:`${Math.min(100,Number(line.received)/Number(line.quantity)*100)}%`}" /></div><footer><span :class="Number(line.received) > 0 ? 'ready' : ''">{{ Number(line.received) > 0 ? `已收 ${number(line.received)} ${line.unit}` : '等待白件' }}</span><button v-if="w.can('plan')" class="spray-text-button" @click="assign(line)">安排</button></footer></article><div v-if="!filtered.length" class="spray-empty"><strong>需求池为空</strong><RouterLink :to="{path:`${SPRAY_BASE}/planning/demands`,query:{factory:w.factory.value}}" class="spray-text-button">登记订单</RouterLink></div></div><RouterLink class="spray-demand-footer" :to="{path:`${SPRAY_BASE}/planning/demands`,query:{factory:w.factory.value}}"><Plus :size="14" />登记 / 查看全部需求</RouterLink></template><span v-else class="spray-rail-count">{{ lines.length }}</span>
      </aside><div v-if="!railCollapsed" class="spray-rail-resize" role="separator" tabindex="0" aria-label="调整需求池宽度" aria-orientation="vertical" :aria-valuenow="railWidth" :aria-valuemin="240" :aria-valuemax="320" @pointerdown="resizeRail" @keydown="changeRail" />
      <section class="spray-schedule-center">
        <div class="spray-risk-strip"><span class="spray-status-dot" /><span>{{ scenario ? `当前方案 · ${scenario.snapshot.tasks.length} 项建议` : `已发布 ${tasks.length} 个任务` }}</span><span v-if="scenario?.snapshot.unplanned.length" class="spray-risk-count">{{ scenario.snapshot.unplanned.length }} 项暂不可安排</span><span class="spray-muted">排期以已确认工艺、准备及合格来料为依据</span><label class="spray-zoom">缩放<input v-model.number="zoom" type="range" min="180" max="720" step="60" aria-label="时间轴缩放" /></label></div>
        <div v-if="!resources.length" class="spray-empty spray-empty--full"><strong>先登记可安排的生产资源</strong><p>工作位、能力与日历确认后，时间轴会自动建立真实资源行。</p><RouterLink :to="{path:`${SPRAY_BASE}/master`,query:{factory:w.factory.value}}" class="spray-secondary">登记资源与工艺<ArrowUpRight :size="15" /></RouterLink></div>
        <div v-else-if="view === 'timeline'" class="spray-timeline" :style="{'--day-width': `${zoom}px`, '--canvas-width':`${span*zoom}px`}">
          <div class="spray-time-header"><div class="spray-resource-heading">生产资源 <small>{{ resources.length }}</small></div><div class="spray-time-scale"><div v-for="day in days" :key="day.toISOString()"><strong>{{ dateLabel(day) }}</strong><div><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span></div></div></div></div>
          <template v-for="group in [{key:'manual',label:'手喷'},{key:'automatic',label:'自动'},{key:'pad',label:'移印'}]" :key="group.key"><div v-if="resources.some(r=>r.kind === group.key)" class="spray-resource-group"><span>{{ group.label }}</span><small>{{ resources.filter(r=>r.kind === group.key).length }} 项资源</small></div><div v-for="resource in resources.filter(r=>r.kind === group.key)" :key="resource.id" class="spray-resource-row"><div class="spray-resource-label"><span class="spray-status-dot" /><div><strong>{{ resource.name }}</strong><small>{{ resource.code }} · {{ resource.capabilities.map(c=>c.capability).join(' / ') || '能力待确认' }}</small></div></div><div class="spray-resource-track" @dragover.prevent @drop.prevent="dropTask($event,resource)">
            <div v-for="window in resource.calendar.filter(window=>window.kind !== 'available' && Date.parse(window.start_at)<endMs && Date.parse(window.end_at)>startMs)" :key="window.id" class="spray-downtime" :style="band(window)">{{ window.reason || '资源不可用' }}</div>
            <button v-for="plan in w.items('forecasts').filter(p=>p.resource_id===resource.id&&p.status==='conditional')" :key="plan.id" class="spray-task-band is-draft" :style="band(plan as unknown as Task)" :title="String(plan.condition)" @click="w.passportId.value=lines.find(l=>l.id===plan.line_id)?.demand_id??null"><strong>条件计划 · {{lines.find(l=>l.id===plan.line_id)?.item_no}}</strong><span>{{number(plan.quantity)}} · 未匹配实物</span></button>
            <button v-for="task in tasks.filter(task=>task.resource_id === resource.id && (!scenario?.snapshot.replace_task_ids.includes(task.id) || compare))" :key="task.id" :draggable="w.can('plan') && task.status === 'planned'" class="spray-task-band" :class="[task.status,{'is-original':scenario?.snapshot.replace_task_ids.includes(task.id)}]" :style="band(task)" :title="taskTitle(task)" :aria-label="taskTitle(task)" @dragstart="beginDrag(task)" @dragend="clearDrag" @click="task.status === 'planned' && w.can('plan') ? assign(undefined,task) : w.passportId.value=lineForTask(task)?.demand_id ?? null"><strong>{{ lineForTask(task)?.item_no }} · {{ lineForTask(task)?.part }}</strong><span>{{ stepName(task.step_id) }} · {{ number(task.quantity) }}</span></button>
            <button v-for="(task,i) in scenario?.snapshot.tasks.filter(task=>task.resource_id === resource.id) ?? []" :key="'draft'+i" class="spray-task-band is-draft" :style="band(task)" :title="taskTitle(task)" @click="w.passportId.value=lineForTask(task)?.demand_id ?? null"><strong>{{ lineForTask(task)?.item_no }} · {{ lineForTask(task)?.part }}</strong><span>{{ stepName(task.step_id) }} · 本次建议</span></button>
          </div></div></template>
          <div class="spray-timeline-floor"><span>横向滚动查看未来 {{ span }} 日；点击任务可分配资源和时间。</span></div>
        </div>
        <div class="spray-schedule-list" :class="{ 'always-visible':view==='list' }"><article v-for="task in tasks" :key="task.id"><div><span class="spray-badge">{{ resources.find(r=>r.id === task.resource_id)?.name }}</span><strong>{{ lineForTask(task)?.item_no }} · {{ lineForTask(task)?.part }}</strong><p>{{ stepName(task.step_id) }} · {{ number(task.quantity) }} 件</p><small>{{ dateTime(task.start_at) }} — {{ dateTime(task.end_at) }}</small></div><button class="spray-secondary" @click="task.status === 'planned' && w.can('plan') ? assign(undefined,task) : w.passportId.value=lineForTask(task)?.demand_id ?? null">{{ task.status === 'planned' ? '分配 / 调整' : '订单追踪' }}</button></article><div v-if="!tasks.length" class="spray-empty"><strong>该窗口尚无已发布任务</strong><p>登记来料并完成准备后，可生成排期建议。</p><RouterLink :to="{path:`${SPRAY_BASE}/planning/demands`,query:{factory:w.factory.value}}" class="spray-secondary">查看需求池</RouterLink></div></div>
        <div v-if="scenario?.snapshot.unplanned.length" class="spray-unplanned"><details><summary>{{ scenario.snapshot.unplanned.length }} 条需求的未排原因</summary><p v-for="(item,index) in scenario.snapshot.unplanned" :key="index"><b>{{ lines.find(line=>line.id === item.line_id)?.item_no }}</b> {{ item.message }}</p></details></div>
        <footer class="spray-timeline-legend"><span><i class="actual" />实际执行</span><span><i />已发布计划</span><span><i class="draft" />本次建议</span><span><i class="blocked" />停机 / 缺勤</span><small>厂区数据 · {{ w.asOf.value ? dateTime(w.asOf.value) : '待刷新' }}</small></footer>
      </section>
    </div>
    <div v-if="scenario" class="spray-decision-dock"><div><span class="spray-badge">本次调整</span><strong>{{ scenario.snapshot.tasks.length }} 项 · 影响 {{ affected }} 张订单</strong><small>尚未占用库存与资源</small></div><div class="spray-actions"><button class="spray-icon-button" aria-label="撤销上次草稿调整" @click="undo"><Undo2 :size="18" /></button><button class="spray-secondary" @click="discard">放弃草稿</button><button class="spray-secondary" :aria-pressed="compare" @click="compare=!compare">{{ compare ? '结束比较' : '比较前后' }}</button><Button :disabled="working || !scenario.snapshot.tasks.length" @click="publish"><Check :size="16" />发布本次调整</Button></div></div>
    <WorkspaceDialog :open="assignOpen" title="分配资源与时间" @close="closeAssignment"><form id="spray-assign-form" class="spray-form" @input="assignmentDirty=true;w.dirty.value=true" @submit.prevent="previewAssignment"><label class="wide">订单部位<select v-model="selectedLine" :disabled="!!selectedTask" required><option v-for="line in lines" :key="line.id" :value="line.id">{{ line.item_no }} / {{ line.part }} · {{ line.order.document_no }}</option></select></label><label>工序<select v-model="assignment.step_id" required><option v-for="step in selectedRoute?.steps" :key="step.id" :value="step.id">{{ step.name }} · {{ step.capability }}</option></select></label><label>生产资源<select v-model="assignment.resource_id" required><option v-for="resource in resources" :key="resource.id" :value="resource.id">{{ resource.name }}</option></select></label><label>预计开始<input v-model="assignment.start" type="datetime-local" required /></label><label>预计结束<input v-model="assignment.end" type="datetime-local" required /></label><fieldset class="wide spray-stock-picker"><legend>选取实际来料批次</legend><label v-for="stock in availableStock" :key="stock.id"><span>{{ stock.batch_id.slice(0,8) }} · {{ stock.state === 'white' ? '白件' : '在制' }}<small>库存 {{ number(stock.quantity) }} · 已预留 {{ number(stock.reserved) }}</small></span><input v-model="selections[stock.id]" inputmode="numeric" :aria-label="'批次数量 '+stock.id.slice(0,8)" placeholder="本次安排数" /></label><p v-if="!availableStock.length" class="spray-muted">没有可选合格来料，请先登记接收与准备。</p></fieldset><label class="wide">调整依据<textarea v-model="assignment.note" /></label><p v-if="error" class="spray-alert wide" role="alert">{{ error }}</p></form><template #footer><Button variant="outline" @click="closeAssignment">取消</Button><Button type="submit" form="spray-assign-form" :disabled="working">预览本次调整</Button></template></WorkspaceDialog>
  </div>
</template>
