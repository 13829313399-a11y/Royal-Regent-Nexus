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
  Search,
  Table2,
} from '@lucide/vue'
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import CustomerOrderCenterWorkspace from '@/components/modules/sales/customer-order-center/CustomerOrderCenterWorkspace.vue'
import { getFactoryScopedRoute } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'

export type CustomerOrderCenterSection = 'dashboard' | 'import' | 'preview' | 'ledger' | 'exceptions' | 'schedule'

const appStore = useAppStore()
appStore.setActiveDepartment('sales-business')

const activeSection = ref<CustomerOrderCenterSection>('dashboard')
const activeFactory = computed(() => appStore.activeProductionFactory)
const departmentRoute = computed(() => getFactoryScopedRoute('/modules/sales-business', activeFactory.value.id))

const navigationItems = [
  { id: 'dashboard' as const, label: '工作台', icon: LayoutDashboard },
  { id: 'import' as const, label: 'PO 与排期导入', icon: FileInput },
  { id: 'preview' as const, label: '预览与确认', icon: ClipboardList },
  { id: 'ledger' as const, label: '订单数据台账', icon: Table2 },
  { id: 'exceptions' as const, label: '异常与提醒', icon: CircleAlert },
  { id: 'schedule' as const, label: '厂区总排期', icon: CalendarRange },
]

function navigate(section: CustomerOrderCenterSection) {
  activeSection.value = section
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
</script>

<template>
  <div class="customer-order-center">
    <header class="order-topbar">
      <div class="order-topbar__brand">
        <RouterLink :to="departmentRoute" class="order-back-link" aria-label="返回业务部模块中心">
          <ArrowLeft aria-hidden="true" />
          <span>业务部模块中心</span>
        </RouterLink>
      </div>

      <label class="order-global-search">
        <Search aria-hidden="true" />
        <input type="search" placeholder="全局搜索 P/O#、合同号或产品编号" aria-label="全局搜索订单">
      </label>

      <div class="order-topbar__actions">
        <button type="button" class="order-icon-button order-help-button">
          <HelpCircle aria-hidden="true" />
          <span>帮助</span>
        </button>
        <button type="button" class="order-icon-button" aria-label="通知">
          <Bell aria-hidden="true" />
        </button>
        <span class="order-factory-chip">{{ activeFactory.shortName }}</span>
        <AccountMenu />
      </div>
    </header>

    <aside class="order-sidebar">
      <div class="order-sidebar__heading">
        <span class="order-sidebar__mark"><CalendarRange aria-hidden="true" /></span>
        <div>
          <h1>客户订单中心</h1>
          <p>基础功能试用版</p>
        </div>
      </div>

      <button type="button" class="order-new-button" @click="navigate('import')">
        <FileInput aria-hidden="true" />
        新建导入
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
        </button>
      </nav>

      <div class="order-sidebar__scope">
        <div class="order-sidebar__scope-title">
          <CircleAlert aria-hidden="true" />
          当前阶段
        </div>
        <ol>
          <li><b>01</b><span>PO 入客户排期并输出</span></li>
          <li><b>02</b><span>厂区月度走货与生产反馈</span></li>
          <li><b>03</b><span>交付异常与生产提醒</span></li>
        </ol>
        <p>生产模块后续读取订单需求并回传只读进度。</p>
      </div>
    </aside>

    <main class="order-main">
      <nav class="order-mobile-nav" aria-label="客户订单中心移动端页面">
        <button
          v-for="item in navigationItems"
          :key="`mobile-${item.id}`"
          type="button"
          :class="{ active: activeSection === item.id }"
          @click="navigate(item.id)"
        >
          <component :is="item.icon" aria-hidden="true" />
          {{ item.label }}
        </button>
      </nav>

      <CustomerOrderCenterWorkspace
        :active-section="activeSection"
        :factory-id="activeFactory.id"
        :factory-name="activeFactory.shortName"
        @navigate="navigate"
      />
    </main>
  </div>
</template>

<style scoped>
.customer-order-center {
  --order-primary: #003d9b;
  --order-primary-strong: #002c72;
  --order-primary-container: #0052cc;
  --order-secondary: #006c47;
  --order-secondary-container: #8af5be;
  --order-background: #faf8ff;
  --order-surface: #fff;
  --order-surface-low: #f3f3fd;
  --order-surface-high: #e7e7f2;
  --order-outline: #737685;
  --order-outline-soft: #c3c6d6;
  --order-text: #191b23;
  --order-muted: #434654;

  min-height: 100vh;
  background: var(--order-background);
  color: var(--order-text);
  font-family: Inter, "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
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
  background: rgb(250 248 255 / 94%);
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
  color: #08736d;
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
  height: 38px;
  gap: 9px;
  border: 1px solid var(--order-outline-soft);
  border-radius: 6px;
  background: #ededf8;
  padding: 0 13px;
  color: var(--order-outline);
  transition: border-color 180ms ease, background-color 180ms ease, box-shadow 220ms ease;
}

.order-global-search:focus-within {
  border-color: var(--order-primary);
  box-shadow: 0 0 0 3px rgb(0 61 155 / 10%);
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
  color: #fff;
}

.order-sidebar__mark svg {
  width: 20px;
  height: 20px;
}

.order-sidebar h1,
.order-sidebar p {
  margin: 0;
}

.order-sidebar h1 {
  color: var(--order-primary);
  font-size: 18px;
  font-weight: 900;
  line-height: 1.3;
}

.order-sidebar__heading p {
  margin-top: 2px;
  color: var(--order-muted);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .12em;
}

.order-new-button {
  display: flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 9px;
  border: 0;
  border-radius: 6px;
  background: var(--order-primary-container);
  color: #fff;
  font-size: 14px;
  font-weight: 900;
  box-shadow: 0 7px 16px rgb(0 61 155 / 18%);
  transition: background-color 180ms ease, box-shadow 220ms ease, transform 180ms ease;
}

.order-new-button:hover {
  background: var(--order-primary);
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgb(0 61 155 / 24%);
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
  color: #005235;
  font-weight: 900;
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
  background: #fff;
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
  animation: order-main-enter 300ms cubic-bezier(.2, .8, .2, 1) both;
}

.order-mobile-nav {
  display: none;
}

@media (max-width: 980px) {
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
    min-height: 38px;
    flex: 0 0 auto;
    align-items: center;
    gap: 7px;
    border: 1px solid var(--order-outline-soft);
    border-radius: 6px;
    background: #fff;
    padding: 0 11px;
    color: var(--order-muted);
    font-size: 12px;
    font-weight: 800;
    transition: background-color 180ms ease, border-color 180ms ease, color 180ms ease, transform 180ms ease;
  }

  .order-mobile-nav button.active {
    border-color: #58d398;
    background: var(--order-secondary-container);
    color: #005235;
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
  .order-help-button,
  .order-factory-chip {
    display: none;
  }

  .order-main {
    padding-inline: 12px;
  }
}

@keyframes order-main-enter {
  from {
    opacity: 0;
    transform: translateY(8px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
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
</style>
