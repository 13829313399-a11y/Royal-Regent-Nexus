<script setup lang="ts">
import { ref } from 'vue'
import { useSprayPage } from '../usePage'
import { dateTime, type Entity } from '../contracts'
import WorkspaceState from '../components/WorkspaceState.vue'
const w=useSprayPage(['activity']),page=ref(1)
const labels:Record<string,string>={resource:'资源',route:'工艺路线',employee:'员工',demand:'需求',batch:'来料',preparation:'生产准备',plan:'排期',task:'生产任务',report:'日报',quality:'质量处置',delivery:'交收',return:'实物退货',container:'周转容器',material:'材料',purchase:'采购',saving:'采购减价',rule:'业务规则',payroll:'工资',expense:'费用',valuation:'工序产值',settlement:'月结',credit:'贷项',period:'期间',import:'导入',export:'导出'}
const verbs:Record<string,string>={create:'登记',confirm:'确认',reverse:'冲回',preview:'预览',publish:'发布',start:'开工',receive:'收货',move:'流转',accept:'验收',dispatch:'发出',close:'锁定',reopen:'重开',trial:'试算',upload:'上传',amend:'变更',match:'匹配',price:'核价',cancel:'取消',calendar:'维护日历'}
function label(row:Entity){const [domain,verb]=String(row.action).split(':')[0]!.split('.');return `${labels[domain!]??'业务操作'} · ${verbs[verb!]??'确认'}`}
async function go(delta:number){page.value+=delta;await w.load(['activity'],{page:page.value})}
</script>
<template><div class="spray-page"><header class="spray-page-heading"><div><span class="spray-eyebrow">ACTIVITY / 操作记录</span><h1>每一次变更，都有来源</h1><p>记录当前执行工厂的保存回执、操作人和业务日期。</p></div></header><WorkspaceState/><section class="spray-panel"><div v-if="!w.items('activity').length" class="spray-empty">尚无操作记录</div><article v-for="row in w.items('activity')" :key="row.id" class="spray-activity-row"><span class="spray-activity-dot"/><div><strong>{{label(row)}}</strong><p class="spray-muted">业务日期 {{row.business_date??'—'}} · 操作人 {{row.actor_id}}</p><small>回执 {{row.operation_id}}</small></div><time>{{dateTime(row.created_at)}}</time></article></section><div class="spray-actions"><button class="spray-secondary" :disabled="page===1" @click="go(-1)">上一页</button><span class="spray-muted">第 {{page}} 页 · 共 {{w.totals.activity??0}} 条</span><button class="spray-secondary" :disabled="page*200>=(w.totals.activity??0)" @click="go(1)">下一页</button></div></div></template>
