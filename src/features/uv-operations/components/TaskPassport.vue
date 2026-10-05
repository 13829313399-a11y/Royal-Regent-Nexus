<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { X, FileCheck, ArrowUpRight, Layers3, Printer } from '@lucide/vue'
import { useUvWorkspace } from '../workspace'
import { displayTime, entities, label, num, object, str, UV_BASE, type Entity } from '../contracts'
import UvState from './UvState.vue'
const w=useUvWorkspace(), task=ref<Entity|null>(null), tab=ref('资料'), loading=ref(false), error=ref('')
const panel=ref<HTMLElement>()
let previousFocus:HTMLElement|null=null
watch(w.selectedTaskId,async (id,previous)=>{if(id&&!previous){previousFocus=document.activeElement as HTMLElement;await nextTick();panel.value?.focus()}else if(!id){previousFocus?.focus()} })
let requestVersion=0
watch(w.selectedTaskId,async id=>{task.value=null;error.value='';const version=++requestVersion;if(!id)return;loading.value=true;try{const response=await w.request<Entity>('tasks/'+id);if(version===requestVersion)task.value=response.data}catch(cause){error.value=w.explain(cause)}finally{if(version===requestVersion)loading.value=false}})
const process=computed(()=>object(task.value?.process_snapshot))
const batches=computed(()=>entities(task.value?.batches))
const steps=['资料','排程','执行','核数','交接']
const current=computed(()=>batches.value.length&&batches.value.every(row=>num(row,'received')===num(row,'good')&&num(row,'good')>0)&&task.value?.status==='completed'?4:task.value?.status==='completed'?3:task.value?.status==='in_progress'?2:task.value?.status==='planned'?1:0)
</script>
<template>
  <aside v-if="w.selectedTaskId.value" ref="panel" tabindex="-1" class="uv-passport" aria-label="任务档案" @keydown.esc="w.selectedTaskId.value=null">
    <header><div><span class="uv-context">任务档案</span><h2>{{task?str(task,'code'):'正在读取…'}}</h2></div><button class="uv-icon-button" aria-label="关闭任务档案" @click="w.selectedTaskId.value=null"><X :size="20"/></button></header>
    <UvState v-if="loading" kind="loading" title="读取任务档案"/><UvState v-else-if="error" kind="error" :title="error"/>
    <template v-else-if="task">
      <ol class="uv-stepper"><li v-for="(step,index) in steps" :key="step" :data-complete="index<=current"><span>{{index+1}}</span>{{step}}</li></ol>
      <div class="uv-passport-title"><div class="uv-preview-icon"><img v-if="task.preview_file_id" :src="'/api/uv-operations/files/'+task.preview_file_id+'/download?factory_id=huakang-a'" alt="当前工艺预览"/><Printer v-else :size="30"/></div><div><h3>{{str(task,'product_snapshot')}}</h3><span class="uv-badge" :data-state="task.status">{{label(task.status)}}</span></div></div>
      <div class="uv-tabs" role="tablist" aria-label="任务档案栏目"><button v-for="name in ['资料','运行','品质','核算']" :key="name" :aria-selected="tab===name" role="tab" @click="tab=name">{{name}}</button></div>
      <div class="uv-passport-body">
        <template v-if="tab==='资料'"><dl class="uv-definition"><dt>需求编号</dt><dd>{{str(task,'demand_code')}}</dd><dt>计划数量</dt><dd>{{task.quantity}} pcs</dd><dt>工艺版本</dt><dd>{{str(process,'name')}} · V{{process.revision}}</dd><dt>每板件数</dt><dd>{{process.pieces_per_board}} pcs</dd><dt>工序遍数</dt><dd>{{process.passes}}</dd><dt>墨材型号</dt><dd>{{process.ink_family}}</dd><dt>创建时间</dt><dd>{{displayTime(task.created_at)}}</dd></dl><a class="uv-file-link" :href="'/api/uv-operations/files/'+task.file_version_id+'/download?factory_id=huakang-a'"><FileCheck :size="19"/><span>已确认生产文件<br><small>下载原始版本 · 不向打印机发送</small></span><ArrowUpRight :size="16"/></a></template>
        <template v-else-if="tab==='运行'"><p class="uv-notice">原始运行记录与人工核数分别保留。采集完成不等于良品完成。</p><div v-for="row in entities(task.run_allocations)" :key="row.id" class="uv-detail-row"><Layers3 :size="18"/><span>运行 {{str(row,'run_id').slice(0,8)}}<small>第 {{row.pass_index}} 遍 · {{row.full_boards}} 整板 + {{row.tail_pieces}} 尾板件</small></span></div><p v-if="!entities(task.run_allocations).length" class="uv-muted">尚无已确认的运行分配。</p><h4>参与记录</h4><div v-for="row in entities(task.participations)" :key="row.id" class="uv-detail-row">{{row.employee_name}}<small>{{displayTime(row.start_at)}}–{{displayTime(row.end_at)}}</small></div></template>
        <template v-else-if="tab==='品质'"><div v-for="batch in batches" :key="batch.id" class="uv-batch-detail"><h4>批次 {{batch.id.slice(0,8)}} · 第 {{batch.pass_index}} 遍</h4><dl class="uv-definition"><dt>实体总数</dt><dd>{{batch.quantity}} pcs</dd><dt>最终良品</dt><dd>{{batch.good}} pcs</dd><dt>待返工 / 待检</dt><dd>{{batch.rework}} / {{batch.pending}}</dd><dt>报废 / 中间合格</dt><dd>{{batch.scrap}} / {{batch.intermediate}}</dd><dt>已签收 / 预留</dt><dd>{{batch.received}} / {{batch.reserved}}</dd></dl></div><h4>批次流转</h4><div v-for="edge in entities(task.batch_relations)" :key="edge.id" class="uv-detail-row"><span>{{edge.kind==='split'?'拆分':'合并'}} {{str(edge,'source_id').slice(0,8)}} → {{str(edge,'target_id').slice(0,8)}}<small>{{edge.quantity}} pcs · {{displayTime(edge.created_at)}}</small></span></div><p v-if="!entities(task.batch_relations).length" class="uv-muted">原始批次，尚无拆分或合并。</p><h4>报产依据</h4><div v-for="entry in entities(task.production)" :key="entry.id" class="uv-detail-row"><span>{{entry.evidence}}<small>{{entry.business_date}} · {{num(entry,'direction')<0?'冲销':'确认'}} {{entry.processed}} pcs</small></span></div></template>
        <template v-else><div v-if="w.can('cost_read')"><h4>冻结价格</h4><dl v-if="task.cost_price_snapshot" class="uv-definition"><dt>单位价格</dt><dd>{{object(task.cost_price_snapshot).rate}} {{object(task.cost_price_snapshot).currency}}</dd><dt>口径</dt><dd>{{object(task.cost_price_snapshot).basis==='piece'?'最终良品件数':'最终良品面积'}}</dd><dt>依据</dt><dd>{{object(task.cost_price_snapshot).evidence}}</dd></dl><p v-else class="uv-notice">任务创建时未确认价格，核算资料不完整。</p></div><div v-if="w.can('payroll_read')"><h4>冻结工资规则</h4><p>{{task.payroll_policy_snapshot?str(object(task.payroll_policy_snapshot),'name'):'未设置，不能核准正式工资'}}</p></div><UvState v-if="!w.can('cost_read')&&!w.can('payroll_read')" kind="denied" title="未获核算查看权限" description="金额和工资字段未从服务器返回。"/></template>
      </div>
      <footer><RouterLink class="uv-button primary" :to="{path:UV_BASE+'/shifts',query:{factory:'huakang-a',task:task.id}}" @click="w.selectedTaskId.value=null">前往班次核数 <ArrowUpRight :size="16"/></RouterLink></footer>
    </template>
  </aside>
</template>
