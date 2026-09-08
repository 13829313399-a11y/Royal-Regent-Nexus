<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { http, getApiErrorMessage } from "@/lib/http";
import { threeDPrintingApi } from "@/api/threeDPrinting";
import type {
  ThreeDProductionRecord,
  ThreeDProduct,
} from "@/types/threeDPrinting";

const props = withDefaults(
  defineProps<{
    modelValue: string | string[];
    kind: "records" | "spool" | "file" | "products";
    multiple?: boolean;
    state?: string;
    productId?: string;
  }>(),
  { multiple: false, state: "", productId: "" },
);
const emit = defineEmits<{ "update:modelValue": [string | string[]] }>();
type Choice = { id: string; label: string };
const query = ref(""),
  choices = ref<Choice[]>([]),
  selectedLabels = ref<Record<string, string>>({});
const message = ref(""),
  busy = ref(false);
const title = computed(
  () =>
    ({ records: "生产记录", spool: "卷材", file: "附件", products: "产品" })[
      props.kind
    ],
);
const selected = computed(() =>
  Array.isArray(props.modelValue)
    ? props.modelValue
    : props.modelValue
      ? [props.modelValue]
      : [],
);
let generation = 0;
async function search() {
  const current = ++generation;
  busy.value = true;
  try {
    let result: { items: Choice[]; total: number };
    if (props.kind === "records") {
      const data = await threeDPrintingApi.collection<ThreeDProductionRecord>(
        "records",
        {
          q: query.value,
          state: props.state,
          product_id: props.productId,
          page_size: 50,
        },
      );
      result = {
        total: data.total,
        items: data.items.map((r) => ({
          id: r.id,
          label: `${r.business_date} · ${r.machine_no}号机 · ${r.product_name || r.gcode_file || "未匹配任务"} · ${r.quantity}件`,
        })),
      };
    } else if (props.kind === "products") {
      const data = await threeDPrintingApi.collection<ThreeDProduct>(
        "products",
        { q: query.value, page_size: 50 },
      );
      result = {
        total: data.total,
        items: data.items.map((r) => ({
          id: r.id,
          label: `${r.name} · ${r.customer}`,
        })),
      };
    } else {
      const { data } = await http.get(
        `/three-d-printing/operations/resources/${props.kind}`,
        { params: { q: query.value, page_size: 50 } },
      );
      result = {
        total: data.total,
        items: data.items.map(
          (r: {
            id: string;
            resource_key: string;
            data: Record<string, unknown>;
          }) => ({
            id: r.id,
            label:
              props.kind === "file"
                ? String(r.data.name)
                : `${r.resource_key} · ${r.data.material} · 批次${r.data.lot} · ${r.data.remaining_g}g`,
          }),
        ),
      };
    }
    if (current !== generation) return;
    choices.value = result.items;
    for (const item of result.items) selectedLabels.value[item.id] = item.label;
    message.value =
      result.total > 50
        ? `共${result.total}条，请输入名称缩小范围`
        : `${result.total}条结果`;
  } catch (error) {
    if (current === generation) message.value = getApiErrorMessage(error);
  } finally {
    if (current === generation) busy.value = false;
  }
}
function choose(event: Event) {
  const value = (event.target as HTMLSelectElement).value;
  emit(
    "update:modelValue",
    props.multiple
      ? [...new Set([...selected.value, value].filter(Boolean))]
      : value,
  );
}
watch(() => [props.kind, props.state, props.productId], search, {
  immediate: true,
});
</script>
<template>
  <div class="min-w-0 space-y-2">
    <div class="flex gap-2">
      <input
        v-model="query"
        :aria-label="`搜索${title}`"
        :placeholder="`按名称搜索${title}`"
        @keydown.enter.prevent="search"
      />
      <button
        type="button"
        class="shrink-0 rounded border px-3"
        :disabled="busy"
        @click="search"
      >
        查找
      </button>
    </div>
    <select
      :value="multiple ? '' : modelValue"
      :aria-label="`选择${title}`"
      @change="choose"
    >
      <option value="">{{ multiple ? `添加${title}` : `选择${title}` }}</option>
      <option
        v-if="
          !multiple && modelValue && !choices.some((c) => c.id === modelValue)
        "
        :value="String(modelValue)"
      >
        已关联{{ title }}
      </option>
      <option v-for="item in choices" :key="item.id" :value="item.id">
        {{ item.label }}
      </option>
    </select>
    <div v-if="multiple" class="flex flex-wrap gap-2">
      <button
        v-for="id in selected"
        :key="id"
        type="button"
        class="max-w-full break-words rounded bg-teal-50 px-2 py-1 text-left text-sm text-teal-900"
        @click="
          emit(
            'update:modelValue',
            selected.filter((v) => v !== id),
          )
        "
      >
        {{ selectedLabels[id] || `已关联${title}` }} ×
      </button>
    </div>
    <small role="status">{{ busy ? "查询中…" : message }}</small>
  </div>
</template>
