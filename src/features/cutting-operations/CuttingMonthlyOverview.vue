<script setup lang="ts">
import { watchCuttingWorkspace } from './workspaceRefresh'
import {ref,watch,onBeforeUnmount,useId} from 'vue'
import {Button} from '@/components/ui/button'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import CuttingMetrics from './CuttingMetrics.vue'
import CuttingReportExport from './CuttingReportExport.vue'
import CuttingReadTarget from './CuttingReadTarget.vue'
import {errorMessage,type Access} from './api'
import {businessDay,workspaceApi} from './workspaceApi'
type Domain='period'|'settlement'|'payment'
interface Frozen {kind:Domain;event_id:string;document_id:string;version:number;month:string;valid:boolean;actor:string;date:string}
interface MonthView {month:string;domains:Array<{kind:Domain;available:boolean;reason?:string;states?:Record<string,number>;count?:number}>;frozen:Frozen[]}
defineProps<{access?:Access;exportsOnly?:boolean}>()
const emit=defineEmits<{open:[kind:Domain,month:string,id:string,eventId?:string];loaded:[month:string]}>()
const formId=`cutting-monthly-${useId()}`
const month=defineModel<string>('month',{default:businessDay().slice(0,7)})
const value=ref<MonthView>(),busy=ref(false),error=ref('')
const failedRead=ref<{month:string}>(),readingMonth=ref('')
const names:Record<Domain,string>={period:'内部月结',settlement:'外发对账与结算',payment:'付款登记与核销'}
const states:Record<string,string>={save:'草稿',submit:'待复核',return:'已退回',lock:'已锁月',reopen:'已反结',confirm:'已复核生效',reverse:'已冲销'}
let generation=0,alive=true
async function load(target=month.value){const ticket=++generation;busy.value=true;readingMonth.value=target;failedRead.value=undefined;error.value='';value.value=undefined
  try{const result=await workspaceApi.monthly(target);if(alive&&ticket===generation){value.value=result;emit('loaded',target)}}
  catch(e){if(alive&&ticket===generation){error.value=errorMessage(e);const status=(e as {response?:{status?:number}})?.response?.status;if(status!==401&&status!==403)failedRead.value={month:target}}}finally{if(alive&&ticket===generation)busy.value=false}}
watch(month,()=>void load(),{immediate:true});onBeforeUnmount(()=>{alive=false;generation++})
watchCuttingWorkspace(()=>void load())
</script>
<template>
  <div class="cutting-overview">
    <form class="order-toolbar" @submit.prevent="load()"><label :for="`${formId}-month`">核对月份<input :id="`${formId}-month`" name="month" v-model="month" type="month" min="2000-01" :max="businessDay().slice(0,7)" required /></label><Button :disabled="busy">查询／刷新</Button></form>
    <p v-if="busy" role="status">正在读取 {{readingMonth}} 月结进度…</p><p v-if="error" role="alert">{{error}}</p>
    <CuttingReadTarget v-if="failedRead" :target="failedRead" :label="exportsOnly?'冻结报表列表':'月结进度'" retry-label="按原月份重试" :disabled="busy" readable @retry="load(failedRead!.month)" />
    <template v-if="value">
      <CuttingMetrics v-if="!exportsOnly" :items="value.domains.map(d=>({label:names[d.kind],value:d.available?d.count??0:'—',unit:d.available?'份':'',hint:d.available?Object.entries(d.states??{}).map(([s,n])=>`${states[s]??s} ${n}`).join(' · ')||'本月尚未编制':d.reason}))" />
      <SectionPanel v-if="!exportsOnly" title="月结办理与核对" class="cutting-content-panel">
        <p>内部月结按裁床部整月锁定；外发结算、实际付款分别复核。下列数量表示单据当前状态，不表示已经满足锁月条件。</p>
        <div class="cutting-master-actions"><Button v-for="d in value.domains.filter(d=>d.available)" :key="d.kind" variant="outline" @click="$emit('open',d.kind,value.month,'')">办理{{names[d.kind]}}</Button></div>
        <p class="cutting-muted">进入内部月结核对缺价、期初、完工归属及更正依赖；提交外发对账仅占用验收数量，付款待复核仅占用可核销金额，均不代表已付款。</p>
      </SectionPanel>
      <SectionPanel :title="exportsOnly?'冻结报表与版本导出':'本月冻结记录'" class="cutting-content-panel">
        <p class="cutting-muted">导出读取对应不可变快照。历史已失效版本仅供追溯，不计入当前有效月结、应付或已付。</p>
        <article v-for="row in value.frozen" :key="row.event_id" class="cutting-master-line">
          <h3>{{names[row.kind]}} · {{row.document_id}} · V{{row.version}}</h3>
          <StatusPill :label="row.valid?'当前有效冻结版本':'历史已失效版本'" compact />
          <p>{{row.actor}} · {{row.date}}</p>
          <Button variant="outline" size="sm" @click="$emit('open',row.kind,row.month,row.document_id,row.event_id)">查看冻结依据</Button>
          <CuttingReportExport v-if="exportsOnly&&access&&row.kind!=='payment'" :selection="{kind:row.kind,month:row.month,event_id:row.event_id,document_id:row.kind==='period'?undefined:row.document_id}" :access="access" />
        </article>
        <p v-if="!value.frozen.length" class="cutting-no-records">本月暂无当前权限可查看的冻结版本。</p>
      </SectionPanel>
      <SectionPanel v-if="exportsOnly&&access?.permissions.includes('payment_read')" title="付款登记与当前未付余额" class="cutting-content-panel">
        <p>此表按当前全量有效付款及余额导出，不作为历史时点冻结余额。单笔历史付款请在上方查看原版本。</p>
        <CuttingReportExport :selection="{kind:'payments',month:value.month}" :access="access" />
      </SectionPanel>
    </template>
  </div>
</template>
