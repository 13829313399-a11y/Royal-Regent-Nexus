<script setup lang="ts">
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import EntryForm from '../components/EntryForm.vue'
import SharedResources from '../components/SharedResources.vue'
import { useSprayWorkspace, capabilities, localDate, str } from '../workspace'
const s=useSprayWorkspace(), adding=ref(false)
async function save(v:Record<string,string>) { const result=await s.command('resources',{...v,workers:Number(v.workers),calendar:[{start:v.start_at+'+08:00',end:v.end_at+'+08:00'}]}); if(result) adding.value=false }
</script>
<template><div class="spray-toolbar"><div><h2>资料中心</h2><p>配置本厂真实资源与可用班次。工艺随工单部件保存。</p></div><Button v-if="s.can('master_write')" @click="adding=!adding">新增资源</Button></div>
  <section v-if="adding" class="spray-panel"><EntryForm :fields="[{key:'name',label:'机台/工位/班组名称'},{key:'capability',label:'能力',options:capabilities},{key:'workers',label:'独立资源配备人数',type:'decimal'},{key:'machine_rate',label:'设备件数/小时',type:'decimal',optional:true},{key:'person_minutes',label:'每件人员分钟',type:'decimal',optional:true},{key:'setup_hours',label:'准备占用小时',value:'0',type:'decimal'},{key:'start_at',label:'可用班次开始',type:'datetime-local',value:localDate()+'T08:00'},{key:'end_at',label:'可用班次结束',type:'datetime-local',value:localDate()+'T20:00'}]" :busy="s.busy" submit-label="保存资源及班次" @submit="save" /><p class="spray-help">人数应属于此独立班组；共享人员及工装请在下方配置。未知节拍留空，排产时填写确认工时。</p></section>
  <div class="spray-table-wrap"><table class="spray-table"><thead><tr><th>资源</th><th>能力</th><th>人数</th><th>设备件/小时</th><th>人员分钟/件</th><th>班次配置</th></tr></thead><tbody><tr v-for="r in s.items('resources')" :key="r.id"><td><strong>{{ r.name }}</strong></td><td>{{ capabilities.find(v=>v.value===r.capability)?.label }}</td><td>{{ r.workers }}</td><td>{{ r.machine_rate ?? '未确认' }}</td><td>{{ r.person_minutes ?? '未确认' }}</td><td>{{ Array.isArray(r.calendar) ? r.calendar.length : 0 }} 个时段</td></tr></tbody></table></div><p v-if="!s.items('resources').length" class="spray-empty">没有配置资源；不会自动建立 6 条线或 UV 设备。</p>
  <SharedResources /><section class="spray-panel mt-5"><h3 class="font-semibold">部件工艺资料</h3><div v-for="line in s.items('lines')" :key="line.id" class="spray-row"><strong>{{ s.lineLabel(line) }}</strong><span>{{ s.items('steps').filter(v=>v.line_id===line.id).map(v=>str(v,'name')).join(' → ') }}</span></div></section>
</template>
