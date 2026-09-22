import { onBeforeUnmount, watch } from 'vue'
import { useSprayWorkspace } from './workspace'

export function useSprayPage(collections: string[]) {
  const workspace = useSprayWorkspace()
  workspace.activeCollections.value = collections
  watch([workspace.ready, workspace.relatedDemand], ([ready]) => { if (ready) void workspace.load(collections) }, { immediate: true })
  onBeforeUnmount(() => { workspace.saveDraft.value = null })
  return workspace
}
