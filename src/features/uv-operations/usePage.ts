import { onMounted, ref } from 'vue'
import { type Entity } from './contracts'
import { useUvWorkspace } from './workspace'
export function useUvPage(collections: () => string[]) {
  const w=useUvWorkspace(), busy=ref(false), error=ref(''), action=ref<string|null>(null), target=ref<Entity|null>(null), preset=ref<Record<string,unknown>>({})
  async function reload() { busy.value=true; error.value=''; try { await w.load(collections()) } catch(cause) {error.value=w.explain(cause)} finally {busy.value=false} }
  function open(name:string,row:Entity|null=null,values:Record<string,unknown>={}) { target.value=row; preset.value=values; action.value=name }
  onMounted(reload)
  return {w,busy,error,action,target,preset,reload,open}
}
