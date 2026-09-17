<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { ThreeDMaterial, ThreeDSettings } from "@/types/threeDPrinting";
import { calculateQuote, type QuoteInput } from "../quote";
const props = defineProps<{
  modelValue: number;
  input: QuoteInput;
  settings?: ThreeDSettings;
  materials: ThreeDMaterial[];
  snapshot?: Record<string, unknown>;
  existing?: boolean;
}>();
const emit = defineEmits<{ "update:modelValue": [value: number] }>();
const manual = ref(false);
const preserved = ref(!!props.existing);
const quote = computed(() =>
  calculateQuote(props.input, props.settings, props.materials, props.snapshot),
);
const money = (n: number) => `¥${n.toFixed(2)}`;
function apply() {
  if (!quote.value) return;
  manual.value = false;
  preserved.value = false;
  emit("update:modelValue", Number(quote.value.unit.toFixed(2)));
}
// Opening an existing record never silently changes its saved price.
watch(
  [
    () => props.input.material,
    () => props.input.weight,
    () => props.input.hours,
    () => props.input.quantity,
    () => props.input.designFee,
  ],
  () => {
    if (!manual.value) apply();
  },
);
function enter(event: Event) {
  manual.value = true;
  preserved.value = false;
  emit("update:modelValue", Number((event.target as HTMLInputElement).value));
}
</script>
<template>
  <section class="quote-editor" aria-label="自动报价">
    <div class="quote-heading">
      <div>
        <strong>报价计算</strong>
        <p>
          {{
            preserved
              ? "已保留原单价，修改计价数据后自动更新。"
              : manual
                ? "当前为手填单价，可随时重新使用公式。"
                : "修改材料、单件重量或时间，自动生成单价。"
          }}
        </p>
      </div>
      <button
        type="button"
        class="action-button secondary"
        :disabled="!quote"
        @click="apply"
      >
        按公式重新计算
      </button>
    </div>
    <div class="quote-values">
      <label
        >单件报价（元，不含设计费）<input
          aria-label="单件报价"
          :value="modelValue"
          type="number"
          min="0"
          step="0.01"
          required
          @input="enter"
      /></label>
      <div aria-live="polite">
        <span>公式参考合计 · {{ input.quantity }} 件</span
        ><strong>{{ quote ? money(quote.total) : "待补齐计价信息" }}</strong
        ><small
          >含本条记录设计费
          {{ money(Number(input.designFee) || 0) }}，只收取一次</small
        >
      </div>
    </div>
    <template v-if="quote">
      <div class="quote-breakdown">
        <span
          >单件材料 <b>{{ money(quote.material) }}</b></span
        ><span
          >单件电费 <b>{{ money(quote.electricity) }}</b></span
        ><span
          >单件人工 <b>{{ money(quote.labor) }}</b></span
        ><span
          >利润加成 <b>{{ quote.profitRate }}%</b></span
        >
      </div>
      <p class="quote-note">
        单价 =（材料 + 电费 + 人工）×（1 + 利润加成）；合计 = 单价 × 数量 +
        设计费。按 12 小时分摊电费和人工，使用{{ quote.basis }}。计算保留原始精度，合计最后四舍五入。
      </p>
    </template>
    <p v-else class="quote-note" role="status">
      {{
        snapshot !== undefined
          ? "这条历史记录缺少对应材料的保存费率，暂不能自动计算。原报价保留，可手动填写。"
          : "请选择已登记价格的材料，并填写有效的重量、时间和数量。"
      }}
    </p>
  </section>
</template>
<style scoped>
.quote-editor {
  grid-column: 1/-1;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--muted);
  padding: 18px;
  color: var(--foreground);
}
.quote-heading,
.quote-values {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: center;
}
.quote-heading p,
.quote-note,
small {
  font-size: 12px;
  color: var(--muted-foreground);
  line-height: 1.7;
}
.quote-heading p {
  margin: 4px 0;
}
.quote-values {
  margin: 16px 0;
  align-items: flex-start;
}
.quote-values label {
  flex: 1;
  max-width: 320px;
}
.quote-values > div {
  display: grid;
  gap: 4px;
  flex: 1;
}
.quote-values > div > strong {
  font-size: 26px;
  color: var(--primary);
  font-variant-numeric: tabular-nums;
}
.quote-values span {
  font-size: 13px;
}
.quote-breakdown {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 13px;
}
.quote-breakdown span {
  background: var(--background);
  padding: 8px 12px;
  border-radius: 8px;
}
.quote-note {
  margin: 12px 0 0;
}
@media (max-width: 600px) {
  .quote-heading,
  .quote-values {
    flex-direction: column;
    gap: 12px;
  }
  .quote-values label {
    width: 100%;
    max-width: none;
  }
}
</style>
