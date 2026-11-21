<script setup lang="ts">
import {
  ArrowLeft,
  Bell,
  CalendarRange,
  CircleAlert,
  ClipboardList,
  FileInput,
  HelpCircle,
  LayoutDashboard,
  MessageSquarePlus,
  MessagesSquare,
  Search,
  Table2,
} from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { isCuttingPoTestBridgeEnabled } from '@/features/cutting-operations/poTestBridge'
import CuttingAcceptanceNotice from '@/features/cutting-operations/CuttingAcceptanceNotice.vue'
import UsageGuideDialog from '@/components/common/UsageGuideDialog.vue'
import ModuleFeedbackHub from '@/features/module-feedback/ModuleFeedbackHub.vue'
import type { FeedbackContext } from '@/api/moduleFeedback'
import CustomerOrderCenterWorkspace from '@/components/modules/sales/customer-order-center/CustomerOrderCenterWorkspace.vue'
import CartonQuickAssetLibrary from '@/components/CartonQuickAssetLibrary.vue'
import HuakangBJPIntake from '@/components/modules/sales/customer-order-center/HuakangBJPIntake.vue'
import { customerOrderUsageGuide } from '@/data/salesUsageGuides'
import { getFactoryScopedRoute } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'

import type { CustomerOrderCenterSection } from '@/types/customerOrder'
export type { CustomerOrderCenterSection } from '@/types/customerOrder'

const appStore = useAppStore()
const route = useRoute()
const router = useRouter()
appStore.setActiveDepartment('sales-business')

const activeSection = ref<CustomerOrderCenterSection>('ledger')
const materialsSearch = ref('')
const orderWorkspace = ref<InstanceType<typeof CustomerOrderCenterWorkspace> | null>(null)
const feedbackHub = ref<InstanceType<typeof ModuleFeedbackHub> | null>(null)
const feedbackUnread = ref(0)
const activeFactory = computed(() => appStore.activeProductionFactory)
const initialCustomerCode = computed(() => route.query.factory === activeFactory.value.id
  && route.query.customer === 'zuru' && ['huakang-a', 'huaxing'].includes(activeFactory.value.id) ? 'zuru' : '')
watch(() => [initialCustomerCode.value, route.query.section], () => {
  if (initialCustomerCode.value && route.query.section === 'import') activeSection.value = 'import'
}, { immediate: true })
const poTestBridge = computed(() => activeFactory.value.id === 'huakang-c' && isCuttingPoTestBridgeEnabled())
const focusedOrderId = computed(() => route.query.factory === activeFactory.value.id
  && typeof route.query.order === 'string' && route.query.order.length <= 64 ? route.query.order : '')
watch(focusedOrderId, id => { if (id) activeSection.value = 'ledger' }, { immediate: true })
function clearFocusedOrder() {
  if (route.query.order) void router.replace({ query: { ...route.query, order: undefined } })
}
const departmentRoute = computed(() => getFactoryScopedRoute('/modules/sales-business', activeFactory.value.id))

const standardNavigationItems = [
  { id: 'dashboard' as const, label: '工作台', icon: LayoutDashboard },
  { id: 'import' as const, label: 'PO 与排期导入', icon: FileInput },
  { id: 'preview' as const, label: '预览与确认', icon: ClipboardList },
  { id: 'ledger' as const, label: '订单数据台账', icon: Table2 },
  { id: 'customer-schedule' as const, label: '各客排期', icon: CalendarRange },
  { id: 'exceptions' as const, label: '异常与提醒', icon: CircleAlert },
  { id: 'schedule' as const, label: '厂区总排期', icon: CalendarRange },
  { id: 'materials' as const, label: '箱唛资料', icon: FileInput },
  { id: 'feedback' as const, label: '反馈与答复', icon: MessagesSquare },
]
const huakangBSections = new Set<CustomerOrderCenterSection>(['jp-intake', 'ledger', 'customer-schedule', 'materials', 'feedback'])
const navigationItems = computed(() => activeFactory.value.id === 'huakang-b'
  ? [{ id: 'jp-intake' as const, label: 'JP问单录入', icon: FileInput }, ...standardNavigationItems.filter(item => huakangBSections.has(item.id))]
  : standardNavigationItems)
