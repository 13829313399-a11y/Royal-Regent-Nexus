import {createPinia,setActivePinia} from 'pinia'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
vi.mock('vue-router',async original=>{
  const actual=await original<typeof import('vue-router')>()
  return {...actual,createWebHistory:actual.createMemoryHistory}
})
import {router} from '@/router'
const paths=['/monthly-title-check','/monthly-title-other','/monthly-title-newest']
let cleanup:Array<()=>void>=[]
beforeEach(async()=>{
  setActivePinia(createPinia())
  cleanup=paths.map((path,i)=>router.addRoute({path,name:`monthly-title-${i}`,component:{template:'<div />'},meta:{requiresAuth:false,title:`月结标题${i}`}}))
  await router.replace(paths[0]!)
})
afterEach(()=>{cleanup.reverse().forEach(stop=>stop());vi.restoreAllMocks()})
it('retains the active title when a form navigation guard refuses the target',async()=>{
  const title=document.title
  cleanup.push(router.beforeResolve(to=>to.path===paths[1]?false:true))
  await router.push(paths[1]!)
  expect(router.currentRoute.value.path).toBe(paths[0]);expect(document.title).toBe(title)
})
it('does not let a cancelled older navigation replace the newest successful title',async()=>{
  let finish!:(value:boolean)=>void
  cleanup.push(router.beforeResolve(to=>to.path===paths[1]?new Promise<boolean>(r=>finish=r):true))
  const older=router.push(paths[1]!)
  await vi.waitFor(()=>expect(finish).toBeTypeOf('function'))
  await router.push(paths[2]!)
  finish(true);await older
  expect(router.currentRoute.value.path).toBe(paths[2]);expect(document.title).toBe('月结标题2 | Royal Regent Nexus')
})
it('updates a successful title and leaves it unchanged for duplicate navigation',async()=>{
  await router.push(paths[1]!);expect(document.title).toBe('月结标题1 | Royal Regent Nexus')
  await router.push(paths[1]!);expect(document.title).toBe('月结标题1 | Royal Regent Nexus')
})
