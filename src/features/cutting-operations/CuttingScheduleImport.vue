<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { RouterLink } from 'vue-router'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { errorMessage } from './api'
import { CUTTING_FACTORY } from './navigation'
import { scheduleImportApi, type SchedulePreview, type ScheduleCommand, type ScheduleResult } from './scheduleImportApi'
const emit=defineEmits<{imported:[]}>()
const id=`cutting-schedule-${useId()}`,open=ref(false),file=ref<File>(),preview=ref<SchedulePreview>(),result=ref<ScheduleResult>()
const reason=ref(''),confirmed=ref(false),busy=ref(false),error=ref(''),pending=ref<{file:File;command:ScheduleCommand}>(),uncertain=ref(false)
const fileInput=ref<HTMLInputElement>()
const labels={new:'可导入',duplicate:'已存在，跳过',conflict:'已有订单冲突',invalid:'需修正'}
const sheetsReady=computed(()=>!!preview.value?.sheets?.length&&preview.value.sheets.every(sheet=>sheet.status==='ready'||sheet.status==='empty'))
const ready=computed(()=>file.value&&preview.value?.can_confirm&&sheetsReady.value&&confirmed.value&&reason.value.trim().length>=4)
let alive=true,generation=0
function discard(){
  if(busy.value||pending.value){error.value='导入结果尚未确认，请先重试原操作或恢复核对。';return false}
  return !file.value||window.confirm('有尚未导入的文件，离开将放弃本次预览。确定继续？')
}
defineExpose({discard})
function unload(e:BeforeUnloadEvent){if(file.value||pending.value||busy.value){e.preventDefault();e.returnValue=''}}
onMounted(()=>window.addEventListener('beforeunload',unload))
onBeforeUnmount(()=>{alive=false;generation++;window.removeEventListener('beforeunload',unload)})
function choose(event:Event){
  generation++;file.value=(event.target as HTMLInputElement).files?.[0];preview.value=undefined;result.value=undefined;confirmed.value=false;error.value=''
  if(file.value&&(!file.value.name.toLowerCase().endsWith('.xlsx')||file.value.size>10*1024*1024)){file.value=undefined;error.value='请选择不超过 10 MB 的 .xlsx 文件。'}
}
async function read(){
  if(!file.value||pending.value)return
  const ticket=++generation,source=file.value;busy.value=true;error.value='';preview.value=undefined;confirmed.value=false
  try{const r=await scheduleImportApi.preview(source);if(alive&&ticket===generation)preview.value=r}
  catch(e){if(alive&&ticket===generation)error.value=errorMessage(e)}
  finally{if(alive&&ticket===generation)busy.value=false}
}
function complete(r:ScheduleResult){result.value=r;pending.value=undefined;uncertain.value=false;file.value=undefined;preview.value=undefined;reason.value='';confirmed.value=false;busy.value=false;if(fileInput.value)fileInput.value.value='';emit('imported')}
function invalidatePreview(){preview.value=undefined;confirmed.value=false}
async function submit(){
  if(!pending.value){
    if(!ready.value||!file.value||!preview.value)return
    pending.value={file:file.value,command:{factory_id:CUTTING_FACTORY,operation_id:crypto.randomUUID(),expected_version:0,reason:reason.value.trim(),fingerprint:preview.value.fingerprint,file_sha256:preview.value.file_sha256,file_name:preview.value.file_name,confirmed:true}}
  }
  busy.value=true;error.value=''
  try{const r=await scheduleImportApi.confirm(pending.value.file,pending.value.command);if(alive)complete(r)}
  catch(e){if(alive){error.value=errorMessage(e);const status=(e as {response?:{status:number}}).response?.status
    if(uncertain.value||!status||status>=500){uncertain.value=true;error.value+=' 结果尚未确认，请保留原请求并重试或恢复核对。'}
    else{pending.value=undefined;invalidatePreview();error.value+=' 原预览已失效，请重新读取预览并重新勾选确认。'}
  }}finally{if(alive)busy.value=false}
}
async function recover(){
  if(!pending.value)return
  busy.value=true;error.value=''
  try{const r=await scheduleImportApi.recover(pending.value.command);if(alive){if(r.state==='committed')complete(r.result);else{pending.value=undefined;uncertain.value=false;invalidatePreview();error.value='原操作未执行，已安全终止。请重新预览并勾选确认后导入。'}}}
  catch(e){if(alive)error.value=errorMessage(e)}finally{if(alive)busy.value=false}
}
async function download(){
  busy.value=true;error.value=''
  try{const blob=await scheduleImportApi.template();if(!alive)return;const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='裁床排期导入模板.xlsx';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
  catch(e){if(alive)error.value=errorMessage(e)}finally{if(alive)busy.value=false}
}
function close(){if(discard()){open.value=false;file.value=undefined;preview.value=undefined;error.value='';reason.value='';confirmed.value=false}}
</script>
<template>
  <SectionPanel title="业务排期 Excel 导入" subtitle="按排期原行建立可追溯订单来源，确认导入时首次下发并自动接单。" class="cutting-content-panel">
    <template #action><Button v-if="!open" type="button" variant="outline" @click="open=true">排期 Excel 导入</Button><Button v-else type="button" variant="outline" :disabled="busy||!!pending" @click="close">收起导入</Button></template>
    <p class="schedule-note">导入预览 → 确认导入并自动接单 → 工程关联 BOM → 发布任务 → 物料库存提交领料 → 布料仓核对发料 → 裁床签收物料。</p>
    <div v-if="open" class="schedule-intake">
      <p class="schedule-note">仅接收本厂客户的 .xlsx，单批最多 500 行。请按模板整理七列，单位须明确；首批不生成采购、成本或月结。可先发布任务而不排日计划，待实际领料后再核定日期。</p>
      <div class="schedule-toolbar"><Button type="button" variant="outline" :disabled="busy||!!pending" @click="download">下载导入模板</Button></div>
      <label :for="`${id}-file`">业务排期 Excel<input ref="fileInput" :id="`${id}-file`" name="cutting_schedule_file" type="file" accept=".xlsx" :disabled="busy||!!pending" @change="choose" /></label>
      <Button type="button" :disabled="!file||busy||!!pending" @click="read">{{busy&&!pending?'正在读取…':'读取导入预览'}}</Button>
      <p v-if="error" role="alert" class="cutting-error">{{error}}</p>
      <p v-if="busy" role="status">{{pending?'正在核对原导入操作，请勿重复建单或关闭页面。':'正在读取，请稍候。'}}</p>
      <template v-if="preview">
        <p role="status">{{preview.file_name}} · 共 {{preview.rows.length}} 行 · 可新增 {{preview.new_count}} 行 · 已存在 {{preview.duplicate_count}} 行</p>
        <div v-if="preview.sheets?.length" class="schedule-coverage" role="region" aria-label="工作表核对结果">
          <h3>工作表核对结果 · 共 {{preview.sheets.length}} 张</h3>
          <ul><li v-for="sheet in preview.sheets" :key="sheet.sheet"><strong>{{sheet.sheet}}</strong> · {{sheet.status==='ready'?`已读取 ${sheet.row_count} 行`:sheet.status==='empty'?'空表，无需导入':'未读取，需处理'}}<p :class="{'cutting-error':sheet.status==='blocked'}">{{sheet.message}}</p></li></ul>
        </div>
        <p v-else role="alert" class="cutting-error">当前服务未提供工作表核对结果，不能确认导入，请联系管理员更新服务后重新预览。</p>
        <div class="cutting-table-scroll" role="region" aria-label="排期导入预览，可横向滚动" tabindex="0"><table>
          <thead><tr><th>来源行</th><th>客户</th><th>订单号／货号</th><th>货名</th><th>数量／单位</th><th>交期</th><th>校验结果</th></tr></thead>
          <tbody><tr v-for="r in preview.rows" :key="`${r.sheet}-${r.row}`"><td>{{r.sheet}} · {{r.row}}</td><td>{{r.data.customer_name}}</td><td>{{r.data.reference_no}}<br>{{r.data.product_no}}</td><td>{{r.data.product_name_zh}}</td><td>{{r.data.quantity}} {{r.data.unit}}</td><td>{{r.data.requested_ship_date}}</td><td><StatusPill :label="labels[r.status]" compact/><p v-for="message in r.errors" :key="message">{{message}}</p></td></tr></tbody>
        </table></div>
        <p v-if="!preview.can_confirm||!sheetsReady" class="cutting-error">请先修正未读取的工作表、文件错误或已有订单冲突，再重新预览；本批不能确认，不会覆盖原订单。</p>
        <label :for="`${id}-reason`">核对说明<textarea :id="`${id}-reason`" name="cutting_schedule_reason" v-model="reason" rows="2" maxlength="500" :disabled="busy||!!pending" placeholder="至少四字，说明排期来源及本批核对依据" /></label>
        <label class="schedule-check" :for="`${id}-confirmed`"><input :id="`${id}-confirmed`" name="cutting_schedule_confirmed" type="checkbox" v-model="confirmed" :disabled="busy||!!pending" />已核对客户、订单、数量、单位和交期；这不是生产完成或库存入库。</label>
        <Button v-if="!pending" type="button" :disabled="!ready||busy" @click="submit">确认导入并自动接单</Button>
      </template>
      <div v-if="pending" class="schedule-toolbar"><Button type="button" :disabled="busy" @click="submit">重试原导入</Button><Button type="button" variant="outline" :disabled="busy" @click="recover">恢复核对原操作</Button></div>
      <div v-if="result" role="status" class="cutting-notice"><p>导入完成：新增并自动接单 {{result.created}} 条，已存在跳过 {{result.skipped}} 条。原文件和来源行已留存，请继续关联 BOM 和发布任务。</p><details><summary>导入批次与订单</summary><p class="schedule-id">{{result.batch_id}}</p><ul><li v-for="r in result.rows" :key="`${r.sheet}-${r.row}`"><RouterLink :to="{path:'/modules/production/cutting/planning',query:{factory:CUTTING_FACTORY,line_id:r.line_id}}">{{r.reference_no}}／{{r.product_no}} · 来源 {{r.sheet}} 第 {{r.row}} 行 · V{{r.version}}</RouterLink></li></ul></details></div>
    </div>
  </SectionPanel>
</template>
<style scoped>
.schedule-intake{display:grid;gap:16px;margin-top:16px}.schedule-intake label{display:grid;gap:8px;font-size:14px}.schedule-intake :is(input[type=file],textarea){max-width:100%;width:100%;border:1px solid var(--border);border-radius:var(--radius-md);padding:10px;background:var(--background)}.schedule-intake .schedule-check{display:flex;align-items:flex-start;gap:10px}.schedule-check input{margin-top:4px;flex:none}.schedule-note{font-size:13px;color:var(--muted-foreground);line-height:1.8}.schedule-toolbar{display:flex;flex-wrap:wrap;gap:10px}.schedule-intake td{padding:14px 20px;text-align:center;border-bottom:1px solid var(--border);min-width:110px}.schedule-intake td:last-child{min-width:200px}.schedule-id{overflow-wrap:anywhere}.schedule-intake a{color:var(--primary);text-decoration:underline}.schedule-intake li{padding:6px 0}.schedule-intake button{justify-self:start}
</style>
