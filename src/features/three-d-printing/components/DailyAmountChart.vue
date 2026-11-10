<script setup lang="ts">
import { computed, ref, useId } from "vue";
import { currency, isAmount, type ChartDay } from "../dashboardPresentation";

const props = defineProps<{ days: ChartDay[]; balance?: boolean }>();
const keyboardHint = useId();
const activeDate = ref("");
const focusedDate = ref("");
const series = computed(() => props.balance
  ? [{ key: "balance", label: "结余" }] as const
  : [{ key: "revenue", label: "产值" }, { key: "totalCost", label: "支出" }] as const);
const selected = computed(() => props.days.find(d => d.date === (activeDate.value || focusedDate.value)) ?? props.days.at(-1));
const selectedText = (day: ChartDay) => day.date + " · " + series.value.map(s => s.label + " " + currency(day[s.key])).join("　");

function axisLimit(value: number) {
  if (!value) return 0;
  const unit = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / unit) * unit;
}
const scale = computed(() => {
  let high = 0, low = 0;
  for (const day of props.days) {
    for (const { key } of series.value) {
      const value = day[key];
      if (isAmount(value)) { high = Math.max(high, value); low = Math.min(low, value); }
    }
  }
  if (!high && !low) return props.balance ? { high: 1, low: -1 } : { high: 1, low: 0 };
  // Leave room to label both signs, even when the losses are much smaller.
  return { high: high ? axisLimit(Math.max(high, -low / 4)) : 0,
    low: low ? -axisLimit(Math.max(-low, high / 4)) : 0 };
});
function y(n: number) {
  return (scale.value.high - n) / (scale.value.high - scale.value.low) * 100;
}
const ticks = computed(() => {
  const { high, low } = scale.value;
  return high && low ? [high, 0, low] : [high, (high + low) / 2, low];
});
const axisNumber = new Intl.NumberFormat("zh-CN", { notation: "compact", maximumSignificantDigits: 3 });
function barStyle(value: number) {
  return { top: Math.min(y(0), y(value)) + "%", height: Math.abs(y(value) - y(0)) + "%" };
}
function move(event: KeyboardEvent, index: number) {
  const buttons = (event.currentTarget as HTMLElement).parentElement?.querySelectorAll("button");
  if (!buttons?.length) return;
  const next = { ArrowLeft: index - 1, ArrowRight: index + 1, Home: 0, End: buttons.length - 1 }[event.key];
  if (next === undefined) return;
  event.preventDefault();
  buttons[Math.min(buttons.length - 1, Math.max(0, next))]?.focus();
}
</script>
<template>
  <div class="amount-chart">
    <div class="chart-key">
      <span>金额（元）</span>
      <span v-if="balance"><i class="income" />盈利 <i class="loss" />亏损</span>
      <span v-else><i class="income" />产值 <i class="expense" />支出</span>
    </div>
    <p v-if="!days.length" class="chart-empty">该期间暂无生产记录</p>
    <template v-else>
      <span :id="keyboardHint" class="sr-only">使用左右方向键切换日期，Home 和 End 可移至首日或末日。</span>
      <div class="plot">
        <div class="axis" aria-hidden="true">
          <small v-for="tick in ticks" :key="tick" :style="{ top: y(tick) + '%' }">{{ axisNumber.format(tick) }}</small>
        </div>
        <div class="plot-scroll">
          <div class="plot-days" :style="{ minWidth: days.length * 42 + 'px' }">
            <span v-for="tick in ticks" :key="tick" class="grid-line" :class="{ zero: tick === 0 }" :style="{ top: y(tick) + '%' }" aria-hidden="true" />
            <button v-for="(day, index) in days" :key="day.date" type="button" class="chart-day"
              :tabindex="day.date === (focusedDate || days.at(-1)?.date) ? 0 : -1" :aria-describedby="keyboardHint"
              :aria-label="selectedText(day)" :title="selectedText(day)" @keydown="move($event, index)"
              @focus="focusedDate = day.date; activeDate = ''" @blur="focusedDate = ''" @click="focusedDate = day.date"
              @mouseenter="activeDate = day.date" @mouseleave="activeDate = ''">
              <span v-for="s in series" :key="s.key" class="bar-lane">
                <i v-if="isAmount(day[s.key])" class="bar" :class="{ expense: s.key === 'totalCost', loss: s.key === 'balance' && day.balance < 0, mark: day[s.key] === 0 }" :style="barStyle(day[s.key])" />
              </span>
              <small>{{ day.date.slice(5) }}</small>
            </button>
          </div>
        </div>
      </div>
      <p class="chart-value">{{ selected && selectedText(selected) }}</p>
    </template>
  </div>
</template>
<style scoped>
.amount-chart { color: var(--tdp-muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.chart-key, .chart-key span { display: flex; align-items: center; gap: 5px; }
.chart-key { justify-content: space-between; gap: 12px; margin: 8px 0 14px; }
.chart-key i { width: 8px; height: 8px; border-radius: 2px; margin-left: 7px; }
.income, .bar { background: var(--tdp-brand); }
.expense { background: var(--tdp-electricity); }
.loss { background: var(--destructive); }
.plot { display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 8px; }
.axis { height: 140px; margin-top: 7px; position: relative; }
.axis small { position: absolute; transform: translateY(-50%); right: 0; white-space: nowrap; font-size: 10px; }
.plot-scroll { overflow-x: auto; scrollbar-width: thin; padding: 7px 2px 24px; }
.plot-days { height: 140px; display: flex; position: relative; }
.grid-line { position: absolute; width: 100%; border-top: 1px dashed var(--tdp-border); pointer-events: none; }
.grid-line.zero { border-top: 1px solid var(--tdp-muted); }
.chart-day { position: relative; min-width: 0; flex: 1; display: flex; gap: 3px; justify-content: center; padding: 0; border-radius: 4px; }
.chart-day:hover, .chart-day:focus-visible { background: color-mix(in oklch, var(--accent) 45%, transparent); }
.chart-day:focus-visible { outline: 2px solid var(--ring); outline-offset: 0; }
.bar-lane { width: min(28%, 15px); height: 100%; position: relative; pointer-events: none; }
.bar { display: block; position: absolute; width: 100%; border-radius: 3px 3px 0 0; }
.bar.loss { border-radius: 0 0 3px 3px; }
.bar.mark { border-top: 2px solid var(--tdp-muted); }
.chart-day small { position: absolute; top: calc(100% + 4px); font-size: 10px; white-space: nowrap; }
.chart-value { min-height: 18px; margin-top: 7px; color: var(--tdp-text); overflow-wrap: anywhere; }
.chart-empty { display: grid; min-height: 160px; place-items: center; }
</style>
