import { defineComponent, reactive } from 'vue'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { usePositionReview } from '../usePositionReview'
import type { WorkItemDetail, ReviewPreview, ReviewResult } from '@/api/positionReviews'
const api = vi.hoisted(() => ({ detail: vi.fn(), packages: vi.fn(), preview: vi.fn(), commit: vi.fn(), decide: vi.fn(), receipt: vi.fn() }))
vi.mock('@/api/positionReviews', () => ({ positionReviewsApi: api }))
const auth = reactive({ currentUser: { id: 'admin', identity: { employment_epoch: 1, effective_context_key: 'scope-A' } }, authorizationVersion: 1 })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
enableAutoUnmount(afterEach)
afterEach(() => vi.useRealTimers())
const detail = (id = 'p'): WorkItemDetail => ({ item_key: `position:${id}`, kind: 'position', origin: 'employee',
  user: { id, display_name: id, username: id }, source_revision: 'position:1', status: 'pending', before: null,
  declaration: { org_unit_id: 'f', department_code: 'd', position: '主管', note: '' }, created_at: '', updated_at: '',
  available_actions: ['preview', 'commit', 'return_position'], current_official: { org_unit_id: 'f', department_code: 'd', position: '工程师' },
  identity_mode: 'v2', identity_version: 1, authorization_version: 1, primary_assignment_id: 'a', current_bindings: [],
  independent_allows: [], explicit_denials: [], registration_details: null, can_keep_permissions: true, blocked_reasons: [] })
const preview = (token = 'first'): ReviewPreview => ({ preview_token: token, expires_at: '2026-10-13T01:05:00Z', server_now: '2026-10-13T01:00:00Z',
  source_revision: 'position:1', preview_fingerprint: token, decision: 'keep_permissions', permission_diffs: { added: [], removed: [], retained: [], source_changed: [] },
  retained_sources: [], explicit_denials: [], high_risk: false, requires_independent_approval: false, allowed_to_commit: true, blocked_reasons: [], handover_summary: '' })
