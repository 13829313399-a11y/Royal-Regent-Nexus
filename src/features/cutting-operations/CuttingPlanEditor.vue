<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { cuttingApi, errorMessage, type BomData, type MasterRecord, type ResourceData } from './api'
import CuttingDailyPlanTools from './CuttingDailyPlanTools.vue'
import type { OrderData } from './ordersApi'
import type { PlanTaskInput } from './planning'
const props = defineProps<{ data: OrderData }>()
const tasks = defineModel<PlanTaskInput[]>({ required: true })
const removedTaskReasons = defineModel<Record<string, string>>('removedTaskReasons', { default: () => ({}) })
const resourceCache = ref<Record<string, MasterRecord>>({})
const missingOriginalTasks = computed(() => {
  const originals = new Map([...(props.data.planning?.published?.tasks ?? []),...(props.data.planning?.draft?.tasks ?? [])].map(t=>[t.task_id,t]))
  return [...originals.values()].filter(t=>!tasks.value.some(n=>n.task_id===t.task_id) && (t.prerequisite_required || t.prerequisite_date || t.actual_prerequisite_date) && !props.data.planning?.draft?.removed_task_reasons?.[t.task_id])
})
const query = ref(''), resources = ref<MasterRecord[]>([]), page = ref(1), total = ref(0), error = ref(''), busy = ref(false)
let alive = true, generation = 0
onBeforeUnmount(() => { alive = false; generation++ })
watch(query, () => { generation++; resources.value = []; busy.value = false; error.value = '' }, { flush: 'sync' })
async function search(next = 1) {
  const request = ++generation; busy.value = true; error.value = ''
  try {
    const result = await cuttingApi.list('resource', next, query.value)
    if (!alive || request !== generation) return
    resources.value = result.data.filter(r => r.status === 'active'); total.value = result.total; page.value = next
    for (const r of resources.value) resourceCache.value[`${r.id}:${r.version}`] = r
  } catch (e) { if (alive && request === generation) error.value = errorMessage(e) }
  finally { if (alive && request === generation) busy.value = false }
}
function add(resource: MasterRecord) {
  if (tasks.value.reduce((sum, t) => sum + Number(t.target_sets), 0) >= (props.data.target_sets ?? 0)) { error.value = '订单目标已全部分配，请先调整原任务数量'; return }
  tasks.value.push({ task_id: crypto.randomUUID(), name: `${resource.data.name}裁剪`, resource_id: resource.id,
    resource_version: resource.version, date_basis: 'estimated', preparation_workdays: (resource.data as ResourceData).preparation_workdays ?? 3, resource_change_basis:'', prerequisite_required: false, prerequisite_change_reason: '', actual_prerequisite_date: null, actual_prerequisite_reference: '', target_sets: Math.max(1, (props.data.target_sets ?? 1) - tasks.value.reduce((sum, t) => sum + Number(t.target_sets), 0)),
    materials: (props.data.bom?.data as BomData).requirements.flatMap((r, row) => r.required_for_cutting ? [{ row, expected_date: props.data.batches.filter(b => b.row === row).map(b => b.expected_date).sort().at(-1) ?? null }] : []),
    readiness_basis: '', actual_issue_date: null, actual_issue_reference: '', prerequisite_date: null, prerequisite_basis: '', days: [] })
}
function remove(index: number) {
  const task = tasks.value[index]!
  const old = (props.data.planning?.draft ?? props.data.planning?.published)?.tasks.find(t => t.task_id === task.task_id)
  if (old && (old.prerequisite_required || old.prerequisite_date || old.actual_prerequisite_date)) {
    const reason = window.prompt('移除有前置工序要求的原任务，请填写取消依据（至少4字）。更换执行方可直接使用下方替换按钮。')?.trim()
    if (!reason || reason.length < 4) { error.value = '取消依据不足，任务保留'; return }
    removedTaskReasons.value[task.task_id] = reason
  } else if (!window.confirm('移除此草稿任务及其日计划？已保存历史仍保留。')) return
  tasks.value.splice(index, 1)
}
function replaceResource(task: PlanTaskInput, resource: MasterRecord) {
  task.resource_id = resource.id; task.resource_version = resource.version
  // Keep task identity, prerequisite requirements, targets and original daily draft.
  // Actual evidence for the previous executor must be checked again.
  task.date_basis = 'estimated'; task.actual_issue_date = null; task.actual_issue_reference = ''
  task.resource_change_basis = ''
  task.actual_prerequisite_date = null; task.actual_prerequisite_reference = ''
}
function resourceFor(task: PlanTaskInput) {
  return resourceCache.value[`${task.resource_id}:${task.resource_version}`] ?? [props.data.planning?.draft, props.data.planning?.published].flatMap(p => p?.tasks ?? []).find(t => t.resource_id === task.resource_id && t.resource_version === task.resource_version)?.resource
}
function calendarFor(task: PlanTaskInput) {
  const resource = resourceFor(task)
  return resource ? (resource.data as ResourceData).calendar ?? null : undefined
}
function executorChanged(task: PlanTaskInput) {
  return [props.data.planning?.draft,props.data.planning?.published].some(p => p?.tasks.some(t => t.task_id === task.task_id && t.resource_id !== task.resource_id))
}
function materialName(row: number) {
  const requirement = (props.data.bom?.data as BomData).requirements[row]
  return requirement ? props.data.bom?.material_references?.[`${requirement.material_id}:${requirement.material_version}`]?.name ?? `物料行 ${row+1}` : '原物料行已失效'
}
</script>
<template>
  <section class="plan-editor">
    <p>订单目标 {{ data.target_sets }} 套；下列任务按完整配套套数拆分。先安排部分部件的裁片计划在后续填数阶段衔接。</p>
    <div class="plan-tools"><label>执行方编码／名称 <input v-model="query" maxlength="80" /></label><Button variant="outline" type="button" :disabled="busy" @click="search()">查本厂／外发资源</Button>
      <Button variant="outline" type="button" :disabled="busy || page <= 1" @click="search(page-1)">资源上一页</Button><Button variant="outline" type="button" :disabled="busy || page*50 >= total" @click="search(page+1)">资源下一页</Button>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <div class="plan-tools"><Button variant="outline" v-for="r in resources" :key="r.id" type="button" @click="add(r)">增加任务：{{ r.code }} · {{ r.data.name }} V{{ r.version }}</Button></div>
    <div class="plan-tools"><Button variant="outline" v-for="r in resources.filter(r => tasks.some(t => t.resource_id === r.id && t.resource_version !== r.version))" :key="r.id" type="button" @click="tasks.filter(t => t.resource_id === r.id).forEach(t => { t.resource_version = r.version })">采用 {{ r.data.name }} 最新资料／日历 V{{ r.version }}</Button></div>
    <p v-if="!tasks.length">先选择有效执行方，建立本厂或外发任务。</p>
    <label v-for="old in missingOriginalTasks" :key="old.task_id">取消原任务「{{ old.name }}」及前置要求的依据 <input v-model="removedTaskReasons[old.task_id]" required minlength="4" maxlength="500" /></label>
    <article v-for="(task, index) in tasks" :key="task.task_id" class="plan-task">
      <h4>执行任务 {{ index+1 }}</h4><label>任务名称 <input v-model="task.name" required maxlength="120" /></label>
      <p>执行方：{{ resourceFor(task)?.data.name ?? '请查询当前资料' }} · V{{ task.resource_version }}；更换执行方保留任务及前置要求，实际凭据须重新核对。</p>
      <div class="plan-tools"><Button variant="outline" v-for="r in resources" :key="r.id" type="button" :disabled="r.id === task.resource_id && r.version === task.resource_version" @click="replaceResource(task,r)">替换为：{{ r.data.name }} V{{ r.version }}</Button></div>
      <label>任务目标套数 <input v-model.number="task.target_sets" type="number" min="1" max="1000000000" step="1" required /></label>
      <label>计划日期依据 <select v-model="task.date_basis"><option value="estimated">提前预排（采购预计交期）</option><option value="actual">实际核定（实际领料与就绪）</option></select></label>
      <label>供数准备工作日 <input v-model.number="task.preparation_workdays" type="number" min="0" max="365" step="1" required /></label>
      <p>3 个工作日为默认建议，可按任务缩短或延长。大于 0 时就绪当天不计；0 天可在就绪当日供数，若为休息日顺延至下一工作日。提前预排与实际核定均采用本任务设置。</p>
      <h4>当前裁剪必需料预计日期</h4>
      <p>采购回复交期后即可预排，无需实际领料。带入当前最晚回复日期，可按该任务批次核定；部分到料支持数量须写明依据。</p>
      <ul><li v-for="b in data.batches" :key="`${b.row}-${b.purchase_reference}-${b.expected_date}`">采购需求行 {{ b.row+1 }}：{{ b.expected_date }} · {{ b.quantity }} · {{ b.purchase_reference }}</li></ul>
      <label v-for="material in task.materials" :key="material.row">{{ material.row+1 }} · {{ materialName(material.row) }} <input :value="material.expected_date ?? ''" type="date" @input="material.expected_date = ($event.target as HTMLInputElement).value || null" /></label>
      <label>实际领料日期 <input :value="task.actual_issue_date ?? ''" type="date" @input="task.actual_issue_date = ($event.target as HTMLInputElement).value || null" /></label>
      <label>领料单号／实际领料凭据 <input v-model="task.actual_issue_reference" maxlength="500" :required="!!task.actual_issue_date" /></label>
      <label v-if="executorChanged(task)">更换执行方后的实际凭据复核依据 <input v-model="task.resource_change_basis" maxlength="500" :required="!!(task.actual_issue_date || task.actual_prerequisite_date)" placeholder="填写该执行方的领料／前置凭据核对依据" /></label>
      <p>领料日期须据实登记且不得晚于今天；布料仓接口尚未接通，此处保留人工核对依据，不重复生成出库或库存。</p>
      <p>提前预排使用必需料及前置工序预计日期；实际核定使用实际领料及前置工序实际就绪日期。两者均按资源日历及任务准备周期计算，未配置默认周一至周六工作、周日休息。</p>
      <label>批次物料日期／数量支持依据 <textarea v-model="task.readiness_basis" maxlength="500" placeholder="说明该批目标套数所需物料的预计来源和数量；此处不预留或扣减库存" /></label>
      <label><input v-model="task.prerequisite_required" type="checkbox" />本任务需要贴合／捆条等前置工序</label>
      <label v-if="!task.prerequisite_required">取消原前置工序的核对依据（原任务有要求时必填） <input v-model="task.prerequisite_change_reason" maxlength="500" /></label>
      <label>贴合／捆条等前置工序预计就绪 <input :value="task.prerequisite_date ?? ''" type="date" @input="task.prerequisite_date = ($event.target as HTMLInputElement).value || null" /></label>
      <label>前置工序说明 <input v-model="task.prerequisite_basis" maxlength="500" /></label>
      <template v-if="task.date_basis === 'actual'">
        <label>前置工序实际就绪日期 <input :value="task.actual_prerequisite_date ?? ''" type="date" @input="task.actual_prerequisite_date = ($event.target as HTMLInputElement).value || null" /></label>
        <label>前置工序实际就绪凭据 <input v-model="task.actual_prerequisite_reference" maxlength="500" :required="!!task.actual_prerequisite_date" /></label>
        <p>原计划涉及贴合／捆条等前置工序时，须补齐实际就绪凭据。核定日变化后请调整下方日计划，发布后保留原基准及历史。</p>
      </template>
      <h4>每日计划供数（完整套数）</h4>
      <CuttingDailyPlanTools :task="task" :calendar="calendarFor(task)" :sources="tasks" />
      <div v-for="(day, i) in task.days" :key="i" class="plan-tools"><label>生产日期 <input v-model="day.day" type="date" required /></label><label>计划套数 <input v-model.number="day.sets" type="number" min="1" max="1000000000" step="1" required /></label><Button variant="outline" type="button" @click="task.days.splice(i, 1)">移除此日</Button></div>
      <div class="plan-tools"><Button variant="outline" type="button" @click="task.days.push({ day: '', sets: 1 })">增加日计划</Button><Button variant="outline" type="button" @click="remove(index)">移除任务</Button></div>
      <p>只有当前裁剪必需料参与最早供数推算，其他辅料仍在采购交期区跟进。日历、工作日及数量由服务端核对；保存后查看计算完成期。未排足显示“计划未排完”。</p>
    </article>
  </section>
</template>
<style scoped>
.plan-task { border: 1px solid var(--border); padding: 16px; border-radius: var(--radius); margin-top: 16px; display: grid; gap: 16px; min-width: 0; }
.plan-tools { display: flex; align-items: end; flex-wrap: wrap; gap: 12px; margin: 12px 0; }
</style>
