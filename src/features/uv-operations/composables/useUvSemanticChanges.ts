import { reactive, watch, type Ref } from 'vue'
import type { Entity } from '../contracts'
import { useUvMotion } from './useUvMotionPreference'

export function useUvSemanticChanges(rows: Readonly<Ref<Entity[]>>) {
  const motion = useUvMotion(), changed = reactive(new Set<string>())
  let previous = new Map<string, string>()
  watch(() => rows.value.map(row => [row.id, JSON.stringify([row.collection_health, row.work_state, row.current_run_id])] as const), values => {
    const next = new Map(values)
    for (const [id, fingerprint] of next) if (motion.allowed.value && previous.has(id) && previous.get(id) !== fingerprint) changed.add(id)
    for (const id of changed) if (!next.has(id)) changed.delete(id)
    previous = next
  }, { immediate: true })
  watch(motion.allowed, allowed => { if (!allowed) changed.clear() }, { flush: 'sync' })
  return changed
}
