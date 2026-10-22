<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
import { cuttingApi,errorMessage,type Access } from './api'
import { canReadCutover,cutoverApi,type CutoverPreview,type CutoverScope,type ExternalOpening,type CutoverTarget } from './cutoverApi'
import { cuttingDestination } from './location'

const props=defineProps<{access?:Access;accessLoading?:boolean}>()
const emit=defineEmits<{payment:[month:string,id:string,eventId?:string];settlement:[month:string,id:string,eventId?:string]}>()
const currentMonth=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit'}).format(new Date())
const month=ref(currentMonth),scope=ref<CutoverScope>('internal'),result=ref<CutoverPreview>(),busy=ref(false),error=ref('')
const inputs=ref<Record<string,{value:string;evidence:string;unit:string}>>({}),external=ref<ExternalOpening[]>([]),page=ref(1)
const draftContext=ref('')
const draftScope=ref<CutoverScope>()
const query=ref(''),batch=ref(1),batchSize=ref(50),batchKeys=ref<Record<number,string[]>>({})
const context=computed(()=>JSON.stringify([month.value,scope.value,query.value.trim(),batchSize.value]))
const allowed=computed(()=>canReadCutover(props.access,scope.value))
const visible=computed(()=>matches.value.slice((page.value-1)*30,page.value*30))
const dirty=computed(()=>Object.values(inputs.value).some(r=>r.value!==''||r.evidence!=='')||external.value.length>0)
const changed=computed(()=>!!draftContext.value&&draftContext.value!==context.value)
let generation=0,alive=true,controller:AbortController|undefined
function invalidate(){generation++;controller?.abort();result.value=undefined;busy.value=false;error.value='';page.value=1}
function clear(){invalidate();inputs.value={};external.value=[];draftContext.value='';draftScope.value=undefined;batchKeys.value={};batch.value=1}
function checkDraftAccess(){
  // A failed parent access read is unknown, not a confirmed revocation. Keep the
  // draft hidden until access is revalidated; explicit denial/session exit clears it.
  if(!props.accessLoading&&props.access&&!canReadCutover(props.access,draftScope.value??scope.value))clear()
}
watch(()=>props.access,checkDraftAccess,{deep:true})
watch(()=>props.accessLoading,checkDraftAccess)
function beforeLeave(){return !dirty.value||window.confirm('期初对照资料仅在本页临时保留，离开后将丢失。确定离开？')}
onBeforeRouteLeave(beforeLeave)
onBeforeRouteUpdate(beforeLeave)
function beforeUnload(e:BeforeUnloadEvent){if(dirty.value){e.preventDefault();e.returnValue=''}}
window.addEventListener('beforeunload',beforeUnload)
window.addEventListener('auth-session-boundary-changed',clear)
onBeforeUnmount(()=>{alive=false;clear();window.removeEventListener('beforeunload',beforeUnload);window.removeEventListener('auth-session-boundary-changed',clear)})
function edit(){if(result.value)result.value={...result.value,counts:{},rows:result.value.rows.map(r=>({...r,status:'待重新核对',difference:undefined,declared:undefined,evidence:undefined}))}}
async function run(compare=false,nextBatch=batch.value){
  if(busy.value||!allowed.value||props.accessLoading)return
  if(changed.value){if(!beforeLeave())return;clear();nextBatch=1}
  if(compare&&!result.value)return
  draftContext.value=context.value;draftScope.value=scope.value
  const selectedMonth=month.value,selectedScope=scope.value,selectedContext=context.value,ticket=++generation,auth=getAuthenticationGeneration()
  const keys=new Set(result.value?.rows.map(r=>r.key))
  const options={batch:nextBatch,batch_size:batchSize.value,query:query.value.trim(),...(compare?{token:result.value!.token,comparisons:Object.entries(inputs.value).filter(([key,r])=>keys.has(key)&&(r.value!==''||r.evidence!=='')).map(([key,r])=>({key,...r})),external:external.value.map(r=>({...r}))}:{})}
  controller=new AbortController();busy.value=true;error.value=''
  const valid=()=>alive&&ticket===generation&&auth===getAuthenticationGeneration()&&allowed.value&&selectedContext===context.value
  try{
    const access=await cuttingApi.access();if(!valid())return
    if(!canReadCutover(access,selectedScope)){clear();error.value='期初核对权限已变化，请重新读取页面。';return}
    const response=await cutoverApi.preview(selectedMonth,selectedScope,options,controller.signal)
    if(!valid())return
    const current=await cuttingApi.access();if(!valid())return
    if(!canReadCutover(current,selectedScope)){clear();error.value='期初核对权限已撤销。';return}
    result.value=response;page.value=1;batch.value=nextBatch
    batchKeys.value[nextBatch]=[...new Set([...(batchKeys.value[nextBatch]??[]),...response.rows.map(r=>r.key)])]
    // Preserve local source material on refresh; obsolete mappings remain visible for explicit removal.
    for(const row of response.rows)inputs.value[row.key]??={value:'',evidence:'',unit:row.unit}
  }catch(e){if(valid()){
    const status=(e as {response?:{status?:number}}).response?.status
    if(status===401||status===403)clear()
    else if(status!==422)result.value=undefined
    else edit()
    error.value=errorMessage(e)
  }}finally{if(alive&&ticket===generation)busy.value=false}
}
const obsolete=computed(()=>result.value?(batchKeys.value[batch.value]??[]).filter(key=>inputs.value[key]&&!result.value!.rows.some(r=>r.key===key)&&(inputs.value[key]!.value!==''||inputs.value[key]!.evidence!=='')):[])
const filtered=ref('')
const matches=computed(()=>result.value?.rows.filter(r=>!filtered.value||`${r.category} ${r.label} ${r.status}`.includes(filtered.value))??[])
const destination=(target:CutoverTarget)=>cuttingDestination(target.line_id!,target.month,target.workspace,target.kind,target.id)
function openFinance(target:CutoverTarget){if(target.workspace==='payment')emit('payment',target.month,target.id,target.event_id);else emit('settlement',target.month,target.id,target.event_id)}
watch(filtered,()=>{page.value=1})
</script>

