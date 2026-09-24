<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Activity, CalendarDays, ChartColumn, Coins, Package, Printer, ReceiptText, Wallet } from '@lucide/vue';
import TdpButton from '../components/TdpButton.vue';
import { useWorkspaceContext } from "../context";
import type { ThreeDDashboard } from "@/types/threeDPrinting";
const {
  dashboard,
  dateFrom,
  dateTo,
  loadDashboard,
  todayText,
  money,
  printerMetrics,
} = useWorkspaceContext();
const period = ref("month");
const stats = computed(
  () =>
    (dashboard.value?.summary.legacyDisplay ||
      dashboard.value?.summary ||
      {}) as ThreeDDashboard["summary"],
);
type Day = {
  date: string;
  revenue: number;
  totalCost: number;
  balance: number;
};
type Machine = { machine_no: number; hours: number };
const daily = computed(() => (stats.value.daily as Day[]) || []);
const highlightedBalance = ref<Day | null>(null);
const selectedBalance = computed(() => highlightedBalance.value || daily.value.at(-1));
const firstMetrics = computed(() => [
  { label: '产值', display: money(stats.value.revenue), icon: ChartColumn },
  { label: '支出', display: money(stats.value.totalCost), icon: ReceiptText },
  { label: '结余', display: money(stats.value.balance), icon: Wallet },
  { label: '材料成本', display: money(stats.value.materialCost), icon: Package },
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
const max = computed(() =>
  Math.max(
    1,
    ...daily.value.flatMap((d) => [
      Math.abs(d.revenue),
      Math.abs(d.totalCost),
      Math.abs(d.balance),
    ]),
  ),
);
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
const costs = computed(
  () =>
    [
      ["材料", stats.value.materialCost],
      ["电费", stats.value.electricityCost],
      ["人工", stats.value.laborCost],
      ["维修", stats.value.maintenanceCost],
    ] as [string, number | undefined][],
);
</script>
<template>
  <section v-if="dashboard" class="space-y-5">
    <form class="legacy-toolbar tdp-overview-toolbar" @submit.prevent="apply">
      <strong>查看周期：</strong
      ><select v-model="period" @change="apply">
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
      <div v-for="metric in firstMetrics" :key="metric.label" class="metric-card">
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
      <article class="panel-card p-5">
        <h2 class="tdp-panel-title font-bold"><ChartColumn :size="17" aria-hidden="true" />产值与支出趋势</h2>
        <div class="legacy-chart">
          <div
            v-for="d in daily"
            :key="d.date"
            class="chart-column"
            :title="`${d.date} 产值 ${money(d.revenue)} 支出 ${money(d.totalCost)}`"
            :aria-label="`${d.date} 产值 ${money(d.revenue)}，支出 ${money(d.totalCost)}`"
            tabindex="0"
          >
            <div class="chart-pair">
              <i
                :style="{ height: `${Math.max(1, (d.revenue / max) * 150)}px` }"
              /><i
                class="expense"
                :style="{
                  height: `${Math.max(1, (d.totalCost / max) * 150)}px`,
                }"
              />
            </div>
            <small>{{ d.date.slice(5) }}</small>
          </div>
          <p v-if="!daily.length">该期间暂无生产记录</p>
        </div>
        <p class="text-xs text-slate-500">青绿色：产值　灰色：支出</p>
      </article>
      <article class="panel-card p-5">
        <h2 class="tdp-panel-title font-bold"><Wallet :size="17" aria-hidden="true" />每日结余</h2>
        <div class="legacy-chart">
          <div
            v-for="d in daily"
            :key="d.date"
            class="chart-column"
            :title="`${d.date} 结余 ${money(d.balance)}`"
            :aria-label="`${d.date} 结余 ${money(d.balance)}${d.balance < 0 ? '，负值' : ''}`"
            tabindex="0"
            @focus="highlightedBalance = d"
            @blur="highlightedBalance = null"
            @mouseenter="highlightedBalance = d"
            @mouseleave="highlightedBalance = null"
          >
            <div class="chart-pair">
              <i
                :class="{ negative: d.balance < 0 }"
                :style="{
                  height: `${Math.max(1, (Math.abs(d.balance) / max) * 150)}px`,
                }"
              />
            </div>
            <small>{{ d.date.slice(5) }}</small>
          </div>
          <p v-if="!daily.length">该期间暂无生产记录</p>
        </div>
        <p class="tdp-chart-note" v-if="selectedBalance">{{ selectedBalance.date }} 结余 {{ money(selectedBalance.balance) }} · 柱高表示金额绝对值<span v-if="daily.some(d => d.balance < 0)">，红色表示负结余</span></p>
      </article>
      <article class="panel-card p-5">
        <h2 class="tdp-panel-title font-bold mb-4"><Coins :size="17" aria-hidden="true" />支出构成</h2>
        <div v-for="[label, value] in costs" :key="label" class="mb-3">
          <div class="flex justify-between text-sm">
            <span>{{ label }}</span
            ><span>{{ money(value) }}</span>
          </div>
          <div class="machine-progress">
            <i
              :style="{
                width: `${(Number(value || 0) / Math.max(1, Number(stats.totalCost || 0))) * 100}%`,
              }"
            />
          </div>
        </div>
      </article>
      <article class="panel-card p-5">
        <h2 class="tdp-panel-title font-bold mb-4"><Printer :size="17" aria-hidden="true" />机器使用明细</h2>
        <div
          v-for="m in machines"
          :key="m.machine_no"
          class="flex justify-between border-b py-1 text-sm"
        >
          <span>#{{ m.machine_no }}</span
          ><span>{{ m.hours }} 小时</span>
        </div>
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
.legacy-chart {
  display: flex;
  gap: 7px;
  min-height: 210px;
  align-items: end;
  overflow-x: auto;
  padding: 15px 0;
}
.chart-column {
  min-width: 35px;
  flex: 1;
  text-align: center;
}
.chart-column:hover,
.chart-column:focus-visible { background: color-mix(in oklch, var(--accent) 60%, transparent); border-radius: 6px; outline: none; }
.chart-column:focus-visible { box-shadow: inset 0 0 0 2px var(--ring); }
.tdp-panel-title { display: flex; align-items: center; gap: 8px; color: var(--foreground); }
.tdp-panel-title svg { color: var(--primary); }
.tdp-chart-note { margin-top: 4px; font-size: 11px; color: var(--muted-foreground); font-variant-numeric: tabular-nums; }
.chart-pair {
  display: flex;
  gap: 2px;
  height: 155px;
  align-items: end;
  justify-content: center;
}
.chart-pair i {
  display: block;
  width: 12px;
  background: var(--primary);
  border-radius: 3px 3px 0 0;
}
.chart-pair .expense {
  background: var(--muted-foreground);
}
.chart-pair .negative { background: var(--color-red-700); }
.chart-column small {
  font-size: 9px;
  white-space: nowrap;
  color: var(--muted-foreground);
}
</style>
