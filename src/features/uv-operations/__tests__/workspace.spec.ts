import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest'
import {defineComponent,reactive} from 'vue'
import {flushPromises,mount} from '@vue/test-utils'
import {createUvWorkspace,type UvWorkspace} from '../workspace'
const auth=reactive({currentUser:{id:'A'},authorizationVersion:1,effectiveAccess:[],isAuthenticated:true,refreshSession:vi.fn()})
const app=reactive({activeFactoryId:'huakang-a'})
const route=reactive({query:{factory:'huakang-a'}})
vi.mock('@/stores/auth',()=>({useAuthStore:()=>auth}))
vi.mock('@/stores/app',()=>({useAppStore:()=>app}))
vi.mock('vue-router',()=>({useRoute:()=>route}))
const meta={factory_id:'huakang-a',authorization_version:1,view_revision:1,data_mode:'synthetic',coverage:{state:'partial'},warnings:[]}
const snapshot={machines:[],tasks:[],runs:[],schedule:[],shifts:[],batches:[],collection_totals:{}}
class Stream {
  static instances:Stream[]=[]
  closed=false
  listeners=new Map<string,(event:MessageEvent)=>void>()
  constructor(){Stream.instances.push(this)}
  addEventListener(name:string,listener:(event:MessageEvent)=>void){this.listeners.set(name,listener)}
  close(){this.closed=true}
  emit(name:string,data:unknown){this.listeners.get(name)?.({data:JSON.stringify(data)} as MessageEvent)}
}
const response=(data:unknown,extra:Record<string,unknown>={})=>({ok:true,status:200,json:async()=>({data,meta,...extra})})
const fetcher=vi.fn(async (url:string)=>response(url.includes('/access?')?{permissions:['read']}:snapshot))
describe('UV live workspace lifecycle',()=>{
  let w:UvWorkspace,wrapper:ReturnType<typeof mount>|undefined
  beforeEach(()=>{
    auth.currentUser={id:'A'};auth.authorizationVersion=1;app.activeFactoryId='huakang-a';route.query.factory='huakang-a'
    Stream.instances=[];fetcher.mockReset();fetcher.mockImplementation(async url=>response(url.includes('/access?')?{permissions:['read']}:snapshot))
    vi.stubGlobal('EventSource',Stream);vi.stubGlobal('fetch',fetcher)
    vi.spyOn(document,'hidden','get').mockReturnValue(false)
    wrapper=mount(defineComponent({setup(){w=createUvWorkspace();return()=>null}}))
  })
  afterEach(()=>{wrapper?.unmount();vi.restoreAllMocks();vi.unstubAllGlobals()})
  it('ignores a completed old request after factory context changes, and closes its stream',async()=>{
    await flushPromises();const oldStream=Stream.instances[0]!
    let finish!:(value:ReturnType<typeof response>)=>void
    fetcher.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
    const pending=w.load(['tasks']).catch(cause=>cause)
    app.activeFactoryId='huakang-b';await flushPromises()
    finish(response([{id:'OLD-FACTORY',version:1}]));const result=await pending
    expect(result.name).toBe('AbortError');expect(w.items('tasks')).toEqual([]);expect(w.ready.value).toBe(false);expect(oldStream.closed).toBe(true)
    oldStream.emit('snapshot',{data:{...snapshot,tasks:[{id:'LATE-SSE',version:1}]},meta:{...meta,view_revision:99}})
    expect(w.items('tasks')).toEqual([])
  })
  it('keeps explicitly paged rows when a bounded live snapshot arrives',async()=>{
    await flushPromises()
    fetcher.mockResolvedValueOnce(response([{id:'ONE',version:1}],{pagination:{total:2,has_more:true,next_cursor:'ONE'}}))
    await w.load(['runs'])
    fetcher.mockResolvedValueOnce(response([{id:'TWO',version:1}],{pagination:{total:2,has_more:false,next_cursor:null}}))
    await w.load(['runs'],true)
    Stream.instances[0]!.emit('snapshot',{data:{...snapshot,runs:[{id:'LIVE',version:1}]},meta:{...meta,view_revision:2}})
    expect(w.items('runs').map(row=>row.id)).toEqual(['ONE','TWO']);expect(w.liveData.value.runs?.[0]?.id).toBe('LIVE')
  })
  it('clears cached sensitive data on authorization revision change from SSE',async()=>{
    await flushPromises();w.data.value={tasks:[{id:'sensitive',version:1,cost_price_snapshot:{rate:'0.015'}}]}
    Stream.instances[0]!.emit('snapshot',{data:snapshot,meta:{...meta,authorization_version:2}})
    expect(w.data.value).toEqual({});expect(w.permissions.value).toEqual([]);expect(auth.refreshSession).toHaveBeenCalled()
  })
  it('retains the last snapshot and gives a retryable localized error for an empty proxy failure',async()=>{
    await flushPromises();w.data.value={tasks:[{id:'LAST',version:1}]}
    fetcher.mockResolvedValueOnce({ok:false,status:502,json:async()=>{throw new SyntaxError('Unexpected end')}})
    await w.refresh()
    expect(w.offline.value).toBe(true);expect(w.items('tasks')[0]?.id).toBe('LAST')
    expect(w.error.value).toContain('服务暂时不可用');expect(w.error.value).not.toContain('Unexpected')
    const staleStream=Stream.instances[0]!
    await w.refresh()
    expect(w.offline.value).toBe(false);expect(staleStream.closed).toBe(true);expect(Stream.instances).toHaveLength(2)
  })
})
