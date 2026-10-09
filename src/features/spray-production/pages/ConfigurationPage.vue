<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Plus, Workflow, Users, Wrench, Check, X, ArrowRight, Package } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useSprayPage } from '../usePage'
import { today, utc, dateTime, stateLabel, type Resource, type RouteVersion, type Rule, type Entity } from '../contracts'
import CalendarEditor from '../components/CalendarEditor.vue'
import WorkspaceDialog from '../components/WorkspaceDialog.vue'
import WorkspaceState from '../components/WorkspaceState.vue'
import RecordTable from '../components/RecordTable.vue'
const w = useSprayPage(['resources', 'routes', 'employees', 'materials', 'rules'])
const calendarResource = ref<Resource | null>(null)
const tab = ref('resources'), open = ref(false), saving = ref(false), localError = ref('')
const tabs = [{ key: 'resources', label: '资源与日历' }, { key: 'routes', label: '部件与工艺' }, { key: 'employees', label: '生产人员' }, { key: 'materials', label: '物料与单位' }, { key: 'rules', label: '核算规则' }]
const parameterLabels:Record<string,string>={method:'计薪方法',basis:'产量口径',rate:'正班单价',overtime_rate:'加班单价',nonproductive_rate:'非生产工时单价',currency:'币种',exchange_rule_id:'汇率版本',daily_guarantee:'每日保底',reference_hours:'基准小时',paid_hours:'计薪小时',from_unit:'原单位',to_unit:'换算单位',factor:'换算倍率',from_currency:'原币种',to_currency:'目标币种',price:'工序单价'}
const form = reactive({ code: '', name: '', kind: 'manual', capacity: 1, capability: '', hourly_capacity: '', start: '', end: '', evidence: '', revision: 1, confirmed: false, unit: 'KG', rule_kind: 'wage', effective_from: today(), material_id: '', step_id: '', from_unit: '', to_unit: '', factor: '', method: 'team_piece', basis: 'processed', rate: '', currency: 'CNY', daily_guarantee: '0', overtime_rate: '', nonproductive_rate: '', exchange_rule_id: '', reference_hours: '', paid_hours: '', from_currency: 'HKD', to_currency: 'CNY' })
const steps = ref([{ code: 'S1', name: '', capability: '', predecessors: '', input_unit: '件', output_unit: '件', output_ratio: '1', drying_minutes: 0, prep_required: true, tool_id: '', crew_id: '' }])
const resourceKind: Record<string, string> = { manual: '手喷工作位', automatic: '自动线', pad: '移印', tool: '共享工装', crew: '作业班组' }
const resources = computed(() => w.items<Resource>('resources'))
const routes = computed(() => w.items<RouteVersion>('routes'))
const rules = computed(() => w.items<Rule>('rules'))
const canCreate = computed(() => tab.value === 'rules' ? w.can('cost_write') || w.can('payroll_write') : w.can('master_write'))
const title = computed(() => ({ resources: '登记真实生产资源', routes: '建立工艺版本', employees: '登记生产人员', materials: '登记材料 SKU', rules: '建立核算规则草稿' })[tab.value])
function create() { if(tab.value==='rules')form.rule_kind=w.can('payroll_write')?'wage':'unit'; form.code = ''; form.name = ''; form.evidence = ''; localError.value = ''; open.value = true }
watch(form, () => { if (open.value) w.dirty.value = true })
watch(steps, () => { if (open.value) w.dirty.value = true }, { deep: true })
async function close() { if (w.dirty.value && !(await w.confirmDiscard('放弃当前未保存的基础资料？'))) return; open.value = false; w.dirty.value = false }
async function save() {
  saving.value = true; localError.value = ''
  try {
    let body: Record<string, unknown>
    if (tab.value === 'resources') {
      body = { code: form.code, name: form.name, kind: form.kind, capacity: form.capacity, capabilities: form.capability ? [{ capability: form.capability, hourly_capacity: form.hourly_capacity || null, evidence: form.evidence }] : [], calendar: form.start && form.end ? [{ start_at: utc(form.start), end_at: utc(form.end), kind: 'available', reason: form.evidence }] : [] }
    } else if (tab.value === 'routes') {
      body = { code: form.code, label: form.name, revision: form.revision, evidence: form.evidence, confirmed: form.confirmed, steps: steps.value.map(step => ({ ...step, predecessors: step.predecessors.split(/[,，\s]+/).filter(Boolean), tool_id: step.tool_id || null, crew_id: step.crew_id || null })) }
    } else if (tab.value === 'rules') {
      let parameters: Record<string, unknown>
      if (form.rule_kind === 'wage') parameters = { method: form.method, basis: form.basis, rate: form.rate, currency: form.currency, daily_guarantee: form.daily_guarantee, overtime_rate: form.overtime_rate || null, nonproductive_rate: form.nonproductive_rate || null, exchange_rule_id: form.exchange_rule_id || null, reference_hours: form.reference_hours || null, paid_hours: form.paid_hours || null }
      else if (form.rule_kind === 'unit') parameters = { from_unit: form.from_unit, to_unit: form.to_unit, factor: form.factor }
      else if (form.rule_kind === 'exchange') parameters = { from_currency: form.from_currency, to_currency: form.to_currency, factor: form.factor }
      else parameters = { price: form.rate, currency: form.currency }
      body = { code: form.code, label: form.name, kind: form.rule_kind, revision: form.revision, effective_from: form.effective_from, parameters, evidence: form.evidence, material_id: form.material_id || null, step_id: form.step_id || null }
    } else body = { code: form.code, name: form.name, ...(tab.value === 'materials' ? { unit: form.unit } : {}) }
    await w.command(tab.value, body)
    open.value = false
    await w.load([tab.value])
  } catch (cause) { localError.value = w.explain(cause) } finally { saving.value = false }
}
const confirming = ref<Rule | null>(null), confirmReason = ref('')
async function confirmRule() {
  if (!confirming.value) return
  try { await w.command(`rules/${confirming.value.id}/confirm`, { business_date: w.businessDate.value, reason: confirmReason.value }, confirming.value.version); confirming.value = null; await w.load(['rules']) } catch (cause) { localError.value = w.explain(cause) }
}
</script>
<template>
  <div class="spray-page">
    <header class="spray-page-heading"><div><span class="spray-eyebrow">FOUNDATION / 基础资料</span><h1>让每一次安排都有依据</h1><p>真实资源、确认工艺和版本化规则，共同支撑生产与核算。</p></div><Button v-if="canCreate" @click="create"><Plus :size="16" />{{ tab === 'rules' ? '新建规则' : tab === 'routes' ? '新建工艺版本' : '新增资料' }}</Button></header>
    <WorkspaceState />
    <div class="spray-tabs" role="tablist"><button v-for="item in tabs" :key="item.key" :class="{ active: tab === item.key }" role="tab" :aria-selected="tab === item.key" @click="tab = item.key">{{ item.label }}</button></div>
    <div v-if="tab === 'resources'" class="spray-resource-grid">
      <article v-for="resource in resources" :key="resource.id" class="spray-panel"><div class="spray-panel__header"><div class="spray-actions"><Wrench :size="18" /><h3>{{ resource.name }}</h3></div><span class="spray-badge">{{ resourceKind[resource.kind] }}</span></div><div class="spray-panel__body"><p class="spray-muted">{{ resource.code }} · 同时容纳 {{ resource.capacity }} 个任务</p><dl class="spray-passport__facts"><div v-for="cap in resource.capabilities" :key="cap.id"><dt>{{ cap.capability }}</dt><dd>{{ cap.hourly_capacity ?? '待确认' }} 件 / 小时</dd></div></dl><div class="spray-actions"><h3>工作日历</h3><button v-if="w.can('master_write')" class="spray-text-button" @click="calendarResource=resource">调整日历</button></div><p v-for="period in resource.calendar" :key="period.id" class="spray-calendar-row">{{ dateTime(period.start_at) }} — {{ dateTime(period.end_at) }} <span>{{ period.kind === 'available' ? '可安排' : '不可用' }}</span></p><p v-if="!resource.calendar.length" class="spray-muted">尚未登记工作时间，不参与自动排期。</p></div></article>
      <div v-if="!resources.length" class="spray-empty"><strong>从真实工作位开始</strong><p>登记设备、班组和工作日历后，即可安排订单工序。</p><Button v-if="canCreate" variant="outline" @click="create">登记第一项资源</Button></div>
    </div>
    <div v-else-if="tab === 'routes'" class="spray-route-list"><article v-for="route in routes" :key="route.id" class="spray-panel"><div class="spray-panel__header"><div><h3>{{ route.label }}</h3><p class="spray-muted">{{ route.code }} · 版本 {{ route.revision }}</p></div><span class="spray-badge" :class="{ 'spray-badge--amber': route.status !== 'confirmed' }">{{ stateLabel[route.status] }}</span></div><div class="spray-route-chain"><div v-for="step in route.steps" :key="step.id"><span>{{ step.code }}</span><strong>{{ step.name }}</strong><small>{{ step.predecessors.length ? `前置 ${step.predecessors.length} 道工序` : '来料' }} · {{ step.capability }}</small></div></div><p class="spray-route-evidence">{{ route.evidence || '确认依据待补充' }}</p></article><div v-if="!routes.length" class="spray-empty"><strong>每个部位拥有自己的工艺路线</strong><p>可定义任意工序和前置依赖，不强制按手喷、自动、移印排列。</p></div></div>
    <RecordTable v-else-if="tab === 'rules'" :rows="rules" :columns="[{key:'label',label:'规则'}, {key:'kind',label:'口径'}, {key:'revision',label:'版本'}, {key:'effective_from',label:'生效日期'}, {key:'status',label:'状态'}]"><template #actions="{ row }"><button v-if="row.status === 'draft' && (row.kind === 'wage' ? w.can('payroll_write') : w.can('cost_write'))" class="spray-text-button" @click.stop="confirming = row as Rule; confirmReason = ''; localError = ''">核对并确认</button><span v-else class="spray-muted">保留此版本依据</span></template></RecordTable>
    <RecordTable v-else :rows="w.items(tab)" :columns="[{key:'code',label:'稳定编号'}, {key:'name',label:'名称'}, ...(tab === 'materials' ? [{key:'unit',label:'库存单位'}] : [{key:'enabled',label:'启用'}])]" />
    <CalendarEditor :resource="calendarResource" @close="calendarResource=null" />
    <WorkspaceDialog :open="open" :title="title ?? '基础资料'" :wide="tab === 'routes'" @close="close">
      <form id="spray-master-form" class="spray-form" @submit.prevent="save">
        <label>编号<input v-model="form.code" required /></label><label>名称<input v-model="form.name" required /></label>
        <template v-if="tab === 'resources'"><label>资源类型<select v-model="form.kind"><option v-for="(label, key) in resourceKind" :key="key" :value="key">{{ label }}</option></select></label><label>并发容量<input v-model.number="form.capacity" type="number" min="1" required /></label><label>工序能力编码<input v-model="form.capability" placeholder="与工艺能力编码保持一致" /></label><label>确认的每小时产能<input v-model="form.hourly_capacity" inputmode="decimal" placeholder="未知可留空" /></label><label>工作时间开始<input v-model="form.start" type="datetime-local" /></label><label>工作时间结束<input v-model="form.end" type="datetime-local" /></label></template>
        <template v-if="tab === 'routes'"><label>工艺版本<input v-model.number="form.revision" type="number" min="1" /></label><label class="check"><input v-model="form.confirmed" type="checkbox" />已核对并确认此工艺</label><div class="wide spray-step-editor"><section v-for="(step, i) in steps" :key="i"><header><strong>工序 {{ i+1 }}</strong><button v-if="steps.length > 1" type="button" class="spray-icon-button" aria-label="删除工序" @click="steps.splice(i,1)"><X :size="15" /></button></header><div class="spray-form"><label>工序编码<input v-model="step.code" required /></label><label>工序名称<input v-model="step.name" required /></label><label>所需能力<input v-model="step.capability" required /></label><label>前置工序编码<input v-model="step.predecessors" placeholder="如 S1,S2；起始工序留空" /></label><label>输入单位<input v-model="step.input_unit" required /></label><label>输出单位<input v-model="step.output_unit" required /></label><label>输入 1 单位对应输出<input v-model="step.output_ratio" inputmode="decimal" required /></label><label>晾干 / 转序分钟<input v-model.number="step.drying_minutes" type="number" min="0" /></label><label>共用工具<select v-model="step.tool_id"><option value="">无需共用工具</option><option v-for="r in resources.filter(r=>r.kind === 'tool')" :key="r.id" :value="r.id">{{ r.name }}</option></select></label><label>所需班组<select v-model="step.crew_id"><option value="">不限定班组</option><option v-for="r in resources.filter(r=>r.kind === 'crew')" :key="r.id" :value="r.id">{{ r.name }}</option></select></label><label class="check wide"><input v-model="step.prep_required" type="checkbox" />开工前需要确认准备</label></div></section><button type="button" class="spray-secondary" @click="steps.push({code:`S${steps.length+1}`,name:'',capability:'',predecessors:'',input_unit:'件',output_unit:'件',output_ratio:'1',drying_minutes:0,prep_required:true,tool_id:'',crew_id:''})"><Plus :size="16" />增加工序</button></div></template>
        <label v-if="tab === 'materials'">库存单位<input v-model="form.unit" required placeholder="KG / L / 桶 / 卡" /></label>
        <template v-if="tab === 'rules'"><label>规则口径<select v-model="form.rule_kind"><option v-if="w.can('payroll_write')" value="wage">员工工资</option><option v-if="w.can('cost_write')" value="unit">SKU 单位换算</option><option v-if="w.can('cost_write')" value="exchange">币种折算</option><option v-if="w.can('cost_write')" value="operation_price">工序产值单价</option></select></label><label>版本<input v-model.number="form.revision" type="number" min="1" /></label><label>生效日期<input v-model="form.effective_from" type="date" required /></label>
          <template v-if="form.rule_kind === 'wage'"><label>计薪方法<select v-model="form.method"><option value="team_piece">班组计件（再按权重分摊）</option><option value="personal_piece">个人计件</option><option value="hourly">按实际工时</option><option value="fixed_shift">每日固定</option><option value="historical_normalized">历史时长折算试算</option></select></label><label>产量口径<select v-model="form.basis"><option value="processed">加工数量</option><option value="good">合格数量</option></select></label><label>确认单价<input v-model="form.rate" inputmode="decimal" required /></label><label>加班单价（依计薪方法）<input v-model="form.overtime_rate" inputmode="decimal" placeholder="留空须待核" /></label><label>非生产每小时单价<input v-model="form.nonproductive_rate" inputmode="decimal" placeholder="留空须待核" /></label><label>工资币种折算<select v-model="form.exchange_rule_id"><option value="">无需币种折算</option><option v-for="rule in rules.filter(r=>r.kind==='exchange')" :key="rule.id" :value="rule.id">{{rule.label}} · V{{rule.revision}} · {{stateLabel[rule.status]}}</option></select></label><label>每天保底<input v-model="form.daily_guarantee" inputmode="decimal" /></label><label>币种<select v-model="form.currency"><option>CNY</option><option>HKD</option><option>USD</option></select></label><template v-if="form.method === 'historical_normalized'"><label>基准小时<input v-model="form.reference_hours" inputmode="decimal" required /></label><label>计薪小时<input v-model="form.paid_hours" inputmode="decimal" required /></label></template></template>
          <template v-if="form.rule_kind === 'unit'"><label>限定物料<select v-model="form.material_id" required><option value="">选择材料</option><option v-for="mat in w.items('materials')" :key="mat.id" :value="mat.id">{{ mat.code }} {{ mat.name }}</option></select></label><label>原单位<input v-model="form.from_unit" required /></label><label>目标单位<input v-model="form.to_unit" required /></label><label>1 原单位对应目标数量<input v-model="form.factor" inputmode="decimal" required /></label></template>
          <template v-if="form.rule_kind === 'exchange'"><label>原币种<select v-model="form.from_currency"><option>CNY</option><option>HKD</option><option>USD</option></select></label><label>目标币种<select v-model="form.to_currency"><option>CNY</option><option>HKD</option><option>USD</option></select></label><label>原金额 × 此系数 = 目标金额<input v-model="form.factor" inputmode="decimal" required /></label></template>
          <template v-if="form.rule_kind === 'operation_price'"><label>工艺工序<select v-model="form.step_id" required><option value="">选择工序版本</option><optgroup v-for="route in routes" :key="route.id" :label="route.label + ' V' + route.revision"><option v-for="step in route.steps" :key="step.id" :value="step.id">{{ step.name }}</option></optgroup></select></label><label>合格品工序单价<input v-model="form.rate" inputmode="decimal" required /></label><label>币种<select v-model="form.currency"><option>CNY</option><option>HKD</option><option>USD</option></select></label></template>
        </template>
        <label v-if="['resources','routes','rules'].includes(tab)" class="wide">来源与确认依据<textarea v-model="form.evidence" :required="tab !== 'resources' || !!form.hourly_capacity" placeholder="记录确认人、合同 / 测试依据及适用范围" /></label>
        <p v-if="tab === 'rules'" class="spray-alert wide">新规则保存为草稿；在核对并确认后，才能用于正式核算。</p><p v-if="localError" role="alert" class="spray-alert wide">{{ localError }}</p>
      </form><template #footer><Button variant="outline" @click="close">取消</Button><Button type="submit" form="spray-master-form" :disabled="saving">{{ saving ? '保存中…' : '保存资料' }}</Button></template>
    </WorkspaceDialog>
    <WorkspaceDialog :open="!!confirming" title="核对并确认规则版本" @close="confirming = null"><p>{{ confirming?.label }} · 版本 {{ confirming?.revision }}</p><dl class="spray-passport__facts"><div v-for="(value,key) in confirming?.parameters" :key="key"><dt>{{ parameterLabels[key]??key }}</dt><dd>{{ value === null ? '未设置' : stateLabel[String(value)]??value }}</dd></div></dl><div class="spray-form"><label class="wide">确认依据<textarea v-model="confirmReason" required /></label></div><p v-if="localError" class="spray-alert">{{ localError }}</p><template #footer><Button variant="outline" @click="confirming = null">返回核对</Button><Button :disabled="!confirmReason.trim()" @click="confirmRule">确认此版本</Button></template></WorkspaceDialog>
  </div>
</template>
