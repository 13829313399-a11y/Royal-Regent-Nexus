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

export type CustomerOrderCenterSection = 'dashboard' | 'import' | 'preview' | 'ledger' | 'customer-schedule' | 'exceptions' | 'schedule' | 'feedback' | 'jp-intake' | 'materials'

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

<style scoped>
.po-test-bridge { margin-bottom: 16px; padding: 12px 16px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--accent); color: var(--foreground); line-height: 1.6; overflow-wrap: anywhere; }
.po-test-bridge button, .po-test-bridge a { display: inline-flex; align-items: center; min-height: 36px; margin-right: 16px; color: var(--primary); text-decoration: underline; text-underline-offset: 3px; }
.customer-order-center {
  --order-primary: var(--primary);
  --order-primary-strong: color-mix(in oklab, var(--primary) 90%, black);
  --order-primary-container: var(--primary);
  --order-secondary: var(--primary);
  --order-secondary-container: color-mix(in oklab, var(--primary) 10%, var(--card));
  --order-background: var(--background);
  --order-surface: var(--card);
  --order-surface-low: var(--muted);
  --order-surface-high: var(--accent);
  --order-outline: var(--muted-foreground);
  --order-outline-soft: var(--border);
  --order-text: var(--foreground);
  --order-muted: var(--muted-foreground);

  min-height: 100vh;
  background: var(--order-background);
  color: var(--order-text);
  font-family: inherit;
}

.order-topbar {
  position: fixed;
  inset: 0 0 auto;
  z-index: 70;
  display: flex;
  height: 58px;
  align-items: center;
  gap: 22px;
  border-bottom: 1px solid var(--order-outline-soft);
  background: color-mix(in oklab, var(--card) 94%, transparent);
  padding: 0 18px;
  backdrop-filter: blur(12px);
}

.order-topbar__brand,
.order-topbar__actions,
.order-global-search,
.order-icon-button {
  display: flex;
  align-items: center;
}

.order-topbar__brand {
  width: 210px;
}

.order-back-link,
.order-icon-button {
  justify-content: center;
  border: 0;
  background: transparent;
  color: var(--order-muted);
  transition: background-color 180ms ease, color 180ms ease, transform 180ms ease;
}

.order-back-link {
  display: inline-flex;
  width: auto;
  height: 34px;
  align-items: center;
  gap: 7px;
  border-radius: 6px;
  padding: 0 10px;
  color: var(--order-primary);
  font-size: 13px;
  font-weight: 800;
  text-decoration: none;
}

.order-back-link:hover,
.order-icon-button:hover {
  background: var(--order-surface-high);
  color: var(--order-primary);
}

.order-back-link svg,
.order-icon-button svg {
  width: 19px;
  height: 19px;
}

.order-back-link svg {
  width: 15px;
  height: 15px;
  stroke-width: 2.2;
}

.order-global-search {
  width: min(440px, 42vw);
  min-width: 0;
  height: 38px;
  gap: 9px;
  border: 1px solid var(--order-outline-soft);
  border-radius: 10px;
  background: var(--order-surface);
  padding: 0 13px;
  color: var(--order-outline);
  transition: border-color 180ms ease, background-color 180ms ease, box-shadow 220ms ease;
}

.order-global-search:focus-within {
  border-color: var(--order-primary);
  box-shadow: 0 0 0 3px color-mix(in oklab, var(--ring) 20%, transparent);
}

.order-global-search svg {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
}

.order-global-search input {
  min-width: 0;
  flex: 1;
  border: 0;
  background: transparent;
  color: var(--order-text);
  font-size: 13px;
  outline: none;
}

.order-topbar__actions {
  margin-left: auto;
  flex: 0 0 auto;
  white-space: nowrap;
  gap: 7px;
}

.order-icon-button {
  min-width: 36px;
  height: 36px;
  gap: 7px;
  border-radius: 6px;
  padding: 0 8px;
  font-size: 13px;
}

.order-factory-chip {
  border: 1px solid var(--order-outline-soft);
  border-radius: 6px;
  background: var(--order-surface);
  padding: 7px 10px;
  color: var(--order-muted);
  font-size: 12px;
  font-weight: 800;
}

