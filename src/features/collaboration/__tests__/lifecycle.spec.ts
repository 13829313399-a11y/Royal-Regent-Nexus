import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useDirectoryQuery } from '@/composables/useDirectoryQuery'
import { useMessagingStore } from '@/stores/messaging'
import ChatPanel from '../ChatPanel.vue'
const mocks = vi.hoisted(() => ({ members: vi.fn(), get: vi.fn(), patch: vi.fn(), post: vi.fn() }))
vi.mock('@/api/directory', () => ({ directoryApi: { getMembers: mocks.members } }))
vi.mock('@/api/collaboration', () => ({ collaborationApi: { get: mocks.get, patch: mocks.patch, post: mocks.post } }))
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => resolve = r); return { promise, resolve } }
function seed(id = 'alice') { useAuthStore().applySession({ id, username: id, display_name: id, roles: [], permissions: [], grants: [], factory_scopes: [], department_scopes: [], force_password_change: false }) }
const response = (id: string) => ({ items: [{ id, display_name: id }], total: 1, total_pages: 1, state_counts: { online: 0, away: 0, offline: 1 } })
describe('collaboration request ownership', () => {
  beforeEach(() => { setActivePinia(createPinia()); seed(); vi.useFakeTimers(); vi.resetAllMocks() })
  afterEach(() => { vi.clearAllTimers(); vi.useRealTimers() })
  it('ignores a slow filter response and cancels/reloads when closing and reopening', async () => {
    const old = deferred<ReturnType<typeof response>>(), fresh = deferred<ReturnType<typeof response>>()
    mocks.members.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise).mockResolvedValue(response('reopened'))
    const params = ref({ q: 'old' }), enabled = ref(true)
    let query!: ReturnType<typeof useDirectoryQuery>
    const wrapper = mount(defineComponent({ setup() { query = useDirectoryQuery(params, enabled); return () => null } }))
    params.value = { q: 'fresh' }; await flushPromises()
    expect(mocks.members.mock.calls[0]![1].aborted).toBe(true)
    fresh.resolve(response('fresh')); await flushPromises(); old.resolve(response('old')); await flushPromises()
    expect(query.items.value.map(x => x.id)).toEqual(['fresh'])
    enabled.value = false; await flushPromises(); expect(query.loading.value).toBe(false)
    enabled.value = true; await flushPromises(); expect(query.items.value[0]?.id).toBe('reopened')
    wrapper.unmount(); await vi.advanceTimersByTimeAsync(60_000); expect(mocks.members).toHaveBeenCalledTimes(3)
  })
  it('does not revive another viewer result after identity change or unmount', async () => {
    const old = deferred<ReturnType<typeof response>>()
    mocks.members.mockReturnValueOnce(old.promise).mockResolvedValue(response('bob'))
    let query!: ReturnType<typeof useDirectoryQuery>
    const wrapper = mount(defineComponent({ setup() { query = useDirectoryQuery({}); return () => null } }))
    seed('bob'); await flushPromises(); expect(query.items.value[0]?.id).toBe('bob')
    wrapper.unmount(); old.resolve(response('alice')); await flushPromises()
    expect(query.items.value[0]?.id).toBe('bob')
    expect(mocks.members.mock.calls.every(call => call[1].aborted)).toBe(true)
  })
  it('a completed send of A preserves B typed while the POST was pending', async () => {
    const sent = deferred<object>(), store = useMessagingStore(); store.bind('alice:1')
    store.drafts.cid = { text: 'A', reply_to_id: null, attachment_ids: [], version: 0, revision: 1, savedRevision: 0, saving: false, error: '', reference: null }
    mocks.patch.mockResolvedValue({ text: 'A', version: 1, reply_to_id: null, attachment_ids: [] })
    mocks.post.mockReturnValue(sent.promise)
    mocks.get.mockResolvedValue({ owner: {user_id:'alice',employment_epoch:1}, events: [], cursor: '', has_more: false, unread: 0 })
    const sending = store.send('cid'); await flushPromises()
    store.edit('cid', { text: 'B' })
    sent.resolve({ id:'m1',conversation_id:'cid',message_seq:1,sender_user_id:'alice',body:'A',version:1,attachments:[],reply:null,retracted_at:null })
    await sending
    expect(store.drafts.cid.text).toBe('B')
    expect(store.pending.cid).toEqual([])
    expect(store.history.cid?.[0]?.body).toBe('A')
    store.bind(''); expect(Object.keys(store.drafts)).toEqual([])
  })
  it.each([true, false])('does not restore sent text when a draft PATCH response is lost (recovered=%s)', async recovered => {
    const store = useMessagingStore(); store.bind('alice:1')
    store.drafts.cid = { text: 'A', reply_to_id: null, attachment_ids: [], version: 0, revision: 1, savedRevision: 0, saving: false, error: '', reference: null }
    mocks.patch.mockRejectedValue(new Error('lost response'))
    const cloud = { text: 'A', reply_to_id: null, attachment_ids: [], version: 1 }
    mocks.get.mockImplementation(async (path: string) => path.endsWith('/draft') ? cloud : { owner: {user_id:'alice',employment_epoch:1}, events: [], cursor: '', has_more: false, unread: 0 })
    if (!recovered) mocks.get.mockRejectedValueOnce(new Error('offline during recovery'))
    mocks.post.mockImplementation(async (_path: string, payload: { draft_version: number }) => {
      expect(payload.draft_version).toBe(recovered ? 1 : 0)
      if (recovered) { cloud.text = ''; cloud.version++ }
      return { id:'m1',conversation_id:'cid',message_seq:1,sender_user_id:'alice',body:'A',version:1,attachments:[],reply:null,retracted_at:null }
    })
    await store.send('cid')
    expect(store.drafts.cid.text).toBe('')
    expect(store.drafts.cid.error).toBe(recovered ? '' : '消息已发送，云端仍有另一份草稿，请选择采用云端或保留本机。')
    await store.send('cid')
    expect(mocks.post).toHaveBeenCalledTimes(1)
    store.bind('')
  })
  it('fills history gaps after jumping from the latest page to the first unread page', async () => {
    const store = useMessagingStore(); store.bind('alice:1')
    store.conversations.push({ id:'cid', peer:{id:'bob',display_name:'bob',available:true}, last_message_seq:200, last_read_seq:0, unread:200, revision:1,updated_at:'',mute_until:null,pin_order:0,archived_at:null,version:1,peer_read_seq:null,last_message:null })
    mocks.get.mockImplementation(async (_path: string, _signal: AbortSignal, params: { before_seq?: number; after_seq?: number }) => {
      const start = params.after_seq !== undefined ? params.after_seq + 1 : (params.before_seq ?? 201) - 50
      return { items: Array.from({length:50}, (_, i) => ({id:`m${start+i}`,conversation_id:'cid',message_seq:start+i,version:1})), has_more:start > 1 }
    })
    await store.loadMessages('cid'); await store.firstUnread('cid')
    expect(store.hasMore.cid).toBe(true)
    await store.loadMessages('cid', true); await store.loadMessages('cid', true)
    expect(store.history.cid?.map(m => m.message_seq)).toEqual(Array.from({length:200}, (_, i) => i + 1))
    expect(store.hasMore.cid).toBe(false)
    expect(mocks.get.mock.calls.slice(2).map(call => call[2].before_seq)).toEqual([151,101])
    store.bind('')
  })
  it('blocks a draft event while a successful send is reconciling its cloud draft', async () => {
    const store = useMessagingStore(); store.bind('alice:1')
    store.drafts.cid = {text:'A',reply_to_id:null,attachment_ids:[],version:0,revision:1,savedRevision:0,saving:false,error:'',reference:null}
    const cloud = {text:'A',reply_to_id:null,attachment_ids:[],version:1}, reconcile = deferred<typeof cloud>()
    const batch = {owner:{user_id:'alice',employment_epoch:1},events:[],cursor:'',has_more:false,unread:0}
    mocks.patch.mockRejectedValue(new Error('lost PATCH'))
    mocks.get.mockRejectedValueOnce(new Error('offline')).mockReturnValueOnce(reconcile.promise).mockImplementation(async (path: string) => path === '/conversations' ? {items:[{id:'cid'}],next_cursor:null} : path.endsWith('/draft') ? cloud : batch)
    mocks.post.mockResolvedValue({id:'m1',conversation_id:'cid',message_seq:1,sender_user_id:'alice',body:'A',version:1,attachments:[],reply:null,retracted_at:null})
    const sending = store.send('cid'); await flushPromises()
    await store.applyBatch({...batch, events:[{event_seq:1,type:'draft.updated',entity_id:'cid',entity_version:1,conversation_id:'cid'}]})
    expect(store.drafts.cid.text).toBe('')
    reconcile.resolve(cloud); await sending
    expect(store.drafts.cid.text).toBe('')
    expect(store.drafts.cid.error).toContain('云端仍有另一份草稿')
    expect(mocks.get.mock.calls.filter(call => call[0].endsWith('/draft'))).toHaveLength(2)
    store.bind('')
  })
  it.each(['same', 'roundtrip', 'scroll'])('preserves the current reading window while filling a gap (%s)', async mode => {
    const store = useMessagingStore(); store.bind('alice:1'); store.selectedId = 'cid'
    store.conversations.push({id:'cid',peer:{id:'bob',display_name:'bob',available:true},last_message_seq:200,last_read_seq:0,unread:200,revision:1,updated_at:'',mute_until:null,pin_order:0,archived_at:null,version:1,peer_read_seq:null,last_message:null})
    store.drafts.cid = {text:'',reply_to_id:null,attachment_ids:[],version:0,revision:0,savedRevision:0,saving:false,error:'',reference:null}
    const message = (seq: number) => ({id:`m${seq}`,conversation_id:'cid',message_seq:seq,sender_user_id:'bob',kind:'text' as const,body:`row ${seq}`,client_message_id:null,version:1,created_at:'2026-01-01T00:00:00Z',retracted_at:null,reply_to_id:null,reply:null,reference:null,attachments:[]})
    store.history.cid = [...Array.from({length:50}, (_,i)=>message(i+1)),...Array.from({length:50}, (_,i)=>message(i+151))]; store.hasMore.cid = true
    const loaded = deferred<object>()
    mocks.get.mockReturnValueOnce(loaded.promise)
    const wrapper = mount(ChatPanel, {props:{fullPage:true},global:{stubs:{RouterLink:true,Teleport:true,AppreciationDialog:true}}})
    const scroller = wrapper.get('.connect-message-scroll').element as HTMLElement
    scroller.scrollTop = 300
    const bounds = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function(this: HTMLElement) {
      const index = this.dataset.messageSeq ? (store.history.cid ?? []).findIndex(row => row.message_seq === Number(this.dataset.messageSeq)) : -1
      const top = index < 0 ? 0 : index * 30 - scroller.scrollTop
      return {x:0,y:top,top,bottom:top+(index < 0 ? 500 : 30),left:0,right:600,width:600,height:index < 0 ? 500 : 30,toJSON:()=>({})}
    })
    Object.defineProperty(scroller,'scrollHeight',{get:()=> (store.history.cid?.length ?? 0)*30})
    await wrapper.get('button.connect-history-button').trigger('click'); await flushPromises()
    if (mode === 'roundtrip') { store.selectedId = 'other'; store.selectedId = 'cid'; scroller.scrollTop = 900 }
    if (mode === 'scroll') { scroller.scrollTop = 900; await wrapper.get('.connect-message-scroll').trigger('scroll') }
    loaded.resolve({items:Array.from({length:50}, (_,i)=>message(i+101)),has_more:true}); await flushPromises()
    expect(store.history.cid).toHaveLength(150)
    expect(scroller.scrollTop).toBe(mode === 'same' ? 300 : 900)
    bounds.mockRestore(); wrapper.unmount(); store.bind('')
  })
  it('retains attachments when sharing a reference and ignores a preview from a previous conversation', async () => {
    const store = useMessagingStore(); store.bind('alice:1')
    for (const id of ['first', 'second']) {
      store.conversations.push({ id, peer: { id, display_name: id, available: true }, last_message_seq: 0, last_read_seq: 0, unread: 0, revision: 1, updated_at: '', mute_until: null, pin_order: 0, archived_at: null, version: 1, peer_read_seq: null, last_message: null })
      store.drafts[id] = { text: '保留说明', reply_to_id: null, attachment_ids: [], version: 0, revision: 0, savedRevision: 0, saving: false, error: '', reference: null }
    }
    store.selectedId = 'first'; store.drafts.first!.attachment_ids = ['staged-image']
    const wrapper = mount(ChatPanel, { props: { fullPage: true }, global: { stubs: { RouterLink: true, Teleport: true, AppreciationDialog: true } } })
    await wrapper.get('[aria-label="分享业务记录"]').trigger('click')
    await wrapper.get('[aria-label="业务记录 ID"]').setValue('order-1')
    await wrapper.get('.connect-reference-form').trigger('submit')
    expect(mocks.post).not.toHaveBeenCalled()
    expect(store.drafts.first!.attachment_ids).toEqual(['staged-image'])
    expect(wrapper.text()).toContain('当前草稿还有附件')
    store.drafts.first!.attachment_ids = []
    const preview = deferred<object>(); mocks.post.mockReturnValueOnce(preview.promise)
    await wrapper.get('.connect-reference-form').trigger('submit')
    store.selectedId = 'second'; await flushPromises()
    preview.resolve({ reference: { available: true }, peer_can_view: true }); await flushPromises()
    expect(store.drafts.first!.reference).toBeNull()
    expect(store.drafts.second!.reference).toBeNull()
    expect(store.drafts.second!.text).toBe('保留说明')
    wrapper.unmount(); store.bind('')
  })
})