function normalizeSection(section: CustomerOrderCenterSection): CustomerOrderCenterSection {
  if (activeFactory.value.id === 'huakang-b' && !huakangBSections.has(section)) return 'jp-intake'
  if (activeFactory.value.id !== 'huakang-b' && section === 'jp-intake') return 'ledger'
  return section
}
watch(() => activeFactory.value.id, factory => {
  if (factory === 'huakang-b') activeSection.value = focusedOrderId.value ? 'ledger' : 'jp-intake'
  else if (activeSection.value === 'jp-intake') activeSection.value = 'ledger'
}, { immediate: true })
// Old PO-import bookmarks must not reopen the unrelated formal-order workspace in B.
watch(() => route.query.section, section => {
  if (activeFactory.value.id === 'huakang-b' && typeof section === 'string'
    && ['dashboard', 'import', 'preview', 'exceptions', 'schedule', 'jp-intake'].includes(section)) {
    activeSection.value = 'jp-intake'
  }
}, { immediate: true })
watch(() => activeFactory.value.id, () => { materialsSearch.value = '' })

function reportProblem(context?: FeedbackContext) {
  feedbackHub.value?.openComposer(context ?? {
    ...orderWorkspace.value?.feedbackContext(),
    page: navigationItems.value.find(item => item.id === activeSection.value)?.label ?? '客户订单中心',
    section: activeSection.value,
  })
}

