<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { CalendarRange, FileInput, ClipboardList, Table2, CalendarClock, Inbox, Download } from '@lucide/vue'
import CustomerOrderCenterWorkspace from '@/components/modules/sales/customer-order-center/CustomerOrderCenterWorkspace.vue'
import type { CustomerOrderCenterSection } from '@/types/customerOrder'
import LocalInbox from './LocalInbox.vue'
import ExportHistory from './ExportHistory.vue'
import { api, errorMessage } from './api'
type Section = CustomerOrderCenterSection | 'local-inbox' | 'exports'
const section = ref<Section>('import')
const ready = ref(false)
const customers = ref<string[]>([])
const customerNames = ref('')
const failure = ref('')
const notice = ref('')
const navigation: { id: Section; label: string; icon: typeof FileInput }[] = [
  { id: 'import', label: 'PO 与排期导入', icon: FileInput },
  { id: 'preview', label: '预览与确认', icon: ClipboardList },
  { id: 'ledger', label: '订单数据台账', icon: Table2 },
  { id: 'customer-schedule', label: '各客排期', icon: CalendarClock },
  { id: 'local-inbox', label: '本机部门收件', icon: Inbox },
  { id: 'exports', label: '排期文件历史', icon: Download },
]
async function load() {
  failure.value = ''
  try {
    const config = await api.config()
    if (config.factory_id !== 'huaxing' || config.customers.length !== 1 || !['caixing', 'edu', 'dickie'].includes(config.customers[0]?.code ?? '')) {
      throw new Error('启动配置与华兴专用包不一致，请使用完整解压后的专用包。')
    }
    customers.value = config.customers.map(c => c.code)
    customerNames.value = config.customers.map(c => c.name).join('、')
    ready.value = true
  } catch (error) { failure.value = await errorMessage(error) }
}
onMounted(load)
</script>

<template>
  <div class="customer-order-center">
    <header class="order-topbar">
      <div class="order-topbar__brand"><span class="order-back-link">华兴 · 订单入排期</span></div>
      <div class="order-topbar__actions"><span class="order-factory-chip">华兴</span><span>本机试用</span></div>
    </header>
    <aside class="order-sidebar">
      <div class="order-sidebar__heading"><span class="order-sidebar__mark"><CalendarRange /></span><div><h1 class="order-sidebar__title">客户订单中心</h1><p class="order-sidebar__subtitle">客户订单与统一排期</p></div></div>
      <button class="order-new-button" @click="section = 'import'"><FileInput />新建导入</button>
      <nav class="order-sidebar__nav" aria-label="客户订单中心页面">
        <button v-for="item in navigation" :key="item.id" :class="{ active: section === item.id }" :aria-current="section === item.id ? 'page' : undefined" @click="section = item.id"><component :is="item.icon" /><span>{{ item.label }}</span></button>
      </nav>
      <div class="order-sidebar__scope"><div class="order-sidebar__scope-title">本机试用范围</div><p>本包客户：{{ customerNames }}。缺资料可先生成，后续补充。</p><p>订单、发送和走货记录保存在本机；发送进入本机部门收件箱。</p></div>
    </aside>
    <main class="order-main">
      <nav class="order-mobile-nav" aria-label="客户订单中心移动端页面"><button v-for="item in navigation" :key="item.id" :class="{ active: section === item.id }" @click="section = item.id">{{ item.label }}</button></nav>
      <p v-if="failure" role="alert">{{ failure }} <button @click="load">重试</button></p>
      <p v-else-if="!ready" role="status">正在读取本机配置…</p>
      <template v-if="ready">
        <p v-if="notice" role="status">{{ notice }}</p>
        <CustomerOrderCenterWorkspace v-show="section !== 'exports' && section !== 'local-inbox'"
          :active-section="section === 'exports' || section === 'local-inbox' ? 'import' : section"
          factory-id="huaxing" factory-name="华兴" :initial-customer-code="customers[0]"
          :customer-codes="customers" local-only @navigate="section = $event"
          @feedback="notice = '请把问题截图和原始文件交给对接人。'" />
        <LocalInbox v-if="section === 'local-inbox'" factory-id="huaxing" />
        <ExportHistory v-if="section === 'exports'" />
      </template>
    </main>
  </div>
</template>

<style scoped src="../../../../src/styles/customer-order-center-shell.css"></style>
