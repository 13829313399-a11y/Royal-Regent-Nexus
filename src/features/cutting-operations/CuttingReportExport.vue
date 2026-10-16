<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
import { cuttingApi, errorMessage, type Access } from './api'
import { exportApi, saveReport, type ReportPreview, type ReportSelection } from './exportApi'

const props=defineProps<{selection:ReportSelection;access?:Access;disabled?:boolean}>()
const preview=ref<ReportPreview>(),busy=ref(false),error=ref(''),notice=ref('')
const permission=computed(()=>({period:'cost_read',settlement:'settlement_read',payments:'payment_read'})[props.selection.kind])
const allowed=computed(()=>!!props.access?.enabled&&props.access.permissions.includes(permission.value))
let generation=0,alive=true,controller:AbortController|undefined
function clear(){generation++;controller?.abort();preview.value=undefined;error.value='';notice.value='';busy.value=false}
watch(()=>JSON.stringify([props.selection,props.access,props.disabled]),clear)
window.addEventListener('auth-session-boundary-changed',clear)
onBeforeUnmount(()=>{alive=false;clear();window.removeEventListener('auth-session-boundary-changed',clear)})
async function run(download=false){
  if(!allowed.value||props.disabled||busy.value||(download&&!preview.value))return
  const selection={...props.selection},token=preview.value?.token,ticket=++generation,auth=getAuthenticationGeneration()
  controller=new AbortController();busy.value=true;error.value='';notice.value=''
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
      saveReport(blob,selection,token!);notice.value='报表已下载；历史冻结金额保持原版本，当前有效状态见报表说明。'
    }else{
      const value=await exportApi.preview(selection,controller.signal)
      if(valid())preview.value=value
    }
  }catch(e){if(valid()){preview.value=undefined;error.value=e instanceof Error&&!('response' in e)?e.message:errorMessage(e)}}
  finally{if(alive&&ticket===generation)busy.value=false}
}
</script>

<template>
  <section v-if="allowed" class="cutting-notice cutting-report-export" aria-label="月结报表导出">
    <Button variant="outline" :disabled="disabled||busy" @click="run()">{{busy?'正在准备报表…':'预览 Excel 导出'}}</Button>
    <p v-if="error" role="alert" class="cutting-error">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
    <template v-if="preview">
      <h3>{{preview.title}}</h3>
      <p v-for="[key,value] in preview.metadata.filter(([key])=>['使用状态','口径','统计截止日期','版本','当前状态','金额规则'].includes(key))" :key="key">{{key}}：{{value}}</p>
      <p>整份报表导出，不受页面明细筛选影响。金额保留精确文本，各币种分别汇总。</p>
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
