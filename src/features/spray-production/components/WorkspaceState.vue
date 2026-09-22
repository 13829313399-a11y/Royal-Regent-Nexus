<script setup lang="ts">
import { RefreshCw, CircleAlert } from '@lucide/vue'
import { useSprayWorkspace } from '../workspace'
import { useRoute, useRouter } from 'vue-router'
const w = useSprayWorkspace()
const route=useRoute(), router=useRouter()
function clearOrder(){const query={...route.query};delete query.demand;void router.push({path:route.path,query})}
const labels:Record<string,string>={stock:'库存',batches:'来料',tasks:'任务',reports:'日报',resources:'资源',routes:'工艺',employees:'员工',deliveries:'交收',returns:'退货',containers:'周转物',materials:'材料',purchases:'采购',rules:'规则',preparations:'准备',forecasts:'条件计划','material-lots':'材料批次'}
</script>
<template>
  <div v-if="w.relatedDemand.value" class="spray-alert"><span>正在查看此订单的关联记录；合并单据保留完整内容。</span><button class="spray-text-button" @click="w.passportId.value=w.relatedDemand.value">订单追踪</button><button class="spray-text-button" @click="clearOrder">查看全部订单</button></div>
  <div v-if="w.error.value" role="alert" class="spray-alert"><CircleAlert :size="18" /><span>{{ w.error.value }}</span><button class="spray-text-button" @click="w.refresh">重试</button></div>
  <div v-else-if="w.loading.value" class="spray-loading" role="status"><RefreshCw :size="16" /><span>正在读取 {{ w.asOf.value ? '最新记录' : '工作区' }}…</span></div>
  <div v-for="key in w.activeCollections.value.filter(k=>w.paging[k]&&w.items(k).length<(w.totals[k]??0))" :key="key" class="spray-alert"><span>{{ labels[key]??'记录' }}已载入 {{w.items(key).length}} / {{w.totals[key]}} 条</span><button class="spray-text-button" :disabled="w.loading.value" @click="w.loadMore(key)">继续载入</button></div>
</template>
