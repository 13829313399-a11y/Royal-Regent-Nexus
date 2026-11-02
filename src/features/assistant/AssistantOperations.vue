<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { assistantApi } from './api'
import type { OperationalSummary } from './types'
const props=defineProps<{available:boolean}>()
const days=ref(7),summary=ref<OperationalSummary|null>(null),loading=ref(false),error=ref('')
const runId=ref(''),trace=ref<Record<string,unknown>|null>(null),traceLoading=ref(false),traceError=ref('')
let generation=0,traceGeneration=0,controller=new AbortController(),traceController=new AbortController()
const timingLabels:Record<string,string>={first_event_seconds:'首个运行事件',first_delta_seconds:'首个模型增量（含思考）',first_answer_seconds:'首段回答正文',elapsed_seconds:'运行总时长',upstream_close_after_cancel_seconds:'取消至上游关闭'}
const categories={factual:'事实错误',off_topic:'没回答问题',sources:'来源问题',experience:'体验问题'}
const count=(v:number|null|undefined)=>v==null?'尚未采集':String(v)
const seconds=(v:number|null)=>v==null?'样本不足或未测':`${v.toFixed(3)} 秒`
const ratioCounts=(v:OperationalSummary['no_source_ratio'])=>v?.denominator?`${v.numerator} / ${v.denominator}`:'暂无可测分母'
async function load() {
  if(!props.available)return
  const g=++generation;controller.abort();controller=new AbortController();loading.value=true;summary.value=null;error.value=''
  try{const value=await assistantApi.operations(days.value,controller.signal);if(g===generation)summary.value=value}
  catch(e){if(g===generation)error.value=e instanceof Error?e.message:'统计暂不可用。'}
  finally{if(g===generation)loading.value=false}
}
async function inspectRun() {
  if(!props.available||!runId.value.trim()||traceLoading.value)return
  if(!/^[A-Za-z0-9_-]{8,64}$/.test(runId.value.trim())){traceError.value='请输入有效的运行编号。';trace.value=null;return}
  const g=++traceGeneration;traceController.abort();traceController=new AbortController();traceLoading.value=true;trace.value=null;traceError.value=''
  try{const value=await assistantApi.operationsTrace(runId.value.trim(),traceController.signal);if(g===traceGeneration)trace.value=value}
  catch(e){if(g===traceGeneration)traceError.value=e instanceof Error?e.message:'诊断暂不可用。'}
  finally{if(g===traceGeneration)traceLoading.value=false}
}
watch(runId,()=>{traceGeneration++;traceController.abort();trace.value=null;traceError.value='';traceLoading.value=false})
watch(()=>props.available,()=>{generation++;traceGeneration++;controller.abort();traceController.abort();summary.value=null;trace.value=null;loading.value=false;traceLoading.value=false;error.value='';traceError.value=''})
onUnmounted(()=>{generation++;traceGeneration++;controller.abort();traceController.abort()})
</script>
<template>
  <section class="yl-operations" aria-label="管理员运行统计">
    <h4>管理员运行统计</h4><p>只统计执行元数据，不读取员工正文或反馈文字。旧记录缺少测量时保留未知，不补写零。</p>
    <p v-if="!available" role="status">运行统计尚未准备完成。</p>
    <template v-else><label>统计窗口<select v-model.number="days" @change="load"><option :value="1">最近 1 天</option><option :value="7">最近 7 天</option><option :value="30">最近 30 天</option></select></label><button type="button" :aria-busy="loading" @click="load">{{ loading?'读取统计中…':'读取运行统计' }}</button></template>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-if="summary"><p>最近 {{ summary.window_days }} 天 · 检查于 {{ new Date(summary.checked_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}) }}（北京时间）</p>
      <dl><dt>可引用来源登记项 / 全部来源登记项</dt><dd>{{ ratioCounts(summary.registered_source_ratio) }}</dd><dt>已定位引用 / 已登记引用</dt><dd>{{ ratioCounts(summary.citation_binding_ratio) }}；仅表示定位成功</dd><dt>无可引用来源运行 / 已测且终结运行</dt><dd>{{ ratioCounts(summary.no_source_ratio) }}；包含正常普通聊天，未测不计入</dd></dl>
      <dl><dt>保留的运行</dt><dd>{{ summary.runs }} 次；已采集 {{ summary.instrumented_runs }}，未采集 {{ summary.unmeasured_runs }}</dd><dt>进行中</dt><dd>{{ summary.active_runs }}</dd><dt>本轮业务查询</dt><dd>取得结果 {{ count(summary.counters.business_completed) }} / 尝试 {{ count(summary.counters.business_attempts) }}；权限错误 {{ count(summary.counters.business_permission_errors) }}</dd><dt>设备等来源时效</dt><dd>原查询标记过时 {{ count(summary.counters.freshness_stale) }}；时效未知 {{ count(summary.counters.freshness_unknown) }}</dd><dt>恢复订阅确认</dt><dd>{{ summary.recovery.client_confirmed_progress }} / {{ summary.recovery.after_seq_attempts }} 次收到客户端进度确认；缺确认 {{ summary.recovery.missing_client_receipt }} 次</dd><dt>反馈</dt><dd>{{ summary.feedback.total }} 条；<span v-for="(label,key) in categories" :key="key">{{ label }} {{ summary.feedback.categories[key] }} </span></dd></dl>
      <details><summary>耗时与统计口径</summary><dl><template v-for="(value,key) in summary.timings" :key="key"><dt>{{ timingLabels[key]||key }} · {{ value.samples }} 个样本</dt><dd>观测范围 {{ seconds(value.min) }} — {{ seconds(value.max) }}；p50 {{ seconds(value.p50) }}；p95 {{ seconds(value.p95) }}</dd></template></dl><p v-for="(text,key) in summary.definitions" :key="key">{{ text }}</p></details>
      <details><summary>分类计数</summary><pre tabindex="0">{{ JSON.stringify({states:summary.states,errors:summary.errors,usage:summary.usage_states,files:summary.files_current_parse_states},null,2) }}</pre></details>
    </div>
    <form v-if="available" @submit.prevent="inspectRun"><label>按运行编号定位<input v-model="runId" maxlength="64" aria-label="诊断运行编号" placeholder="粘贴报告中提供的运行编号"/></label><button :disabled="!runId.trim()||traceLoading" :aria-busy="traceLoading">{{ traceLoading?'读取诊断中…':'查看脱敏运行诊断' }}</button><p>仅返回耗时、错误、步骤编号和用量等元数据，不打开员工对话。</p></form>
    <p v-if="traceError" role="alert">{{ traceError }}</p><pre v-if="trace" tabindex="0" aria-label="脱敏运行诊断">{{ JSON.stringify(trace,null,2) }}</pre>
  </section>
