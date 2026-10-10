import { afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useMessagingStore } from '@/stores/messaging'
import MySpaceView from '@/views/MySpaceView.vue'
import type { Preferences } from '@/api/collaboration'
const mocks = vi.hoisted(() => ({ patch:vi.fn() }))
vi.mock('@/api/collaboration', () => ({ collaborationApi:{patch:mocks.patch,get:vi.fn().mockResolvedValue({items:[],unseen:0,next_cursor:null})} }))
vi.mock('@/api/directory', () => ({ directoryApi:{getMember:vi.fn().mockResolvedValue({id:'alice',display_name:'Alice'})} }))
vi.mock('vue-router', async original => ({...await original<typeof import('vue-router')>(),useRoute:()=>({query:{}})}))
vi.mock('@/composables/useVisibleModules', async () => ({useVisibleModules:()=>({value:[]})}))
afterEach(()=>vi.resetAllMocks())

it('serializes preference saves and preserves edits made while a save is pending', async () => {
  setActivePinia(createPinia())
  useAuthStore().applySession({id:'alice',username:'alice',display_name:'Alice',roles:[],permissions:[],grants:[],factory_scopes:[],department_scopes:[],force_password_change:false})
  const store=useMessagingStore(); store.bind('alice:1')
  store.capabilities={enabled:true,eligible:true,owner:{user_id:'alice',employment_epoch:1},features:{},limits:{}}
  store.profile={bio:'',help_topics:'',skill_tags:[],theme:'celadon',availability:'available',status_text:'',status_expires_at:null,version:0}
  const pref:Preferences={motion:'rich',density:'comfortable',sound_enabled:false,read_receipts_enabled:false,dnd_until:null,send_key:'enter',module_shortcuts:[],version:0}
  store.preferences=pref
  let resolve!:(value:Preferences)=>void
  mocks.patch.mockReturnValueOnce(new Promise<Preferences>(r=>resolve=r))
  const wrapper=mount(MySpaceView,{global:{stubs:{RouterLink:true,MemberCard:true}}})
  await flushPromises()
  const save=wrapper.findAll('button').find(b=>b.text()==='保存偏好')!
  await save.trigger('click'); await flushPromises()
  expect(save.attributes('disabled')).toBeDefined()
  const motion=wrapper.get('#preferences select')
  await motion.setValue('simple'); await save.trigger('click')
  expect(mocks.patch).toHaveBeenCalledTimes(1)
  resolve({...pref,version:1}); await flushPromises()
  expect((motion.element as HTMLSelectElement).value).toBe('simple')
  expect(wrapper.text()).toContain('新修改尚未保存')
  mocks.patch.mockResolvedValueOnce({...pref,motion:'simple',version:2})
  await save.trigger('click'); await flushPromises()
  expect(mocks.patch.mock.calls[1]![1]).toMatchObject({expected_version:1,motion:'simple'})
  expect(wrapper.text()).toContain('偏好已保存')
  expect(save.attributes('disabled')).toBeUndefined()
  wrapper.unmount(); store.bind('')
})
