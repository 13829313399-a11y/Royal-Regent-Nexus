import { onBeforeUnmount, watch } from 'vue'
import { useSprayWorkspace } from './workspace'

export function useSprayPage(collections: string[], defaults: Record<string, Record<string, unknown>> = {}) {
  const workspace = useSprayWorkspace()
  workspace.activeCollections.value = collections
  collections.forEach(key => workspace.configureCollection(key, defaults[key]))
  watch([workspace.ready, workspace.relatedDemand], ([ready]) => { if (ready) void workspace.load(collections) }, { immediate: true })
  onBeforeUnmount(() => { workspace.saveDraft.value = null })
  return workspace
}
