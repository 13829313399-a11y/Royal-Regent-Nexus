<script setup lang="ts">
import { ref, watch } from "vue";
import { threeDPrintingApi } from "@/api/threeDPrinting";
import { getApiErrorMessage } from "@/lib/http";
import type { ThreeDProduct } from "@/types/threeDPrinting";
const props = defineProps<{ modelValue: string }>();
const emit = defineEmits<{
  "update:modelValue": [string];
  selected: [ThreeDProduct];
}>();
const query = ref(""),
  items = ref<ThreeDProduct[]>([]),
  message = ref("");
let generation = 0;
const selectedProduct = ref<ThreeDProduct>();
watch(
  () => props.modelValue,
  async (id) => {
    if (!id || items.value.some((item) => item.id === id)) return;
    try {
      const result = await threeDPrintingApi.collection<ThreeDProduct>(
        "products",
        { q: id, page_size: 50 },
      );
      if (props.modelValue === id)
        selectedProduct.value = result.items.find((item) => item.id === id);
    } catch (error) {
      message.value = getApiErrorMessage(error);
    }
  },
  { immediate: true },
);
async function search() {
  const current = ++generation;
  try {
    const result = await threeDPrintingApi.collection<ThreeDProduct>(
      "products",
      { q: query.value, page_size: 50 },
    );
    if (current !== generation) return;
    items.value = result.items;
    message.value =
      result.total > 50
        ? "结果超过50条，请输入更完整的名称"
        : `${result.total}个产品`;
  } catch (error) {
    message.value = getApiErrorMessage(error);
  }
}
function select(event: Event) {
  const id = (event.target as HTMLSelectElement).value;
  emit("update:modelValue", id);
  const item = items.value.find((i) => i.id === id);
  if (item) emit("selected", item);
}
</script>
<template>
  <div class="space-y-1">
    <div class="flex gap-1">
      <input
        v-model="query"
        aria-label="查询产品名称"
        placeholder="输入名称查询所有产品"
        @keydown.enter.prevent="search"
      /><button
        type="button"
        class="shrink-0 rounded border px-2"
        @click="search"
      >
        查找
      </button>
    </div>
    <select :value="modelValue" aria-label="选择产品" @change="select">
      <option value="">手工填写 / 请选择</option>
      <option
        v-if="modelValue && !items.some((i) => i.id === modelValue)"
        :value="modelValue"
      >
        {{
          selectedProduct?.id === modelValue
            ? selectedProduct.name
            : "已关联产品"
        }}
      </option>
      <option v-for="item in items" :key="item.id" :value="item.id">
        {{ item.name }} · {{ item.customer }}
      </option></select
    ><small role="status">{{ message }}</small>
  </div>
</template>
