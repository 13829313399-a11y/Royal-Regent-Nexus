import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import type { EnterpriseModule } from '@/data/enterpriseMock'

export function canPreviewModule(module: EnterpriseModule) { return Boolean(module.route || module.href) }
export function useHomePresentation(modules: Ref<EnterpriseModule[]>, scope: Ref<string>) {
  const input = ref('')
  const query = ref('')
  const composing = ref(false)
  const previewId = ref<string | null>(null)
  const pinnedId = ref<string | null>(null)
  const dialogOpen = ref(false)
  const filteredModules = computed(() => {
    const needle = query.value.trim().toLocaleLowerCase()
    return modules.value.filter(module => !needle || [module.title, module.summary, ...module.children.map(child => child.label)]
      .some(text => text.toLocaleLowerCase().includes(needle)))
  })
  const featuredModule = computed(() => filteredModules.value.find(module => module.id === (pinnedId.value ?? previewId.value)) ?? filteredModules.value[0] ?? null)
  let timer: ReturnType<typeof setTimeout> | undefined
  let generation = 0
  function cancelPreview() { clearTimeout(timer); timer = undefined; generation++ }
  function clearSearch() { input.value = ''; query.value = ''; composing.value = false }
  function commitSearch(value: string) { input.value = value; if (!composing.value) query.value = value }
  function reset() {
    cancelPreview(); clearSearch(); previewId.value = null; pinnedId.value = null; dialogOpen.value = false
  }
  watch(scope, reset, { flush: 'sync' })
  // Only IDs and current mapped targets are retained. Revocation never leaves a cached module object.
  watch(() => filteredModules.value.map(module => `${module.id}:${module.route ?? ''}:${module.href ?? ''}`).join('|'), () => {
    cancelPreview()
    const available = (id: string | null) => filteredModules.value.some(module => module.id === id && canPreviewModule(module))
    if (pinnedId.value && !available(pinnedId.value)) { pinnedId.value = null; dialogOpen.value = false }
    if (previewId.value && !available(previewId.value)) { previewId.value = null; dialogOpen.value = false }
    if (!filteredModules.value.length) dialogOpen.value = false
  }, { flush: 'sync' })
  function preview(id: string, immediate = false) {
    cancelPreview()
    if (pinnedId.value || !filteredModules.value.some(module => module.id === id && canPreviewModule(module))) return
    const request = generation
    const apply = () => {
      if (request === generation && !pinnedId.value && filteredModules.value.some(module => module.id === id && canPreviewModule(module))) previewId.value = id
    }
    if (immediate) apply()
    else timer = setTimeout(apply, 140)
  }
  function pin(id: string) {
    cancelPreview()
    if (!filteredModules.value.some(module => module.id === id && canPreviewModule(module))) return false
    previewId.value = id; pinnedId.value = id
    return true
  }
  function unpin() { cancelPreview(); pinnedId.value = null }
  onBeforeUnmount(cancelPreview)
  return { input, query, composing, filteredModules, featuredModule, pinnedId, dialogOpen, clearSearch, commitSearch, reset, preview, pin, unpin, cancelPreview }
}
