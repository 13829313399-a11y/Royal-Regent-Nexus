<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
import { cuttingApi, errorMessage, type Access } from './api'
import { exportApi, saveReport, type ReportPreview, type ReportSelection } from './exportApi'

const props=defineProps<{selection:ReportSelection;access?:Access;disabled?:boolean}>()
const preview=ref<ReportPreview>(),busy=ref(false),error=ref(''),notice=ref('')
const phase=ref<'preview'|'download'>('preview'),elapsed=ref(0)
const permission=computed(()=>({period:'cost_read',settlement:'settlement_read',payments:'payment_read'})[props.selection.kind])
const allowed=computed(()=>!!props.access?.enabled&&props.access.permissions.includes(permission.value))
let generation=0,alive=true,controller:AbortController|undefined
let clock:ReturnType<typeof setInterval>|undefined
function stopClock(){if(clock!==undefined)clearInterval(clock);clock=undefined}
function clear(){generation++;controller?.abort();stopClock();preview.value=undefined;error.value='';notice.value='';busy.value=false}
function cancel(){clear();notice.value='已取消本次报表等待，未发起文件下载。后台生成可能仍会短暂运行；再次导出请重新预览。'}
watch(()=>JSON.stringify([props.selection,props.access,props.disabled]),clear)
window.addEventListener('auth-session-boundary-changed',clear)
onBeforeUnmount(()=>{alive=false;clear();window.removeEventListener('auth-session-boundary-changed',clear)})
async function run(download=false){
  if(!allowed.value||props.disabled||busy.value||(download&&!preview.value))return
  const selection={...props.selection},token=preview.value?.token,ticket=++generation,auth=getAuthenticationGeneration()
  controller=new AbortController();busy.value=true;error.value='';notice.value='';phase.value=download?'download':'preview';elapsed.value=0
  const started=Date.now();stopClock();clock=setInterval(()=>{elapsed.value=Math.floor((Date.now()-started)/1000)},1000)
  const valid=()=>alive&&ticket===generation&&auth===getAuthenticationGeneration()&&allowed.value&&!props.disabled
  try{
    const access=await cuttingApi.access()
    if(!valid())return
    if(!access.enabled||!access.permissions.includes(permission.value))throw new Error('报表查询权限已变化，请重新读取页面。')
    if(download){
      const blob=await exportApi.download(selection,token!,controller.signal)
      if(!valid())return
      const current=await cuttingApi.access()
      if(!valid())return
      if(!current.enabled||!current.permissions.includes(permission.value))throw new Error('报表查询权限已撤销，文件未下载。')
      saveReport(blob,selection,token!);notice.value=selection.kind==='payments'
        ?'付款报表已生成并发起下载；登记按所选付款月份，余额为本次导出时的当前全期余额，并非历史月末冻结余额。'
        :'报表已生成并发起下载；金额按所选冻结版本，当前有效状态见报表说明。'
    }else{
      const value=await exportApi.preview(selection,controller.signal)
      if(valid())preview.value=value
    }
  }catch(e){if(valid()){preview.value=undefined;error.value=e instanceof Error&&!('response' in e)?e.message:errorMessage(e)}}
  finally{if(alive&&ticket===generation){busy.value=false;stopClock()}}
}
</script>

<template>
  <section v-if="allowed" class="cutting-notice cutting-report-export" aria-label="月结报表导出">
    <Button variant="outline" :disabled="disabled||busy" @click="run()">{{busy?(phase==='preview'?'正在预览报表…':'正在下载报表…'):'预览 Excel 导出'}}</Button>
    <p v-if="busy" role="status">{{phase==='preview'?'正在核对报表内容':'正在等待完整报表文件'}}，已等待 {{elapsed}} 秒。集中导出可能需要排队，请勿重复提交。</p>
    <Button v-if="busy" variant="outline" @click="cancel">取消本次等待</Button>
    <p v-if="error" role="alert" class="cutting-error">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
    <template v-if="preview">
      <h3>{{preview.title}}</h3>
      <p v-for="[key,value] in preview.metadata.filter(([key])=>['使用状态','口径','统计截止日期','版本','当前状态','金额规则'].includes(key))" :key="key">{{key}}：{{value}}</p>
      <p>整份报表导出，不受页面明细筛选影响。金额保留精确文本，各币种分别汇总。</p>
      <p v-if="selection.kind==='payments'">付款登记按所选付款月份列示；余额为本次导出时的当前全期余额，不是所选月份的历史月末冻结余额。</p>
      <p>{{preview.sheets.map(sheet=>`${sheet.name} ${sheet.rows} 行`).join('；')}}</p>
      <p v-if="preview.delivery">共 {{preview.delivery.volumes}} 卷；{{preview.delivery.format==='zip'?'一次下载压缩包，请解压并保留全部 Excel 文件及清单。':'下载完整 Excel 文件。'}} 每卷附完整性清单，明细连续分卷、不重复。</p>
      <p>首卷含打印摘要；宽明细按原字号横向分页。长凭据请在电子文件中查看。</p>
      <Button :disabled="disabled||busy" @click="run(true)">{{preview.delivery?.format==='zip'?'确认下载压缩包':'确认下载 Excel'}}</Button>
    </template>
  </section>
</template>

<style scoped>
.cutting-report-export {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.75rem;
  min-width: 0;
}
.cutting-report-export > button { align-self: flex-start; }
.cutting-report-export > h3,
.cutting-report-export > p { margin: 0; min-width: 0; line-height: 1.65; overflow-wrap: anywhere; }
</style>