.order-feedback-count { min-width: 18px; border-radius: 8px; background: #b45309; padding: 1px 5px; color: white; font-size: 10px; line-height: 16px; }
.order-feedback-notice { position: relative; }
.order-feedback-notice .order-feedback-count { position: absolute; top: -2px; right: -6px; }

.order-sidebar {
  position: fixed;
  inset: 58px auto 0 0;
  z-index: 60;
  display: flex;
  width: 240px;
  flex-direction: column;
  border-right: 1px solid var(--order-outline-soft);
  background: var(--order-surface-low);
  padding: 18px 13px;
  overflow-y: auto;
}

.order-sidebar__heading {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 0 7px 18px;
}

.order-sidebar__mark {
  display: grid;
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 8px;
  background: var(--order-primary);
  color: var(--primary-foreground);
}

.order-sidebar__mark svg {
  width: 20px;
  height: 20px;
}

.order-sidebar__title,
.order-sidebar p {
  margin: 0;
}

.order-sidebar__title {
  color: var(--order-text);
  font-size: 18px;
  font-weight: 600;
  line-height: 1.3;
}

.order-sidebar__subtitle {
  margin-top: 2px;
  color: var(--order-muted);
  font-size: 12px;
  line-height: 1.5;
}

.order-new-button {
  display: flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 9px;
  border: 0;
  border-radius: 8px;
  background: var(--order-primary-container);
  color: var(--primary-foreground);
  font-size: 14px;
  font-weight: 600;
  box-shadow: 0 1px 2px rgb(15 23 42 / 6%);
  transition: background-color 180ms ease, box-shadow 220ms ease, transform 180ms ease;
}

.order-new-button:hover {
  background: var(--order-primary-strong);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px color-mix(in oklab, var(--primary) 16%, transparent);
}

.order-new-button:active {
  transform: translateY(0) scale(.98);
}

.order-new-button svg {
  width: 19px;
  height: 19px;
}

.order-sidebar__nav {
  display: grid;
  gap: 4px;
  margin-top: 20px;
}

.order-sidebar__nav button {
  display: flex;
  width: 100%;
  min-height: 42px;
  align-items: center;
  gap: 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  padding: 0 12px;
  color: var(--order-muted);
  font-size: 14px;
  font-weight: 700;
  text-align: left;
  transition: background-color 180ms ease, color 180ms ease, transform 180ms ease;
}

.order-sidebar__nav button:hover {
  background: var(--order-surface-high);
  color: var(--order-primary);
  transform: translateX(2px);
}

.order-sidebar__nav button.active {
  background: var(--order-secondary-container);
  color: var(--order-primary);
  font-weight: 600;
}

.order-sidebar__nav svg {
  width: 19px;
  height: 19px;
  flex: 0 0 auto;
}

.order-sidebar__scope {
  margin-top: auto;
  border: 1px solid var(--order-outline-soft);
  border-radius: 8px;
  background: var(--order-surface);
  padding: 13px;
}

.order-sidebar__scope-title {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--order-primary);
  font-size: 12px;
  font-weight: 900;
  letter-spacing: .05em;
}

.order-sidebar__scope-title svg {
  width: 15px;
  height: 15px;
}

.order-sidebar__scope ol {
  display: grid;
  gap: 9px;
  margin: 12px 0;
  padding: 0;
  list-style: none;
}

.order-sidebar__scope li {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  color: var(--order-text);
  font-size: 12px;
  line-height: 1.45;
}

.order-sidebar__scope li b {
  color: var(--order-secondary);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
}

.order-sidebar__scope > p {
  color: var(--order-outline);
  font-size: 12px;
  line-height: 1.5;
}

.order-main {
  min-height: 100vh;
  margin-left: 240px;
  padding: 82px 24px 48px;
  animation: order-main-enter 300ms cubic-bezier(.2, .8, .2, 1) backwards;
}

.order-mobile-nav {
  display: none;
}

.customer-order-center :is(button, a):focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 3px;
}

@media (max-width: 980px) {
  .order-global-search { display: none; }
  .order-sidebar {
    display: none;
  }

  .order-main {
    margin-left: 0;
    padding-top: 76px;
  }

  .order-topbar__brand {
    width: auto;
  }

  .order-mobile-nav {
    display: flex;
    gap: 6px;
    margin-bottom: 16px;
    overflow-x: auto;
    padding-bottom: 4px;
  }

  .order-mobile-nav button {
    display: inline-flex;
    min-height: 44px;
    flex: 0 0 auto;
    align-items: center;
    gap: 7px;
    border: 1px solid var(--order-outline-soft);
    border-radius: 8px;
    background: var(--order-surface);
    padding: 0 11px;
    color: var(--order-muted);
    font-size: 12px;
    font-weight: 600;
    transition: background-color 180ms ease, border-color 180ms ease, color 180ms ease, transform 180ms ease;
  }

  .order-mobile-nav button.active {
    border-color: var(--order-primary);
    background: var(--order-secondary-container);
    color: var(--order-primary);
  }

  .order-mobile-nav button:active {
    transform: scale(.98);
  }

  .order-mobile-nav svg {
    width: 16px;
    height: 16px;
  }
}

@media (max-width: 720px) {
  .order-topbar {
    gap: 10px;
    padding-inline: 10px;
  }

  .order-global-search,
  .order-factory-chip {
    display: none;
  }

  .order-main {
    padding-inline: 12px;
  }
}

@media (max-width: 560px) {
  .order-back-link span, .order-help-button span { display: none; }
  .order-topbar__actions { gap: 3px; }
  .order-icon-button { gap: 4px; padding-inline: 6px; }
}

@keyframes order-main-enter {
  from {
    opacity: 0;
    transform: translateY(8px);
  }

  to {
    opacity: 1;
    transform: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .customer-order-center *,
  .customer-order-center *::before,
  .customer-order-center *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
  }
}
/* Materials use the top search at every width; keep it reachable on narrow screens. */
@media (max-width: 980px) {
  .customer-order-center--materials .order-topbar {
    height: 108px;
    flex-wrap: wrap;
    align-content: center;
    row-gap: 6px;
  }
  .customer-order-center--materials .order-global-search {
    display: flex;
    order: 3;
    width: 100%;
    flex-basis: 100%;
  }
  .customer-order-center--materials .order-main { padding-top: 126px; }
}
</style>
