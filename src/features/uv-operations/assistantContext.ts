import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { registerAssistantSelection } from '@/features/assistant/selection'
import type { ContextSelection } from '@/features/assistant/v2'
import type { UvWorkspace } from './workspace'
import { UV_FACTORY } from './contracts'

export function uvTaskId(raw: unknown): string | null {
  return typeof raw === 'string' && raw.length > 0 && raw.length <= 64 && raw === raw.trim() ? raw : null
}
export function uvSelection(factory: unknown, ready: boolean, selected: string | null, verified: string | null,
  listReady: boolean, error = ''): ContextSelection {
  const issue = error || (factory !== UV_FACTORY ? '请明确选择华康A。' : !ready ? 'UV工作区尚未就绪。'
    : selected ? selected !== verified ? '任务档案正在读取或已失效，请成功读取后再带入。' : ''
      : !listReady ? '当前仅支持任务清单或已读取的任务档案，请先打开对应范围。' : '')
  return { selection_id: selected ? 'uv-selected-task' : 'uv-task-list',
    resources: !issue && selected ? [{ module_id: 'uv-operations', resource_type: 'task', resource_id: selected }] : [],
    filters: { factory_id: typeof factory === 'string' ? factory : '',
      ...(issue ? { scope_error: issue } : { view: 'tasks', scope_note: '读取已保存的原任务和实体批次；当前排程预览或核数草稿不计入。' }) } }
}

export function useUvAssistantContext(w: UvWorkspace) {
  const route = useRoute(), router = useRouter(), sourceError = ref('')
  let priorSource: string | null = null
  watch([() => route.query.uv_task, w.ready, w.contextVersion], ([raw, ready]) => {
    const previous = priorSource
    priorSource = uvTaskId(raw)
    sourceError.value = raw != null && !priorSource ? '任务来源编号无效，请关闭此来源后重新选择。' : ''
    if (!ready) return
    if (priorSource) w.selectedTaskId.value = priorSource
    else if (sourceError.value || w.selectedTaskId.value === previous) w.selectedTaskId.value = null
  }, { immediate: true })
  watch(w.selectedTaskId, id => {
    // Closing a source or choosing a different native row removes the old URL.
    // Same-page query updates keep the existing planning/shift component alive.
    if (w.ready.value && priorSource && route.query.uv_task === priorSource && id !== priorSource) void removeSource()
  })
  async function removeSource() {
    const query = { ...route.query }
    delete query.uv_task
    await router.replace({ query })
  }
  onBeforeUnmount(registerAssistantSelection('uv-operations', () => uvSelection(route.query.factory, w.ready.value,
    w.selectedTaskId.value, w.verifiedTaskId.value, w.assistantListReady.value, sourceError.value)))
  return { sourceError, removeSource }
}
