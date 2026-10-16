import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { positionReviewsApi as api, type BuiltinPackage, type CommitCommand, type DecisionCommand, type FactoryScope,
  type ReviewDraft, type ReviewPreview, type ReviewResult, type WorkItemDetail } from '@/api/positionReviews'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { useAuthStore } from '@/stores/auth'

export function usePositionReview(onSaved: (result: ReviewResult) => void) {
  const auth = useAuthStore()
  const detail = ref<WorkItemDetail>()
  const packages = ref<BuiltinPackage[]>([])
  const draft = ref<ReviewDraft>()
  const originalDraft = ref('')
  const dirty = computed(() => !!originalDraft.value && !result.value && !!draft.value && JSON.stringify(draft.value) !== originalDraft.value)
  const scope = ref<FactoryScope>({ kind: 'home', factory_ids: [] })
  const selectedRole = ref('')
  const preview = ref<ReviewPreview>()
  const state = ref<'idle' | 'loading' | 'editing' | 'previewing' | 'ready' | 'committing' | 'uncertain' | 'conflict' | 'success' | 'forbidden'>('idle')
  const error = ref(''), result = ref<ReviewResult>(), risk = ref(false), packagesLoading = ref(false)
  let generation = 0, previewGeneration = 0, packageGeneration = 0, disposed = false
  let previewTimer: ReturnType<typeof setTimeout> | undefined, expiryTimer: ReturnType<typeof setTimeout> | undefined
  let pending: { key: string; kind: 'commit'; body: CommitCommand } | { key: string; kind: 'decision'; body: DecisionCommand } | undefined
  const account = computed(() => `${auth.currentUser?.id ?? ''}:${auth.currentUser?.identity?.employment_epoch ?? ''}`)
  let pendingOwner = ''
  const identity = computed(() => `${auth.currentUser?.id ?? ''}:${auth.currentUser?.identity?.employment_epoch ?? ''}:${auth.authorizationVersion}:${auth.currentUser?.identity?.effective_context_key ?? ''}`)
  const locked = computed(() => state.value === 'committing' || state.value === 'uncertain')
  const valid = computed(() => {
    const d = draft.value, source = detail.value
    return Boolean(d && source?.available_actions.includes('preview') && source.identity_mode !== 'legacy'
      && d.confirmed_profile.position.trim() && d.confirmed_profile.position.trim().length <= 128
      && d.independent_allow_decisions.length === source.independent_allows.length
      && (d.decision === 'keep_permissions' || d.package_selection) && !packagesLoading.value)
  })
  const canCommit = computed(() => state.value === 'ready' && preview.value?.allowed_to_commit && (!preview.value.high_risk || risk.value))
  function invalidate() {
    ++previewGeneration
    clearTimeout(previewTimer); clearTimeout(expiryTimer)
    preview.value = undefined; risk.value = false
    if (!locked.value && state.value !== 'loading' && state.value !== 'success' && state.value !== 'forbidden') state.value = 'editing'
  }
  function fail(e: unknown) {
    const status = (e as { response?: { status?: number } }).response?.status
    error.value = getApiErrorMessage(e)
    invalidate()
    if (status === 401 || status === 403) { detail.value = undefined; draft.value = undefined; packages.value = []; state.value = 'forbidden' }
    else if (status === 409) state.value = 'conflict'
    else state.value = 'editing'
  }
  async function select(key: string) {
    if (locked.value) return
    const current = ++generation, viewer = identity.value
    ++packageGeneration; invalidate()
    detail.value = undefined; draft.value = undefined; packages.value = []; selectedRole.value = ''
    originalDraft.value = ''; result.value = undefined; error.value = ''; pending = undefined; state.value = 'loading'
    try {
      const data = await api.detail(key)
      if (disposed || current !== generation || viewer !== identity.value) return
      detail.value = data
      scope.value = { kind: 'home', factory_ids: [] }
      draft.value = { expected_source_revision: data.source_revision, decision: data.can_keep_permissions ? 'keep_permissions' : 'apply_package',
        confirmed_profile: { org_unit_id: data.declaration.org_unit_id, department_code: data.declaration.department_code, position: data.declaration.position },
        independent_allow_decisions: [], registration_details_correction: data.registration_details ? { ...data.registration_details } : null }
      state.value = 'editing'
      await loadPackages()
      if (disposed || current !== generation || viewer !== identity.value) return
      originalDraft.value = JSON.stringify(draft.value)
      schedulePreview()
    } catch (e) { if (current === generation && viewer === identity.value) fail(e) }
  }
  async function loadPackages() {
    const data = detail.value, d = draft.value
    if (!data || !d) return
    const current = ++packageGeneration, currentSource = generation, viewer = identity.value
    packagesLoading.value = true; invalidate()
    try {
      const response = await api.packages({ item_key: data.item_key, org_unit_id: d.confirmed_profile.org_unit_id,
        department_code: d.confirmed_profile.department_code, scope_kind: scope.value.kind, factory_ids: scope.value.factory_ids })
      if (disposed || current !== packageGeneration || currentSource !== generation || viewer !== identity.value) return
      packages.value = response.items
      syncSelection()
    } catch (e) { if (current === packageGeneration && currentSource === generation && viewer === identity.value) fail(e) }
    finally { if (current === packageGeneration) { packagesLoading.value = false; schedulePreview() } }
  }
  function syncSelection() {
    if (!draft.value) return
    const choice = packages.value.find(p => p.role_id === selectedRole.value && p.assignable)
    draft.value.package_selection = draft.value.decision === 'apply_package' && choice ? {
      role_id: choice.role_id, definition_hash: choice.definition_hash, role_version_id: choice.role_version_id,
      permission_department: choice.department, factory_scope: { ...scope.value, factory_ids: [...scope.value.factory_ids] },
    } : null
  }
  function schedulePreview() {
    if (locked.value || state.value === 'success') return
    invalidate()
    if (valid.value) previewTimer = setTimeout(() => { void makePreview() }, 300)
  }
  async function makePreview() {
    if (!valid.value || !detail.value || !draft.value || locked.value) return
    const current = ++previewGeneration, source = generation, viewer = identity.value
    state.value = 'previewing'; error.value = ''
    try {
      const value = await api.preview(detail.value.item_key, JSON.parse(JSON.stringify(draft.value)) as ReviewDraft)
      if (disposed || current !== previewGeneration || source !== generation || viewer !== identity.value) return
      preview.value = value; state.value = 'ready'
      const ttl = Date.parse(value.expires_at) - Date.parse(value.server_now)
      expiryTimer = setTimeout(() => { invalidate(); error.value = '预览已过期，请重新核对'; }, Math.max(0, ttl))
    } catch (e) { if (current === previewGeneration && source === generation && viewer === identity.value) fail(e) }
  }
  async function execute() {
    if (!pending || state.value === 'committing') return
    const command = pending, viewer = identity.value, source = generation
    state.value = 'committing'; error.value = ''
    try {
      const value = command.kind === 'commit' ? await api.commit(command.key, command.body) : await api.decide(command.key, command.body)
      if (disposed || viewer !== identity.value || source !== generation) return
      completed(value)
    } catch (e) {
      if (disposed || viewer !== identity.value || source !== generation) return
      const status = (e as { response?: { status?: number } }).response?.status
      if (!status || status >= 500 || status === 408) { state.value = 'uncertain'; error.value = '正在核查提交结果。请保留此页，使用原命令查询或重试。' }
      else { pending = undefined; state.value = 'editing'; fail(e) }
    }
  }
  function completed(value: ReviewResult) {
    clearTimeout(previewTimer); clearTimeout(expiryTimer)
    result.value = value; state.value = 'success'; pending = undefined; preview.value = undefined
    window.dispatchEvent(new Event('iam-identity-changed'))
    onSaved(value)
  }
  async function submit() {
    if (!canCommit.value || !detail.value || !preview.value || locked.value) return
    pendingOwner = account.value
    pending = { key: detail.value.item_key, kind: 'commit', body: { expected_source_revision: preview.value.source_revision,
      preview_token: preview.value.preview_token, command_id: createRandomUuid(), risk_acknowledged: risk.value } }
    await execute()
  }
  async function decide(reason: string) {
    if (!detail.value || locked.value || !reason.trim()) return
    pendingOwner = account.value
    pending = { key: detail.value.item_key, kind: 'decision', body: { expected_source_revision: detail.value.source_revision,
      command_id: createRandomUuid(), action: detail.value.kind === 'registration' ? 'reject_registration' : 'return_position', reason: reason.trim() } }
    await execute()
  }
  async function checkReceipt() {
    if (!pending || state.value !== 'uncertain') return
    const command = pending, viewer = identity.value
    try {
      const receipt = await api.receipt(command.body.command_id)
      if (disposed || pending !== command || viewer !== identity.value) return
      if (receipt.result) completed(receipt.result)
      else error.value = '暂未观察到提交结果，不代表失败。可用原命令重试。'
    } catch (e) { if (pending === command && viewer === identity.value) error.value = getApiErrorMessage(e) }
  }
  watch(() => JSON.stringify(draft.value), schedulePreview, { flush: 'sync' })
  watch(() => [draft.value?.confirmed_profile.org_unit_id, draft.value?.confirmed_profile.department_code, JSON.stringify(scope.value)], () => { void loadPackages() })
  watch(() => [selectedRole.value, draft.value?.decision], syncSelection, { flush: 'sync' })
  watch(identity, () => {
    ++generation; ++packageGeneration
    // Scope changes clear personnel data, but the same actor must still resolve
    // its original uncertain command instead of silently creating another one.
    const unresolved = !!pending && locked.value && pendingOwner === account.value
    if (!unresolved) pending = undefined
    state.value = unresolved ? 'uncertain' : 'idle'
    invalidate(); detail.value = undefined; draft.value = undefined; packages.value = []; result.value = undefined
    if (unresolved) error.value = '授权范围已变化，人员资料已清除。请先核查原提交结果。'
  }, { flush: 'sync' })
  onBeforeUnmount(() => { disposed = true; ++generation; ++previewGeneration; ++packageGeneration; clearTimeout(previewTimer); clearTimeout(expiryTimer) })
  return { detail, packages, draft, scope, selectedRole, preview, state, error, result, risk, locked, dirty, valid, canCommit,
    packagesLoading, select, makePreview, submit, decide, checkReceipt, retry: execute, invalidate }
}
