<script setup lang="ts">
import { computed, ref, watch } from "vue";
const props = defineProps<{ page: number; total: number; size?: number; busy?: boolean }>();
const emit = defineEmits<{ change: [page: number] }>();
const pages = computed(() => Math.max(1, Math.ceil(props.total / (props.size || 50))));
const targetPage = ref<number | string>(props.page);
watch(() => props.page, (value) => { targetPage.value = value; });
function go(value: number | string) {
  if (props.busy || props.total === 0 || value === "" || !Number.isFinite(Number(value))) return;
  const page = Math.max(1, Math.min(pages.value, Math.trunc(Number(value))));
  targetPage.value = page;
  if (page !== props.page) emit("change", page);
}
</script>
<template>
  <nav
    aria-label="列表分页"
    class="my-3 flex flex-wrap items-center justify-between gap-3 text-sm"
  >
    <span
      >共 {{ total }} 条 · 第 {{ page }} /
      {{ pages }} 页</span
    >
    <div class="flex flex-wrap items-center gap-2">
      <button type="button" :disabled="busy || page <= 1" @click="go(1)">首页</button>
      <button
        type="button"
        :disabled="busy || page <= 1"
        @click="go(page - 1)"
      >
        上一页</button
      ><button
        type="button"
        :disabled="busy || page * (size || 50) >= total"
        @click="go(page + 1)"
      >
        下一页
      </button>
      <button type="button" :disabled="busy || page >= pages" @click="go(pages)">末页</button>
      <label class="pagination-jump">
        到第
        <input v-model="targetPage" type="number" min="1" :max="pages" step="1"
          aria-label="跳转页码" :disabled="busy || total === 0"
          class="pagination-input"
          @keydown.enter.prevent="go(targetPage)" />
        页
      </label>
      <button type="button" :disabled="busy || total === 0" @click="go(targetPage)">跳转</button>
    </div>
  </nav>
</template>
<style scoped>
.pagination-jump { display: inline-flex; align-items: center; gap: 8px; white-space: nowrap; }
.pagination-input { width: 72px; margin: 0; padding: 6px 8px; text-align: center; }
button {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--card);
  color: var(--foreground);
}
button:hover:not(:disabled) { background: var(--accent); color: var(--accent-foreground); }
button:disabled { opacity: .4; cursor: not-allowed; }
</style>
