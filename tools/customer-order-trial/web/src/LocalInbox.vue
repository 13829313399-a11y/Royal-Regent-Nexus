<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { inboxApi, errorMessage, type InboxItem, type Recipient } from './api'
import { businessFields } from './fields'
const props = defineProps<{ factoryId: string }>()
const recipient = ref<Recipient>('pmc')
const choices: Array<{ id: Recipient; label: string }> = [{ id: 'pmc', label: 'PMC' }, { id: 'warehouse', label: '仓库' }, { id: 'injection', label: '啤机部' }]
const items = ref<InboxItem[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const receiving = ref('')
const failure = ref('')
const success = ref('')
let sequence = 0
const pages = computed(() => Math.max(1, Math.ceil(total.value / 50)))
async function load() {
  const token = ++sequence
  const requestedFactory = props.factoryId
  const requestedRecipient = recipient.value
  loading.value = true
  failure.value = ''
  try {
    const result = await inboxApi.list(requestedFactory, requestedRecipient, page.value)
    if (token !== sequence) return
    if (result.items.some(item => item.factory_id !== requestedFactory || item.recipient !== requestedRecipient)) throw new Error('收件记录与当前厂区或部门不一致，请重新加载。')
    items.value = result.items
    total.value = result.total
  } catch (error) { if (token === sequence) { items.value = []; total.value = 0; failure.value = await errorMessage(error) } }
  finally { if (token === sequence) loading.value = false }
}
function changeRecipient() { page.value = 1; success.value = ''; void load() }
function go(next: number) { page.value = next; void load() }
async function receive(item: InboxItem) {
  if (receiving.value || item.status === 'received') return
  receiving.value = item.id
  failure.value = ''
  success.value = ''
  try {
    await inboxApi.receive(props.factoryId, recipient.value, item.id)
    success.value = `版本 V${item.version} 已在本机签收，原版本记录继续保留。`
    await load()
  } catch (error) { failure.value = await errorMessage(error) }
  finally { receiving.value = '' }
}
watch(() => props.factoryId, () => { page.value = 1; success.value = ''; void load() }, { immediate: true })
onBeforeUnmount(() => { sequence += 1 })
</script>
<template>
  <SectionPanel title="本机部门收件" subtitle="查看本机发送的订单版本，并模拟部门签收。此处的签收和发送不会通知线上员工。">
    <div class="trial-actions"><label>接收部门<select v-model="recipient" :disabled="Boolean(receiving) || loading" @change="changeRecipient"><option v-for="choice in choices" :key="choice.id" :value="choice.id">{{ choice.label }}</option></select></label><Button variant="outline" :disabled="loading || Boolean(receiving)" @click="load">{{ loading ? '加载中…' : '刷新记录' }}</Button></div>
    <p v-if="failure" class="notice error" role="alert">{{ failure }}</p><p v-if="success" class="notice success" role="status">{{ success }}</p>
    <div class="inbox-grid"><article v-for="item in items" :key="item.id" class="inbox-card"><header><h3>{{ item.snapshot.customer_name || item.snapshot.customer_code }} · {{ item.snapshot.po_no || item.snapshot.reference_no || '订单' }}</h3><StatusPill :label="item.status === 'received' ? '已签收' : '待签收'" :tone="item.status === 'received' ? 'teal' : 'amber'" /></header><dl><div><dt>完整货号</dt><dd>{{ item.snapshot.product_no || '—' }}</dd></div><div><dt>订单数量</dt><dd>{{ item.snapshot.quantity ?? '待核对' }}</dd></div><div><dt>版本</dt><dd>V{{ item.version }}{{ item.version < item.latest_version ? `（最新 V${item.latest_version}）` : ' · 当前版本' }}</dd></div><div><dt>发送时间</dt><dd>{{ item.created_at }}</dd></div></dl><p v-if="item.version < item.latest_version" class="notice warning">此记录为历史版本；请同时核对最新版本，签收历史记录不会替代最新版本。</p><details><summary>展开该版本业务字段</summary><dl class="inbox-snapshot"><div v-for="field in businessFields(item.snapshot)" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></div></dl></details><p v-if="item.received_at" class="muted">{{ item.received_by }} · 签收于 {{ item.received_at }}</p><div><Button variant="outline" :disabled="Boolean(receiving) || loading || item.status === 'received'" @click="receive(item)">{{ receiving === item.id ? '正在签收…' : item.status === 'received' ? '已签收' : '签收该版本' }}</Button></div></article></div>
    <p v-if="!loading && !failure && !items.length" class="muted">该部门暂无本机收件记录。请先在订单台账的订单详情中选择部门并发送。</p>
    <div class="pagination"><span>第 {{ page }} / {{ pages }} 页，共 {{ total }} 条</span><Button variant="outline" :disabled="page <= 1 || loading || Boolean(receiving)" @click="go(page - 1)">上一页</Button><Button variant="outline" :disabled="page >= pages || loading || Boolean(receiving)" @click="go(page + 1)">下一页</Button></div>
  </SectionPanel>
</template>
