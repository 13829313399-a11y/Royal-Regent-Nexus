<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Activity, CalendarDays, ChartColumn, Coins, Package, Printer, ReceiptText, Wallet } from '@lucide/vue';
import TdpButton from '../components/TdpButton.vue';
import { useWorkspaceContext } from "../context";
import DailyAmountChart from "../components/DailyAmountChart.vue";
import CostBreakdown from "../components/CostBreakdown.vue";
import { currency, displayStats, isAmount, type ChartDay } from "../dashboardPresentation";
const {
  dashboard,
  dateFrom,
  dateTo,
  loadDashboard,
  todayText,
  printerMetrics,
} = useWorkspaceContext();
const period = ref("month");
const stats = computed(() => displayStats(dashboard.value?.summary ?? {}));
const daily = computed(() => (stats.value.daily as ChartDay[] | undefined) ?? []);
type Machine = { machine_no: number; hours: number };
const firstMetrics = computed(() => [
  { label: '产值', display: currency(stats.value.revenue), icon: ChartColumn },
  { label: '支出', display: currency(stats.value.totalCost), icon: ReceiptText },
  { label: '结余', display: currency(stats.value.balance), icon: Wallet },
  { label: '材料成本', display: currency(stats.value.materialCost), icon: Package },
]);
const secondMetrics = computed(() => [
  { label: '生产记录', display: dashboard.value?.summary.recordCount ?? '—', icon: ReceiptText },
  { label: '生产天数', display: stats.value.productionDays ?? '—', icon: CalendarDays },
  { label: '在线机器', display: `${printerMetrics.value.connected} / ${printerMetrics.value.total}`, icon: Activity },
  { label: '正在打印', display: printerMetrics.value.running, icon: Printer },
]);
const machines = computed(
  () => (dashboard.value?.summary.machineHours as Machine[]) || [],
);
const maxHours = computed(() => machines.value.reduce((max, m) => isAmount(m.hours) ? Math.max(max, m.hours) : max, 0));
async function apply() {
  const today = todayText();
  if (period.value === "today") {
    dateFrom.value = today;
    dateTo.value = today;
  } else if (period.value === "month") {
    dateFrom.value = today.slice(0, 7) + "-01";
    dateTo.value = today;
  } else if (period.value === "year") {
    dateFrom.value = today.slice(0, 4) + "-01-01";
    dateTo.value = today;
  } else if (period.value === "all") {
    dateFrom.value = "";
    dateTo.value = "";
  }
  await loadDashboard();
}
onMounted(apply);
</script>
<template>
  <section v-if="dashboard" class="space-y-5">
    <form class="legacy-toolbar tdp-overview-toolbar" @submit.prevent="apply">
      <label for="tdp-period">查看周期</label>
      <select id="tdp-period" v-model="period" @change="apply">
        <option value="today">今天</option>
        <option value="month">本月</option>
        <option value="year">本年</option>
        <option value="custom">自定义范围</option>
        <option value="all">全部</option></select
      ><template v-if="period === 'custom'"
        ><input v-model="dateFrom" type="date" aria-label="开始日期" /><span
          >至</span
        ><input v-model="dateTo" type="date" aria-label="结束日期" /><TdpButton tone="soft" type="submit">查看</TdpButton></template
      ><span class="text-xs text-slate-500"
        >{{ dateFrom || "全部历史" }} {{ dateTo ? "～ " + dateTo : "" }}</span
      >
    </form>
    <div class="tdp-metric-group tdp-metrics-first grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <div v-for="metric in firstMetrics" :key="metric.label" class="metric-card" :class="{ 'balance-metric': metric.label === '结余' }">
        <span>{{ metric.label }}</span><strong>{{ metric.display }}</strong>
        <span class="tdp-metric-icon" aria-hidden="true"><component :is="metric.icon" :size="18" /></span>
      </div>
    </div>
    <div class="tdp-metric-group tdp-metrics-second grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <div v-for="metric in secondMetrics" :key="metric.label" class="metric-card">
        <span>{{ metric.label }}</span><strong>{{ metric.display }}</strong>
        <span class="tdp-metric-icon tdp-metric-icon--neutral" aria-hidden="true"><component :is="metric.icon" :size="18" /></span>
      </div>
    </div>
    <div class="tdp-overview-panels grid gap-5 lg:grid-cols-2">
      <article class="panel-card tdp-overview-panel">
        <h2 class="tdp-panel-title"><ChartColumn :size="17" aria-hidden="true" />产值与支出趋势</h2>
        <DailyAmountChart :days="daily" />
      </article>
      <article class="panel-card tdp-overview-panel">
        <h2 class="tdp-panel-title"><Wallet :size="17" aria-hidden="true" />每日结余</h2>
        <DailyAmountChart :days="daily" balance />
      </article>
      <article class="panel-card tdp-overview-panel">
        <h2 class="tdp-panel-title"><Coins :size="17" aria-hidden="true" />支出构成</h2>
        <CostBreakdown :summary="dashboard.summary" />
      </article>
      <article class="panel-card tdp-overview-panel">
        <h2 class="tdp-panel-title"><Printer :size="17" aria-hidden="true" />机器使用明细</h2>
        <ul class="hours-list" aria-label="按机号排列的使用工时" tabindex="0">
          <li v-for="m in machines" :key="m.machine_no">
            <span>#{{ m.machine_no }}</span>
            <span class="hours-track" aria-hidden="true"><i v-if="isAmount(m.hours) && maxHours > 0" :style="{ width: m.hours / maxHours * 100 + '%' }" /></span>
            <strong>{{ isAmount(m.hours) ? m.hours + ' 小时' : '—' }}</strong>
          </li>
        </ul>
        <p v-if="!machines.length" class="text-sm text-muted-foreground">该期间暂无机器工时</p>
      </article>
    </div>
    <details
      v-if="dashboard.network_health?.status !== 'healthy'"
      class="text-xs text-amber-800"
    >
      <summary>网络检测提示</summary>
      <p>
        检测状态：{{ dashboard.network_health?.status }}；未通过机号：{{
          dashboard.network_health?.failed_machine_numbers.join("、") || "无"
        }}。
      </p>
    </details>
  </section>
</template>
<style scoped>
.tdp-overview-toolbar label { font-size: 14px; font-weight: 650; }
.tdp-overview-panel { min-width: 0; padding: clamp(14px, 1.4vw, 21px); font-variant-numeric: tabular-nums; }
.tdp-panel-title { display: flex; align-items: center; gap: 8px; font-weight: 650; font-size: 15px; }
.tdp-panel-title svg { color: var(--tdp-brand); }
.hours-list { max-height: 245px; overflow-y: auto; scrollbar-width: thin; margin-top: 13px; padding-right: 5px; }
.hours-list li { display: grid; grid-template-columns: 36px 1fr 72px; align-items: center; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--tdp-border); font-size: 12px; }
.hours-list strong { text-align: right; font-weight: 600; }
.hours-track { height: 5px; border-radius: 5px; background: var(--muted); }
.hours-track i { display: block; height: 100%; background: var(--tdp-material); border-radius: inherit; }
.hours-list:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
</style>
