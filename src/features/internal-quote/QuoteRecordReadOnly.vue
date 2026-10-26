<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { RefreshCw } from '@lucide/vue'
import { internalQuoteApi, type ApiInternalQuote } from '@/api/internalQuote'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { Button } from '@/components/ui/button'
import InternalQuoteReadiness from '@/components/modules/sales/internal-quote/InternalQuoteReadiness.vue'
import { quoteSelection, useQuoteAssistantSelection } from './assistantContext'

const props = defineProps<{ quoteId: string; factoryId: string }>()
type RecordHeader = Pick<ApiInternalQuote, 'id' | 'factory_id' | 'quote_no' | 'product_name' | 'customer' | 'qty' |
  'version_label' | 'module_version' | 'formula_version' | 'status' | 'updated_at' | 'readiness' | 'header_revision'>
const record = ref<RecordHeader>(), loading = ref(false), error = ref(''), heading = ref<HTMLElement>()
let generation = 0
const workflow = computed(() => record.value?.module_version === 'v4' ? '直接输出' : record.value?.module_version === 'v3' ? '整单审核' : record.value?.module_version === 'v2' ? '分段审核' : '原流程')
const status = computed(() => {
  const item = record.value
  if (!item) return ''
  if (item.module_version === 'v4') return item.status === 'exported' ? '已输出并冻结' : item.status === 'archived' ? '已归档'
    : item.readiness?.state === 'ready' ? '可输出' : item.readiness?.state === 'incomplete' ? '待补齐 / 待重算' : '填写中'
  return ({drafting:'填写中',pending_review:'待审核',rejected:'已退回',fully_approved:'待最终提交',final_pending:'待审核或放行',released:'已放行',exported:'已输出',archived:'已归档'} as Record<string,string>)[item.status] || item.status
})
async function load() {
  const token = ++generation, id = props.quoteId, factory = props.factoryId
  record.value = undefined; error.value = ''; loading.value = true
  try {
    const data = await internalQuoteApi.get(id)
    if (token !== generation) return
    if (data.id !== id || data.factory_id !== factory) throw new Error('原报价不属于当前厂区，请返回报价首页重新选择。')
    // Retain only native operational fields in this read-only view.
    record.value = {id:data.id,factory_id:data.factory_id,quote_no:data.quote_no,product_name:data.product_name,
      customer:data.customer,qty:data.qty,version_label:data.version_label,module_version:data.module_version,
      formula_version:data.formula_version,status:data.status,updated_at:data.updated_at,readiness:data.readiness,
      header_revision:data.header_revision}
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
async function retry() { await load(); await nextTick(); heading.value?.focus() }
watch(() => [props.quoteId, props.factoryId], load, { immediate: true })
onBeforeUnmount(() => { ++generation })
useQuoteAssistantSelection(() => quoteSelection(props.factoryId, [props.quoteId], {
  ...(loading.value || !record.value ? {scope_error:'原报价尚未读取成功，请重新读取。'} : {}),
  scope_note:'当前显示原报价版本的业务状态；成本及金额另需汇总读取权限。',
}))
</script>

<template>
  <section class="quote-record-readonly rounded-xl border border-border bg-card p-5 text-card-foreground" :aria-busy="loading">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 ref="heading" tabindex="-1" class="text-lg font-semibold focus-visible:outline-2 focus-visible:outline-ring">{{ record?.product_name || '原报价版本' }}</h1>
      <Button variant="outline" :disabled="loading" @click="retry"><RefreshCw :size="16" />{{ loading ? '读取中…' : '重新读取' }}</Button>
    </div>
    <p class="my-3 text-muted-foreground">当前账号可查看报价业务状态；成本、利润和金额需要汇总读取权限。</p>
    <p v-if="loading" role="status">正在读取原报价…</p>
    <p v-else-if="error" role="alert" class="my-3 text-destructive">{{ error }}</p>
    <template v-else-if="record">
      <dl class="quote-record-fields">
        <div><dt>报价单号 / 版本</dt><dd>{{ record.quote_no }} · {{ record.version_label }}</dd></div>
        <div><dt>客户</dt><dd>{{ record.customer || '未记录' }}</dd></div>
        <div><dt>流程 / 状态</dt><dd>{{ workflow }} · {{ status }}</dd></div>
        <div><dt>原数量</dt><dd>{{ record.qty }}（源记录未明确件/套单位）</dd></div>
        <div><dt>公式 / 资料版本</dt><dd>{{ record.formula_version }} · {{ record.header_revision }}</dd></div>
        <div><dt>原记录更新时间</dt><dd>{{ formatBusinessDateTime(record.updated_at) }}（北京时间）</dd></div>
      </dl>
      <InternalQuoteReadiness :readiness="record.readiness" />
    </template>
    <RouterLink class="mt-5 inline-block text-primary underline" :to="{name:'internal-quote-desk-home',query:{factory:factoryId}}">返回报价首页</RouterLink>
  </section>
</template>

<style scoped>
.quote-record-readonly{overflow-wrap:anywhere}.quote-record-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:20px 0}.quote-record-fields dt{color:var(--muted-foreground);margin-bottom:5px}.quote-record-fields dd{margin:0;white-space:pre-wrap}@media(max-width:640px){.quote-record-fields{grid-template-columns:minmax(0,1fr)}}
</style>