</template>
<style scoped>
.yl-operations{margin-top:20px;padding-top:12px;border-top:1px solid var(--yl-line);min-width:0;overflow-wrap:anywhere}.yl-operations h4{font-size:14px;margin:0}.yl-operations p,.yl-operations dl{font-size:12px;line-height:1.65}.yl-operations dl{display:block}.yl-operations dt{font-weight:600;margin-top:10px}.yl-operations dd{margin:3px 0}.yl-operations label{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:12px;margin:8px 0}.yl-operations input,.yl-operations select{min-width:0;max-width:100%;min-height:40px;padding:7px;border:1px solid var(--yl-line);border-radius:8px;background:var(--yl-paper)}.yl-operations input{width:100%;box-sizing:border-box}.yl-operations button{min-height:40px;padding:8px 10px;border:1px solid var(--yl-line);border-radius:8px;color:var(--yl-deep);background:var(--yl-paper)}.yl-operations button:disabled{opacity:.55}.yl-operations summary{min-height:40px;padding:9px 0;font-size:12px;cursor:pointer}.yl-operations pre{max-height:260px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;padding:10px;font-size:11px;background:var(--yl-panel)}.yl-operations :focus-visible{outline:2px solid var(--yl-jade);outline-offset:2px}@media(max-width:767px){.yl-operations button,.yl-operations input,.yl-operations select{min-height:44px}}
</style>