function navigate(section: CustomerOrderCenterSection) {
  section = normalizeSection(section)
  if (section !== 'ledger') clearFocusedOrder()
  activeSection.value = section
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
</script>

<template>
  <div class="customer-order-center" :class="{ 'customer-order-center--materials': activeSection === 'materials' }" data-yl-help="customer-orders.overview">
    <header class="order-topbar">
      <div class="order-topbar__brand">
        <RouterLink :to="departmentRoute" class="order-back-link" aria-label="返回业务部模块中心">
          <ArrowLeft aria-hidden="true" />
          <span>业务部模块中心</span>
        </RouterLink>
      </div>

      <label class="order-global-search">
        <Search aria-hidden="true" />
        <input v-if="activeSection === 'materials'" v-model="materialsSearch" type="search" placeholder="搜索箱唛文件名、合同 / PO、客户或货号" aria-label="搜索箱唛资料">
        <input v-else type="search" placeholder="全局搜索 P/O#、合同号或产品编号" aria-label="全局搜索订单">
      </label>

      <div class="order-topbar__actions">
        <button type="button" class="order-icon-button" @click="reportProblem()">
          <MessageSquarePlus aria-hidden="true" /><span>反馈问题</span>
        </button>
        <UsageGuideDialog v-bind="customerOrderUsageGuide">
          <template #trigger>
            <button type="button" class="order-icon-button order-help-button" aria-label="使用教程">
              <HelpCircle aria-hidden="true" />
              <span>使用教程</span>
            </button>
          </template>
        </UsageGuideDialog>
        <button type="button" class="order-icon-button order-feedback-notice" :aria-label="`反馈通知${feedbackUnread ? `，${feedbackUnread} 条未读` : ''}`" @click="navigate('feedback')">
          <Bell aria-hidden="true" />
          <b v-if="feedbackUnread" class="order-feedback-count">{{ feedbackUnread > 99 ? '99+' : feedbackUnread }}</b>
        </button>
        <span class="order-factory-chip">{{ activeFactory.shortName }}</span>
        <AccountMenu />
      </div>
    </header>

    <aside class="order-sidebar">
      <div class="order-sidebar__heading">
        <span class="order-sidebar__mark"><CalendarRange aria-hidden="true" /></span>
        <div>
          <component :is="activeSection === 'jp-intake' ? 'p' : 'h1'" class="order-sidebar__title">{{ activeFactory.id === 'huakang-b' ? '华康B问单' : '客户订单中心' }}</component>
          <p class="order-sidebar__subtitle">{{ activeFactory.id === 'huakang-b' ? '邮件问单与金山导出' : '客户订单与统一排期' }}</p>
        </div>
      </div>

      <button type="button" class="order-new-button" @click="navigate(activeFactory.id === 'huakang-b' ? 'jp-intake' : 'import')">
        <FileInput aria-hidden="true" />
        {{ activeFactory.id === 'huakang-b' ? '新建问单' : '新建导入' }}
      </button>

      <nav class="order-sidebar__nav" aria-label="客户订单中心页面">
        <button
          v-for="item in navigationItems"
          :key="item.id"
          type="button"
          :class="{ active: activeSection === item.id }"
          :aria-current="activeSection === item.id ? 'page' : undefined"
          @click="navigate(item.id)"
        >
          <component :is="item.icon" aria-hidden="true" />
          <span>{{ item.label }}</span>
          <b v-if="item.id === 'feedback' && feedbackUnread" class="order-feedback-count">{{ feedbackUnread }}</b>
        </button>
      </nav>

      <div class="order-sidebar__scope">
        <div class="order-sidebar__scope-title">
          <CircleAlert aria-hidden="true" />
          当前阶段
        </div>
        <ol v-if="activeFactory.id === 'huakang-b'">
          <li><b>01</b><span>准备排期与货价参照</span></li>
          <li><b>02</b><span>导入邮件并核对问单明细</span></li>
          <li><b>03</b><span>确认编号并导出金山 Excel</span></li>
        </ol>
        <ol v-else>
          <li><b>01</b><span>导入并核对客户 PO</span></li>
          <li><b>02</b><span>确认后保存订单台账</span></li>
          <li><b>03</b><span>发送订单与凭出货单确认走货</span></li>
        </ol>
        <p>{{ activeFactory.id === 'huakang-b' ? '问单导出不等于已录入金山或成为正式订单。' : '订单中心不维护生产、物料、库存或排产数据。' }}</p>
      </div>
    </aside>

    <main class="order-main">
      <template v-if="poTestBridge">
        <CuttingAcceptanceNotice />
        <aside class="po-test-bridge" role="note" aria-label="客户PO临时测试线路">
          <strong>客户 PO → 裁床临时测试线路</strong>
          <p>仅写入本独立验收副本。新建导入 → 选择客户并上传 PO 和排期 → 核对预览并保存台账 → 下发时选择裁床部 → 裁床签收。仍需具备各环节权限。</p>
          <button type="button" @click="navigate('import')">新建 PO 导入</button>
          <RouterLink to="/modules/production/cutting/planning?factory=huakang-c">前往裁床接单／排期</RouterLink>
        </aside>
      </template>
      <nav class="order-mobile-nav" aria-label="客户订单中心移动端页面">
        <button
          v-for="item in navigationItems"
          :key="`mobile-${item.id}`"
          type="button"
          :class="{ active: activeSection === item.id }"
          :aria-current="activeSection === item.id ? 'page' : undefined"
          @click="navigate(item.id)"
        >
          <component :is="item.icon" aria-hidden="true" />
          {{ item.label }}
          <b v-if="item.id === 'feedback' && feedbackUnread" class="order-feedback-count">{{ feedbackUnread }}</b>
        </button>
      </nav>

      <CustomerOrderCenterWorkspace
        v-if="activeFactory.id !== 'huakang-b' || activeSection === 'ledger' || activeSection === 'customer-schedule'"
        v-show="activeSection !== 'feedback' && activeSection !== 'jp-intake' && activeSection !== 'materials'"
        ref="orderWorkspace"
        :key="activeFactory.id"
        :active-section="activeSection"
        :factory-id="activeFactory.id"
        :factory-name="activeFactory.shortName"
        :focus-line-id="focusedOrderId"
        :initial-customer-code="initialCustomerCode"
        @close-order="clearFocusedOrder"
        @navigate="navigate"
        @feedback="reportProblem"
      />
      <div v-if="activeSection === 'materials'" class="space-y-4">
        <CartonQuickAssetLibrary v-model:search="materialsSearch" :key="`quick-${activeFactory.id}`" :factory-id="activeFactory.id" audience="sales" />

      </div>
      <HuakangBJPIntake v-if="activeSection === 'jp-intake' && activeFactory.id === 'huakang-b'"
        :key="`jp-${activeFactory.id}`" :factory-id="activeFactory.id" />
      <ModuleFeedbackHub
        :key="`feedback-${activeFactory.id}`"
        ref="feedbackHub"
        :factory-id="activeFactory.id"
        :factory-name="activeFactory.shortName"
        :active="activeSection === 'feedback'"
        @navigate="navigate('feedback')"
        @unread="feedbackUnread = $event"
      />
    </main>
  </div>
</template>

<style scoped src="../styles/customer-order-center-shell.css"></style>
