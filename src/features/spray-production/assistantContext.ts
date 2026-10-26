import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { registerAssistantSelection } from '@/features/assistant/selection'
import type { ContextSelection } from '@/features/assistant/v2'
import type { SprayWorkspace } from './workspace'
import { isSprayFactory } from './contracts'

export function spraySourceId(raw: unknown): string | null {
  return typeof raw === 'string' && raw.length > 0 && raw.length <= 64 && raw === raw.trim() ? raw : null
}

export function spraySelection(w: SprayWorkspace, sourceError = ''): ContextSelection {
  const retained = w.assistantRecord.value
  const opened = w.taskPassportId.value || w.passportId.value
  const factory = w.factory.value, selected = opened || retained?.id
  const view = w.taskPassportId.value ? 'tasks' : w.passportId.value ? 'demands' : retained ? retained.kind === 'task' ? 'tasks' : 'demands' : w.assistantView.value
  const verified = opened ? view === 'tasks' ? w.verifiedTaskId.value : w.verifiedDemandId.value : retained?.id
  const scope = view ? w.readScopes[view] : null
  let issue = sourceError || (!isSprayFactory(factory) || !w.ready.value || !w.can('read') ? '喷油工作区与当前工厂授权尚未就绪。'
    : selected ? selected !== verified ? '来源正在读取或已失效，请成功读取后再带入。' : ''
      : !view || !scope?.ready || scope.demandId !== w.relatedDemand.value ? '请先成功读取喷油需求池或当前任务清单，再带入范围。' : '')
  const filters: ContextSelection['filters'] = { factory_id: factory ?? '', view: view ?? '' }
  const resources: ContextSelection['resources'] = []
  if (!issue && selected) resources.push({module_id:'spray-production', resource_type:view === 'tasks' ? 'task' : 'demand', resource_id:selected})
  else if (!issue && scope && view) {
    if (view === 'demands' && scope.demandId) {
      if (w.items('demands').some(row => row.id === scope.demandId)) resources.push({module_id:'spray-production',resource_type:'demand',resource_id:scope.demandId})
      else issue = '关联需求未成功读到，请先核对原记录。'
    } else {
      const mapping = {search:'q', status:'status', from_date:'date_from', to_date:'date_to', task_scope:'task_scope'}
      for (const [key, target] of Object.entries(mapping)) {
        const value = scope.params[key]
        if (typeof value === 'string' && value) filters[target] = value
      }
      if (scope.demandId) filters.demand_id = scope.demandId
    }
  }
  if (issue) filters.scope_error = issue
  else filters.scope_note = view === 'tasks'
    ? '读取已保存的完整工序任务范围；合并任务包括所有分配，报工量不是成品量，草稿不计入。'
    : '读取已保存需求及其关联库存；按原单位区分合格在库、待处置与交接，当前填写不计入。'
  return { selection_id: selected ? `spray-${view}-record` : `spray-${view ?? 'unavailable'}-list`, resources:issue ? [] : resources, filters }
}

export function useSprayAssistantContext(w: SprayWorkspace) {
  const route = useRoute(), router = useRouter(), sourceError = ref('')
  let priorTask: string | null = null, priorDemand: string | null = null
  watch([() => route.query.spray_task, () => route.query.task, () => route.query.spray_demand, w.ready, w.contextVersion], ([taskRaw, legacyRaw, demandRaw, ready]) => {
    const task = spraySourceId(taskRaw ?? legacyRaw), demand = spraySourceId(demandRaw)
    const oldTask = priorTask, oldDemand = priorDemand
    priorTask = task; priorDemand = demand
    sourceError.value = (taskRaw != null && legacyRaw != null && taskRaw !== legacyRaw)
      || ((taskRaw != null || legacyRaw != null) && !task) || (demandRaw != null && !demand) || (task && demand)
      ? '喷油来源编号无效或存在多个来源，请关闭来源后重新选择。' : ''
    if (!ready) return
    if (sourceError.value) { w.assistantRecord.value=null; w.taskPassportId.value=null; w.passportId.value=null; return }
    if (task) { w.passportId.value=null; w.taskPassportId.value=task }
    else if (demand) { w.taskPassportId.value=null; w.passportId.value=demand }
    else {
      if (w.taskPassportId.value === oldTask) w.taskPassportId.value=null
      if (w.passportId.value === oldDemand) w.passportId.value=null
    }
  }, { immediate:true })
  watch(w.taskPassportId, id => {
    if (id) w.passportId.value=null
    if (w.ready.value && priorTask && id !== priorTask) void removeSource('task', priorTask)
  }, {flush:'sync'})
  watch(w.passportId, id => {
    if (id) w.taskPassportId.value=null
    if (w.ready.value && priorDemand && id !== priorDemand) void removeSource('demand', priorDemand)
  }, {flush:'sync'})
  async function removeSource(kind?: 'task'|'demand', expected?: string) {
    if (expected && expected !== spraySourceId(kind === 'task' ? route.query.spray_task ?? route.query.task : route.query.spray_demand)) return
    const query = {...route.query}
    if (kind !== 'demand') { delete query.spray_task; delete query.task }
    if (kind !== 'task') delete query.spray_demand
    await router.replace({query})
  }
  onBeforeUnmount(registerAssistantSelection('spray-production', () => spraySelection(w, sourceError.value)))
  return { sourceError, removeSource }
}
