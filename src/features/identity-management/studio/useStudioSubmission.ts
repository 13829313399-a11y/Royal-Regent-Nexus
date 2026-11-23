import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import {
  accessStudioApi,
  type StudioDraft,
  type StudioCommand,
  type StudioPreview,
  type StudioResult,
} from '@/api/accessStudio'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { useAuthStore } from '@/stores/auth'
import type { ChangePayload } from '@/api/identity'

export function useStudioSubmission(
  target: () => string,
  draft: () => StudioDraft | ChangePayload | null,
  saved: (value: StudioResult) => void,
) {
  const auth = useAuthStore()
  const account = computed(() =>
    [auth.currentUser?.id, auth.currentUser?.identity?.employment_epoch].join(':'),
  )
  const viewer = computed(() =>
    [account.value, auth.authorizationVersion, auth.currentUser?.identity?.effective_context_key].join(':'),
  )
  const preview = shallowRef<StudioPreview>()
  const state = ref<'idle' | 'previewing' | 'ready' | 'saving' | 'uncertain' | 'conflict'>('idle')
  const error = ref(''),
    acknowledge = ref(false),
    empty = ref(false)
  const locked = computed(() => state.value === 'saving' || state.value === 'uncertain')
  const ready = computed(
    () =>
      state.value === 'ready' &&
      preview.value?.allowed_to_commit &&
      (!preview.value.high_risk || acknowledge.value) &&
      (!preview.value.requires_empty_confirmation || empty.value),
  )
  let generation = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let expiry: ReturnType<typeof setTimeout> | undefined
  let command: { owner: string; id: string; key: string; body: StudioCommand } | undefined
  function invalidate() {
    ++generation
    clearTimeout(timer)
    clearTimeout(expiry)
    preview.value = undefined
    acknowledge.value = false
    empty.value = false
    if (!locked.value) state.value = 'idle'
  }
  function fail(e: unknown) {
    const status = (e as { response?: { status?: number } }).response?.status
    invalidate()
    state.value = status === 409 ? 'conflict' : 'idle'
    error.value = getApiErrorMessage(e)
  }
  async function check() {
    const value = draft()
    if (locked.value || !value || state.value === 'conflict') return
    invalidate()
    const current = generation
    state.value = 'previewing'
    error.value = ''
    try {
      const result = await accessStudioApi.preview(target(), value)
      if (current !== generation) return
      preview.value = result
      state.value = 'ready'
      expiry = setTimeout(
        () => {
          if (locked.value) return
          invalidate()
          error.value = '预览已过期，请重新核对。'
        },
        Math.max(0, Date.parse(result.expires_at) - Date.parse(result.server_now)),
      )
    } catch (e) {
      if (current === generation) fail(e)
    }
  }
  watch(
    () => JSON.stringify(draft()),
    () => {
      if (locked.value || state.value === 'conflict') return
      invalidate()
      error.value = ''
      if (draft()) timer = setTimeout(check, 350)
    },
    { flush: 'sync' },
  )
  function finish(result: StudioResult) {
    command = undefined
    state.value = 'idle'
    invalidate()
    error.value = ''
    saved(result)
  }
  async function retry() {
    const pending = command,
      current = generation
    if (!pending || pending.owner !== account.value || state.value === 'saving') return
    state.value = 'saving'
    error.value = ''
    try {
      const result = await accessStudioApi.commit(pending.id, pending.body, pending.key)
      if (current === generation && pending === command) finish(result)
    } catch (e) {
      if (current !== generation || pending !== command) return
      const response = (e as { response?: { status?: number; data?: { code?: string; detail?: { code?: string } } } }).response
      const status = response?.status
      const switchClosed = (response?.data?.code || response?.data?.detail?.code) === 'ACCESS_STUDIO_DISABLED'
      if (!switchClosed && (!status || status >= 500 || status === 408 || status === 429)) {
        state.value = 'uncertain'
        error.value = '提交结果待确认，请先查询回执或重试原命令。'
      } else {
        command = undefined
        state.value = 'idle'
        fail(e)
      }
    }
  }
  async function commit() {
    if (!ready.value || !preview.value || locked.value) return
    try {
      command = {
        owner: account.value,
        id: target(),
        key: createRandomUuid(),
        body: {
          preview_token: preview.value.preview_token,
          risk_acknowledged: acknowledge.value,
          confirm_empty_packages: empty.value,
        },
      }
    } catch (e) {
      error.value = getApiErrorMessage(e)
      return
    }
    await retry()
  }
  async function receipt() {
    const pending = command,
      current = generation
    if (!pending || state.value !== 'uncertain' || pending.owner !== account.value) return
    state.value = 'saving'
    try {
      const response = await accessStudioApi.receipt(pending.key)
      if (current !== generation || pending !== command) return
      if (response.status === 'committed' && response.result) finish(response.result)
      else {
        state.value = 'uncertain'
        error.value = '尚未观察到回执，可用原命令重试。'
      }
    } catch (e) {
      if (current === generation && pending === command) {
        state.value = 'uncertain'
        error.value = getApiErrorMessage(e)
      }
    }
  }
  watch(
    [viewer, target],
    () => {
      const unresolved = !!command && command.owner === account.value && command.id === target()
      if (!unresolved) command = undefined
      state.value = unresolved ? 'uncertain' : 'idle'
      invalidate()
      error.value = unresolved ? '授权范围已变化，请核查原提交回执。' : ''
    },
    { flush: 'sync' },
  )
  onBeforeUnmount(invalidate)
  return { preview, state, ready, locked, error, acknowledge, empty, check, commit, retry, receipt }
}
