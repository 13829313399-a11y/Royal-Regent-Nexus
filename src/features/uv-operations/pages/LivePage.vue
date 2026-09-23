<script setup lang="ts">
import { computed, ref } from 'vue'
import { Activity, ArrowRight, CircleDot, Clock3, Printer, RefreshCw, Radio, ShieldCheck } from '@lucide/vue'
import { displayTime, label, num, str, UV_BASE, type Entity } from '../contracts'
import { useUvWorkspace } from '../workspace'
import UvState from '../components/UvState.vue'
import RunMatchDialog from '../components/RunMatchDialog.vue'
const w=useUvWorkspace(), matching=ref<Entity|null>(null)
const machines=computed(()=>w.liveData.value.machines??[]), runs=computed(()=>w.liveData.value.runs??[])
const unmatched=computed(()=>runs.value.filter(row=>!row.match_evidence))
const activeShifts=computed(()=>(w.liveData.value.shifts??[]).filter(row=>row.status==='open'))
function current(machine:Entity) {return runs.value.find(row=>row.machine_id===machine.id&&row.state==='running')}
function next(machine:Entity) {return (w.liveData.value.schedule??[]).filter(row=>row.machine_id===machine.id&&row.status==='planned'&&String(row.end_at)>new Date().toISOString()).sort((a,b)=>String(a.start_at).localeCompare(String(b.start_at)))[0]}
function taskTitle(id:unknown) {const task=(w.liveData.value.tasks??[]).find(row=>row.id===id);return task?str(task,'code'):String(id??'尚未分配')}
function select(machine:Entity) {const block=next(machine);if(block) w.selectedTaskId.value=String(block.task_id)}
</script>
<template>
  <div class="uv-page-heading"><div><span class="uv-eyebrow">LIVE WORKSPACE · 华康 A</span><h2>生产现场</h2><p>掌握机台运行，及时核对每一笔产出。</p></div><button class="uv-button" :disabled="w.refreshing.value" @click="w.refresh"><RefreshCw :size="16"/>刷新现场</button></div>
  <div class="uv-live-summary"><div><Radio :size="18"/><span>采集正常</span><strong>{{machines.filter(row=>row.collection_health==='fresh').length}}<small> / {{machines.length}} 台</small></strong></div><div><CircleDot :size="18"/><span><RouterLink class="uv-link" :to="{path:UV_BASE+'/shifts',query:{factory:'huakang-a',tab:'runs'}}">待匹配运行 →</RouterLink></span><strong>{{w.meta.value?.coverage.unmatched_runs??'—'}}</strong></div><div><ShieldCheck :size="18"/><span><RouterLink class="uv-link" :to="{path:UV_BASE+'/shifts',query:{factory:'huakang-a',tab:'quality'}}">待检件数 →</RouterLink></span><strong>{{w.meta.value?.coverage.unconfirmed_output??'—'}}<small> pcs</small></strong></div><div><Clock3 :size="18"/><span>快照时间</span><strong class="uv-summary-time">{{displayTime(w.meta.value?.as_of)}}</strong></div></div>
  <section class="uv-section"><div class="uv-section-heading"><h3><Activity :size="18"/>机台运行</h3><span class="uv-muted">采集健康与设备状态分别显示</span></div>
    <div v-if="machines.length" class="uv-machine-list"><article v-for="machine in machines" :key="machine.id" class="uv-machine-lane">
      <div class="uv-machine-identity"><span class="uv-machine-icon"><Printer :size="32" stroke-width="1.3"/></span><div><span class="uv-eyebrow">{{str(machine,'code')}}</span><h3>{{str(machine,'name')}}</h3><span class="uv-badge" :data-state="machine.collection_health"><span class="uv-status-dot"/>{{label(machine.collection_health)}}</span></div></div>
      <div class="uv-machine-job"><div class="uv-lane-label"><span>当前运行证据</span><span class="uv-badge" :data-state="machine.work_state">{{label(machine.work_state)}}</span></div><strong>{{current(machine)?str(current(machine),'native_job_id'):'等待有效运行证据'}}</strong><p>{{current(machine)?'设备运行记录待人工核数，未折算为良品':'当前来源未提供已验证的打印进度'}}</p><div class="uv-unknown-progress"><span/>进度未知</div><small>{{label(machine.source_type)}} · 采集于 {{displayTime(machine.observed_at)}}</small></div>
      <div class="uv-machine-next"><span class="uv-lane-label">接下来 · 计划</span><button v-if="next(machine)" class="uv-task-title" @click="select(machine)">{{taskTitle(next(machine)?.task_id)}}<ArrowRight :size="15"/></button><span v-else class="uv-muted">暂无后续排程</span><small v-if="next(machine)">{{displayTime(next(machine)?.start_at)}}</small><RouterLink class="uv-link" :to="{path:UV_BASE+'/planning',query:{factory:'huakang-a'}}">查看排程</RouterLink></div>
    </article></div>
    <UvState v-else title="从第一台机台开始" description="在基础设置中录入机台能力，并为现场代理绑定采集源。"><RouterLink class="uv-button primary" :to="{path:UV_BASE+'/settings',query:{factory:'huakang-a'}}">配置机台与采集源<ArrowRight :size="16"/></RouterLink></UvState>
  </section>
  <div class="uv-two-column"><section class="uv-section"><div class="uv-section-heading"><h3>待核对运行</h3><span class="uv-count">{{w.meta.value?.coverage.unmatched_runs??'—'}}</span></div><p class="uv-section-description">核对原始作业与任务归属，再到班次页面确认产量。</p><div v-for="run in unmatched.slice(0,6)" :key="run.id" class="uv-list-row"><div><strong>{{str(run,'native_job_id')}}</strong><small>{{displayTime(run.started_at)}} · {{label(run.state)}}</small></div><button class="uv-button" :disabled="!w.can('production_write')" @click="matching=run">核对归属</button></div><p v-if="!unmatched.length" class="uv-empty-inline">当前快照中没有待匹配运行。</p><RouterLink class="uv-link uv-panel-link" :to="{path:UV_BASE+'/shifts',query:{factory:'huakang-a'}}">全部运行与核数<ArrowRight :size="15"/></RouterLink></section>
  <section class="uv-section"><div class="uv-section-heading"><h3>当班核数</h3><span class="uv-badge">{{activeShifts.length}} 个未结班</span></div><div v-for="shift in activeShifts.slice(0,4)" :key="shift.id" class="uv-list-row"><div><strong>{{str(shift,'name')}}</strong><small>{{str(shift,'business_date')}} · {{displayTime(shift.start_at)}} — {{displayTime(shift.end_at)}}</small></div><RouterLink class="uv-button" :to="{path:UV_BASE+'/shifts',query:{factory:'huakang-a',shift:shift.id}}">继续核数</RouterLink></div><p v-if="!activeShifts.length" class="uv-empty-inline">暂无进行中的班次。</p><div class="uv-inline-note"><ShieldCheck :size="18"/>良品以已确认核数为准，自动采集不会代替报产。</div></section></div>
  <RunMatchDialog :run="matching" @close="matching=null" @saved="matching=null;w.refresh()"/>
</template>
