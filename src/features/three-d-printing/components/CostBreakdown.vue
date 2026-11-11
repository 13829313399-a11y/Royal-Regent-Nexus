<script setup lang="ts">
import { computed, ref } from "vue";
import { costComposition, currency, isAmount, type Summary } from "../dashboardPresentation";
const props = defineProps<{ summary: Summary }>();
const cost = computed(() => costComposition(props.summary));
const selected = ref("");
const share = (pct: number) => pct > 0 && pct < 0.1 ? "<0.1%" : pct.toFixed(1) + "%";
</script>
<template>
  <div class="breakdown">
    <div class="cost-body">
      <div class="cost-ring">
        <svg viewBox="0 0 160 160" aria-hidden="true">
          <circle class="ring-track" cx="80" cy="80" r="65" />
          <template v-for="item in cost.items" :key="item.key">
            <circle v-if="item.arc > 0" cx="80" cy="80" r="65" pathLength="100"
              :stroke="item.color" :stroke-dasharray="item.arc + ' ' + (100 - item.arc)" :stroke-dashoffset="-item.start"
              :class="{ highlighted: selected === item.key }" transform="rotate(-90 80 80)" />
          </template>
        </svg>
        <div class="ring-center"><span>支出合计</span><strong>{{ currency(cost.total) }}</strong></div>
      </div>
      <ul class="cost-list" aria-label="费用金额与占比">
        <li v-for="item in cost.items" :key="item.key" tabindex="0"
          @focus="selected = item.key" @blur="selected = ''" @mouseenter="selected = item.key" @mouseleave="selected = ''">
          <i :style="{ background: item.color }" aria-hidden="true" /><span>{{ item.label }}</span>
          <strong>{{ currency(item.value) }}</strong><small v-if="item.percent !== undefined">{{ share(item.percent) }}</small>
        </li>
      </ul>
    </div>
    <p v-if="cost.mode !== 'ready'" class="cost-message">{{ cost.mode === "empty" ? "该期间暂无支出" : "暂无法形成占比" }}</p>
    <p v-if="cost.legacy" class="cost-basis"><strong>维修 {{ currency(cost.maintenance) }}</strong>维修费用另列，未计入本页经营支出。</p>
    <p v-else class="cost-basis">按记录冻结成本汇总，含维修费用。</p>
    <p v-if="isAmount(cost.incomplete) && cost.incomplete > 0" class="cost-pending">{{ cost.incomplete }} 条记录的成本待核对</p>
  </div>
</template>
<style scoped>
.cost-body { display: flex; align-items: center; justify-content: space-around; flex-wrap: wrap; gap: 12px 18px; margin: 14px 0; }
.cost-ring { position: relative; width: clamp(126px, 12vw, 170px); flex: none; }
.cost-ring svg { width: 100%; display: block; fill: none; stroke-width: 17; }
.ring-track { stroke: var(--muted); }
.highlighted { stroke-width: 20; }
.ring-center { position: absolute; inset: 21%; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; overflow-wrap: anywhere; }
.ring-center span, .cost-basis, .cost-pending, .cost-list small { font-size: 11px; color: var(--tdp-muted); }
.ring-center strong { font-size: clamp(14px, 1.4vw, 21px); line-height: 1.2; margin-top: 4px; letter-spacing: -.03em; }
.cost-list { flex: 1 1 158px; max-width: 390px; }
.cost-list li { display: grid; grid-template-columns: 8px minmax(2em,1fr) auto; gap: 0 8px; align-items: center; padding: 6px 8px; border-radius: 6px; font-size: 13px; }
.cost-list i { width: 8px; height: 8px; border-radius: 2px; }
.cost-list small { grid-column: 3; text-align: right; }
.cost-list li:hover, .cost-list li:focus-visible { background: var(--tdp-surface-inset); }
.cost-list li:focus-visible { outline: 2px solid var(--ring); }
.cost-basis { border-top: 1px solid var(--tdp-border); padding-top: 11px; }
.cost-basis strong { color: var(--tdp-text); margin-right: 9px; white-space: nowrap; }
.cost-message { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.cost-pending { margin-top: 3px; }
</style>