const result: ReviewResult = { command_id: 'receipt', status: 'committed', item_key: 'position:p', decision: 'keep_permissions', source_status: 'applied',
  source_revision: 'position:2', target_identity_version: 2, target_authorization_version: 2, notification_state: 'queued', committed_at: '', message: '完成' }
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r }); return { promise, resolve } }
let review: ReturnType<typeof usePositionReview>
const saved = vi.fn()
function view() { mount(defineComponent({ setup() { review = usePositionReview(saved); return () => null } })) }
beforeEach(() => {
  vi.resetAllMocks(); vi.useFakeTimers()
  auth.currentUser.id = 'admin'; auth.authorizationVersion = 1; auth.currentUser.identity.effective_context_key = 'scope-A'
  api.detail.mockImplementation(async (key: string) => detail(key.split(':')[1]))
  api.packages.mockResolvedValue({ items: [], catalog_revision: 'fixed' })
  api.preview.mockResolvedValue(preview()); api.commit.mockResolvedValue(result)
  view()
})
async function ready() { await review.select('position:p'); await flushPromises(); await vi.advanceTimersByTimeAsync(301); await flushPromises() }
it('automatically previews after debounce and synchronously invalidates risk on any draft edit', async () => {
  await ready(); expect(review.canCommit.value).toBe(true)
  review.risk.value = true; review.draft.value!.confirmed_profile.position = '经理'
  expect(review.preview.value).toBeUndefined(); expect(review.risk.value).toBe(false); expect(review.canCommit.value).toBe(false)
  await vi.advanceTimersByTimeAsync(299); expect(api.preview).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(2); expect(api.preview).toHaveBeenCalledTimes(2)
})
it('drops late previews and late detail responses after the selected person changes', async () => {
  const slow = deferred<ReviewPreview>(); api.preview.mockReturnValueOnce(slow.promise)
  await ready(); expect(review.state.value).toBe('previewing')
  await review.select('position:other'); await flushPromises(); await vi.advanceTimersByTimeAsync(301)
  slow.resolve(preview('stale')); await flushPromises()
  expect(review.detail.value?.user.id).toBe('other'); expect(review.preview.value?.preview_token).toBe('first')
  const oldDetail = deferred<WorkItemDetail>(); api.detail.mockReturnValueOnce(oldDetail.promise)
  const old = review.select('position:old'); await review.select('position:latest')
  oldDetail.resolve(detail('old')); await old
  expect(review.detail.value?.user.id).toBe('latest')
})
it('requires an explicit high risk acknowledgement and expires it with the preview', async () => {
  api.preview.mockResolvedValue({ ...preview(), high_risk: true }); await ready()
  expect(review.canCommit.value).toBe(false); review.risk.value = true; expect(review.canCommit.value).toBe(true)
  await vi.advanceTimersByTimeAsync(300001)
  expect(review.canCommit.value).toBe(false); expect(review.risk.value).toBe(false)
})
it('keeps the immutable command and forbids changing people after an unknown outcome', async () => {
  await ready(); api.commit.mockRejectedValueOnce(new Error('connection reset'))
  await review.submit(); const sent = structuredClone(api.commit.mock.calls[0])
  expect(review.state.value).toBe('uncertain'); expect(review.locked.value).toBe(true)
  await review.select('position:other'); expect(review.detail.value?.user.id).toBe('p')
  api.receipt.mockResolvedValue({ status: 'not_observed', result: null }); await review.checkReceipt()
  expect(review.state.value).toBe('uncertain'); await review.retry()
  expect(api.commit.mock.calls[1]).toEqual(sent); expect(saved).toHaveBeenCalledOnce()
})
it('recovers a committed receipt without issuing another command', async () => {
  await ready(); api.commit.mockRejectedValueOnce({ response: { status: 503 } }); await review.submit()
  api.receipt.mockResolvedValue({ status: 'committed', result }); await review.checkReceipt()
  expect(review.state.value).toBe('success'); expect(api.commit).toHaveBeenCalledOnce(); expect(saved).toHaveBeenCalledWith(result)
})
it('clears protected detail on 403 and keeps corrections on a 409', async () => {
  await ready(); api.preview.mockRejectedValueOnce({ response: { status: 409, data: { message: '版本变化' } } })
  review.draft.value!.confirmed_profile.position = '人工更正'; await vi.advanceTimersByTimeAsync(301)
  expect(review.state.value).toBe('conflict'); expect(review.draft.value?.confirmed_profile.position).toBe('人工更正')
  api.preview.mockRejectedValueOnce({ response: { status: 403, data: { message: '范围撤销' } } }); await review.makePreview()
  expect(review.detail.value).toBeUndefined(); expect(review.packages.value).toEqual([]); expect(review.canCommit.value).toBe(false)
})
it('discards responses from the previous authenticated viewer', async () => {
  const slow = deferred<WorkItemDetail>(); api.detail.mockReturnValueOnce(slow.promise)
  const pending = review.select('position:p'); auth.currentUser.id = 'other'; await flushPromises()
  slow.resolve(detail()); await pending
  expect(review.detail.value).toBeUndefined(); expect(review.preview.value).toBeUndefined()
})

it('clears protected detail and discards late responses at a scheduled context boundary', async () => {
  await ready()
  const old = deferred<WorkItemDetail>(); api.detail.mockReturnValueOnce(old.promise)
  const pending = review.select('position:old-scope')
  auth.currentUser.identity.effective_context_key = 'scope-B'
  await flushPromises()
  expect(review.detail.value).toBeUndefined(); expect(review.preview.value).toBeUndefined()
  old.resolve(detail('old-scope')); await pending
  expect(review.detail.value).toBeUndefined(); expect(review.packages.value).toEqual([])
})

it('keeps the original uncertain command across same-actor scope expiry while clearing private data', async () => {
  await ready(); api.commit.mockRejectedValue(new Error('lost connection'))
  await review.submit(); const command = api.commit.mock.calls[0]?.[1]
  auth.currentUser.identity.effective_context_key = 'scope-B'
  await flushPromises()
  expect(review.detail.value).toBeUndefined(); expect(review.locked.value).toBe(true)
  await review.retry()
  expect(api.commit.mock.calls[1]?.[1]).toEqual(command)
})
