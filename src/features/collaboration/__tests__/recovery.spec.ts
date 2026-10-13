import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useMessagingStore } from '@/stores/messaging'
const mocks = vi.hoisted(() => ({ get: vi.fn(), stream: vi.fn() }))
vi.mock('@/api/collaboration', () => ({ collaborationApi: { get: mocks.get } }))
vi.mock('../stream', () => ({ consumeStream: mocks.stream }))
afterEach(() => vi.restoreAllMocks())

it.each(['handshake', 'poll'])('bootstraps automatically after an expired cursor in %s', async mode => {
  setActivePinia(createPinia()); vi.resetAllMocks()
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  useAuthStore().applySession({ id:'alice',username:'alice',display_name:'alice',roles:[],permissions:[],grants:[],factory_scopes:[],department_scopes:[],force_password_change:false })
  const store = useMessagingStore(); store.bind('alice:1')
  const owner = {user_id:'alice',employment_epoch:1}
  const capabilities = {enabled:true,eligible:true,owner}
  const oldCursor = btoa(JSON.stringify([1,'alice',1,1])), newCursor = btoa(JSON.stringify([1,'alice',1,50]))
  mocks.get.mockImplementation(async (path: string) => {
    if (path === '/capabilities') return capabilities
    if (path === '/sync') throw { response: {data: {detail: {code:'RESET_REQUIRED'}}} }
    if (path === '/bootstrap') return {owner,cursor:newCursor,conversations:{items:[],next_cursor:null},preferences:{},unread:0}
    return {}
  })
  await store.refreshCapabilities(); store.cursor = oldCursor
  store.drafts.cid = {text:'本机未发送',reply_to_id:null,attachment_ids:[],version:0,revision:1,savedRevision:0,saving:false,error:'',reference:null}
  mocks.stream.mockRejectedValueOnce(new Error(mode === 'handshake' ? 'stream:reset' : 'stream:502')).mockImplementation(() => new Promise(() => {}))
  store.resume(); await flushPromises(); await flushPromises()
  expect(store.cursor).toBe(newCursor)
  expect(mocks.stream).toHaveBeenCalledTimes(2)
  expect(mocks.get.mock.calls.filter(call => call[0] === '/bootstrap')).toHaveLength(2)
  expect(store.drafts.cid.text).toBe('本机未发送')
  store.bind('')
})
