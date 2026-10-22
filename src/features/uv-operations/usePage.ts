import { onBeforeUnmount, onMounted, provide, ref, watch, type InjectionKey, type Ref } from 'vue'
import { type Entity } from './contracts'
import { useUvWorkspace } from './workspace'
export const uvPageState: InjectionKey<{busy:Ref<boolean>;error:Ref<string>}> = Symbol('uv-page-state')
export function useUvPage(collections: () => string[]) {
  const w=useUvWorkspace(), busy=ref(true), error=ref(''), action=ref<string|null>(null), target=ref<Entity|null>(null), preset=ref<Record<string,unknown>>({})
  let version=0
  provide(uvPageState,{busy,error})
  async function reload() { const request=++version; busy.value=true; error.value=''; try { await w.load(collections()) } catch(cause) {if(request===version)error.value=w.explain(cause)} finally {if(request===version)busy.value=false} }
  function open(name:string,row:Entity|null=null,values:Record<string,unknown>={}) { target.value=row; preset.value=values; action.value=name }
  onMounted(reload)
  watch(w.contextVersion,()=>{version++;action.value=null;target.value=null;preset.value={};error.value='';busy.value=false})
  onBeforeUnmount(()=>version++)
  return {w,busy,error,action,target,preset,reload,open}
}
