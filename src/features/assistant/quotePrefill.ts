/** Single-use, in-memory text handoff. Business writes stay in the native form. */
import { shallowRef } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
import { internalQuoteApi, type ApiInternalQuote } from '@/api/internalQuote'
import { assistantApi } from './api'
import { identityKey } from './context'
import type { Message } from './types'
import type { UIAction } from './v2'

export interface QuotePrefillTarget {quoteId:string; factoryId:string; headerRevision:number; label:string; actionIndex:number}
export interface QuoteSuggestion extends QuotePrefillTarget {runId:string; text:string}
interface Pending extends QuoteSuggestion {identity:string; expires:number}
const pending=shallowRef<Pending | null>(null)
let expiryTimer: ReturnType<typeof setTimeout> | undefined
export function prefillIdentityKey() {
  const auth=useAuthStore()
  return `${identityKey(auth.currentUser)}:${getAuthenticationGeneration()}:${auth.authorizationVersion}:${auth.currentUser?.identity?.effective_context_key || ''}`
}
export function clearQuotePrefill() { clearTimeout(expiryTimer); pending.value=null }
export function invalidateQuotePrefill() { if(pending.value?.identity!==prefillIdentityKey()) clearQuotePrefill() }
export function quotePrefillFor(quoteId:string,factoryId:string) {
  const value=pending.value
  return value && value.identity===prefillIdentityKey() && value.expires>Date.now() && value.quoteId===quoteId && value.factoryId===factoryId ? value : null
}
export function quotePrefillTargets(message: Message): QuotePrefillTarget[] {
  if(message.unavailable || message.status!=='completed') return []
  const actions=(message.content_parts.find(p=>p.type==='actions')?.items || []) as UIAction[]
  const targets: QuotePrefillTarget[]=[]
  for(const part of message.content_parts) {
    const value=part.result as {contract_version?:number;tool_name?:string;rows?:Record<string,unknown>[]} | undefined
    if(part.type!=='business_snapshot' || value?.contract_version!==3 || value.tool_name!=='get_internal_quote_overview') continue
    for(const row of value.rows || []) {
      const quoteId=String(row.id || ''),factoryId=String(row.factory_id || ''),headerRevision=Number(row.header_revision)
      const actionIndex=actions.findIndex(a=>a.type==='open_record' && a.route_name==='internal-quote-collaboration' && a.resource?.module_id==='internal-quote' && a.resource.resource_id===quoteId && a.params.quoteId===quoteId && a.query.factory===factoryId)
      if(!quoteId || !factoryId || row.resource_ref!==`internal-quote:quote:${quoteId}` || !Number.isInteger(headerRevision) || headerRevision<1 || actionIndex<0 || targets.some(t=>t.quoteId===quoteId)) continue
      targets.push({quoteId,factoryId,headerRevision,label:`${row.quote_no} / ${row.version_label}`,actionIndex})
    }
  }
  return targets
}
async function currentTarget(runId:string,target:QuotePrefillTarget) {
  const snapshot=await assistantApi.snapshot(runId)
  const answer=snapshot.items.find(m=>m.role==='assistant')
  const current=answer && quotePrefillTargets(answer).find(t=>t.quoteId===target.quoteId && t.factoryId===target.factoryId && t.headerRevision===target.headerRevision)
  if(!current) throw new Error('原回答或报价版本已不可用，请重新查询。')
  return current
}
function headerStillEditable(quote:ApiInternalQuote) {
  if(quote.version_archived || quote.document_archive || ['final_pending','final_reviewing','fully_approved','released','exported','archived'].includes(quote.status) || quote.final_release_status==='issued') return false
  if(quote.module_version==='v4' || quote.module_version==='v3' && quote.status==='rejected') return true
  const required=quote.sections?.filter(section=>section.is_required)
  return !!required?.length && required.every(section=>section.status==='draft' && section.revision===1)
}
export async function prepareQuotePrefill(runId:string,target:QuotePrefillTarget,text:string) {
  const identity=prefillIdentityKey(), value=text.trim()
  if(!value || value.length>2000) throw new Error('请填写不超过2000字的备注建议。')
  const current=await currentTarget(runId,target)
  const action=await assistantApi.action(runId,current.actionIndex)
  if(action.type!=='open_record' || action.route_name!=='internal-quote-collaboration' || action.params.quoteId!==current.quoteId || action.query.factory!==current.factoryId) throw new Error('原报价入口已失效。')
  if(identity!==prefillIdentityKey()) throw new Error('身份或权限已变化，请重新操作。')
  clearQuotePrefill()
  pending.value={...current,runId,text:value,identity,expires:Date.now()+5*60_000}
  expiryTimer=setTimeout(clearQuotePrefill,5*60_000)
  return action
}
export async function consumeQuotePrefill(quoteId:string,factoryId:string,headerRevision:number,editable:()=>boolean) {
  const value=quotePrefillFor(quoteId,factoryId)
  if(!value || !editable()) throw new Error('当前报价不可修改资料，未带入备注。')
  try {
    await currentTarget(value.runId,value)
    const native=await internalQuoteApi.get(quoteId)
    if(native.id!==quoteId || native.factory_id!==factoryId || native.header_revision!==headerRevision || value.headerRevision!==headerRevision) throw new Error('原报价已产生新revision，请重新查询后带入，当前表单未改变。')
    if(!headerStillEditable(native)) throw new Error('当前原报价已不可修改资料，请重新读取原页面。')
    if(pending.value!==value || value.identity!==prefillIdentityKey() || value.expires<=Date.now() || !editable()) throw new Error('报价或身份已变化，未带入备注。')
    const suggestion:QuoteSuggestion={...value}
    clearQuotePrefill()
    return suggestion
  } catch(error) { if(pending.value===value) clearQuotePrefill(); throw error }
}