<template>
  <SectionPanel title="历史期初核对与切入准备" class="cutting-content-panel">
    <p>按切入月份 1 日以前的最新有效记录核对。仅作准备预览，不保存期初、不增加库存或应付，不改变锁月起点。</p>
    <p>对照值只计算差额，不叠加系统数。空白表示未核对，明确填写 0 才表示零。对照资料仅在本页临时保留。</p>
    <form class="order-toolbar" @submit.prevent="run()">
      <label>切入月份<input v-model="month" type="month" min="2000-02" :max="currentMonth" required :disabled="busy" /></label>
      <label>核对范围<select v-model="scope" :disabled="busy"><option value="internal" :disabled="!canReadCutover(access,'internal')">内部物料、在制与生产</option><option value="finance" :disabled="!canReadCutover(access,'finance')">外发验收与应付款</option></select></label>
      <label>范围查询<input v-model="query" maxlength="80" :disabled="busy" placeholder="内部：客户／订单／货号；财务：凭据／对象" /></label>
      <label>每批数量<input v-model.number="batchSize" type="number" min="1" max="200" required :disabled="busy" /></label>
      <Button type="submit" variant="outline" :disabled="busy||!allowed||accessLoading">{{busy?'正在核对…':'读取系统依据'}}</Button>
    </form>
    <p v-if="!allowed&&!accessLoading">内部范围需材料成本查看权限；财务范围需外发结算及付款查看权限。</p>
    <p v-if="error" role="alert" class="cutting-error">{{error}}</p>
    <Button v-if="batch>1&&(!result||error)" variant="outline" :disabled="busy||!allowed||accessLoading" @click="run(false,1)">返回第一批重新读取</Button>
    <p v-if="changed">月份、范围或分批条件已改变，请读取对应系统依据。</p>
    <template v-if="result&&!changed&&allowed&&!accessLoading">
      <p>期初截止：{{result.cutoff}}；取数时间：{{result.generated_at}}。补录、更正、反结会改变新预览，本表不是冻结期初。</p>
      <nav v-if="result.batch" class="order-pagination" aria-label="期初核对批次">
        <span>第 {{result.batch.number}} / {{result.batch.pages}} 批 · 当前筛选共 {{result.batch.total}} {{result.batch.unit}}</span>
        <Button variant="outline" :disabled="busy||batch<=1" @click="run(false,batch-1)">上一批</Button>
        <Button variant="outline" :disabled="busy||batch>=result.batch.pages" @click="run(false,batch+1)">下一批</Button>
        <Button variant="outline" :disabled="busy||batch===1" @click="run(false,1)">返回第一批</Button>
      </nav>
      <p>仅显示当前批次，以下核对状态不代表全量结论。内部只列截止日前有生产／实发历史或上月冻结依据的订单。切换批次保留本页输入，返回后须重新核对；查询筛选不代表其余资料不存在。</p>
      <p v-if="scope==='finance'">应付按结算所属月、付款按实际付款日核对；采用当前有效凭据重算。切入后付款不扣期初未付，待复核付款不计已付。</p>
      <p v-for="(notice,i) in result.notices" :key="i" class="cutting-error">{{notice.message}}</p>
      <p>{{Object.entries(result.counts).map(([key,value])=>`${key} ${value} 项`).join('；')||'输入已变化，须重新核对差异。'}}</p>
      <p v-if="!result.rows.length">系统在本批无可核对数值明细；不代表账外期初为零，请核查原始资料及凭据链。</p>
      <label>本批明细筛选<input v-model="filtered" placeholder="类别／对象／核对状态" /></label>
      <div class="cutting-table-scroll" role="region" aria-label="期初对照明细" tabindex="0"><table>
        <thead><tr><th>类别／对象</th><th>系统值</th><th>单位／币种</th><th>账外对照值</th><th>原始资料依据</th><th>差额／状态</th><th>来源与口径</th></tr></thead>
        <tbody><tr v-for="row in visible" :key="row.key">
          <td>{{row.category}}<br />{{row.label}}</td><td>{{row.value??'待确认'}}</td><td>{{row.unit}}</td>
          <td><input v-if="inputs[row.key]" v-model="inputs[row.key]!.value" :aria-label="row.category+'对照值'" inputmode="decimal" maxlength="30" :disabled="busy" @input="edit" /><template v-if="inputs[row.key]&&inputs[row.key]!.unit!==row.unit"><p>原对照单位 {{inputs[row.key]!.unit}} 已变化，请核对原始资料。</p><Button variant="outline" :disabled="busy" @click="inputs[row.key]={value:'',evidence:'',unit:row.unit};edit()">清空旧单位对照</Button></template></td>
          <td><input v-if="inputs[row.key]" v-model="inputs[row.key]!.evidence" :aria-label="row.category+'原始资料依据'" maxlength="500" :disabled="busy" @input="edit" /></td>
          <td>{{row.status}}<br />{{row.difference??'—'}}</td><td><details><summary>查看依据</summary><p>{{row.note}}</p><p v-for="source in row.sources" :key="source">{{source}}</p></details>
            <RouterLink v-if="row.target?.line_id" :to="destination(row.target)">定位原记录</RouterLink>
            <Button v-else-if="row.target" variant="outline" :disabled="busy||accessLoading" @click="openFinance(row.target)">定位原凭据</Button>
          </td>
        </tr></tbody>
      </table></div>
      <nav class="order-pagination" aria-label="期初核对分页"><span>第 {{page}} 页 · 筛选 {{matches.length}} / 本批 {{result.rows.length}} 项</span><Button variant="outline" :disabled="page<=1||busy" @click="page--">上一页</Button><Button variant="outline" :disabled="page*30>=matches.length||busy" @click="page++">下一页</Button></nav>
      <p v-for="key in obsolete" :key="key">原映射 {{key}} 本批已不再出现（可能已更正或批次范围变化），对照资料仍保留：{{inputs[key]?.value}} / {{inputs[key]?.evidence}}。<Button variant="outline" :disabled="busy" @click="delete inputs[key];edit()">移除失效映射</Button></p>
      <details v-for="trace in result.history" :key="trace.key">
        <summary>{{trace.kind==='payment'?'付款':'结算'}} {{trace.label}} {{trace.document_id}} · 当前{{trace.state}}</summary>
        <p>{{trace.effective?'仅当前有效版本按截止口径参与核对；以下旧版本不重复计数。':'当前已失效或未确认，不计入有效金额；保留旧版本解释变动。'}}</p>
        <p v-for="entry in trace.history" :key="entry.id">{{entry.day}} · {{entry.action}} · {{entry.amount}} {{entry.currency}} · {{entry.actor}}（{{entry.actor_id}}）· {{entry.date}} · 原因：{{entry.reason||'—'}}<br />记录 {{entry.id}} · 凭据 {{entry.reference||'—'}}<span v-if="entry.replaces_document_id"> · 替代原凭据 {{entry.replaces_document_id}}</span>
          <Button variant="outline" :disabled="busy||accessLoading" @click="openFinance(entry.target)">定位此版本</Button>
        </p>
        <p v-for="replacement in trace.replacements" :key="replacement.id">后继更正凭据 {{replacement.id}} <Button variant="outline" :disabled="busy||accessLoading" @click="openFinance(replacement.target)">定位后继凭据</Button></p>
      </details>
      <h3>无法映射的账外事项</h3><p>登记缺少的库存、在制或历史未付资料，后续核实后再办理专门期初；不会自动入账。</p>
      <div v-for="(item,index) in external" :key="index" class="order-toolbar">
        <label>事项说明<input v-model="item.description" maxlength="500" :disabled="busy" @input="edit" /></label>
        <label>资料依据<input v-model="item.evidence" maxlength="500" :disabled="busy" @input="edit" /></label>
        <Button variant="outline" :disabled="busy" @click="external.splice(index,1);edit()">移除事项</Button>
      </div>
      <div class="order-toolbar"><Button variant="outline" :disabled="busy||external.length>=100" @click="external.push({description:'',evidence:''});edit()">增加账外事项</Button><Button :disabled="busy||obsolete.length>0" @click="run(true)">核对差异</Button></div>
      <p>账外待处理 {{external.length}} 项。即使已填各项一致，仍须完成资料完整性、正式岗位和切入审批验收，不代表可以正式入账。</p>
    </template>
  </SectionPanel>
</template>
