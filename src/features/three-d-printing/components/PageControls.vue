<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, ArrowRight } from '@lucide/vue';
import TdpButton from './TdpButton.vue';
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
    :aria-busy="busy || undefined"
    class="tdp-pagination my-3 flex flex-wrap items-center justify-between gap-3 text-sm"
  >
    <span
      >共 {{ total }} 条 · 第 {{ page }} /
      {{ pages }} 页</span
    >
    <div class="flex flex-wrap items-center gap-2">
      <TdpButton tone="secondary" :disabled="busy || page <= 1" @click="go(1)"><template #icon><ChevronsLeft :size="15" /></template>首页</TdpButton>
      <TdpButton tone="secondary"
        :disabled="busy || page <= 1"
        @click="go(page - 1)"
      >
        <template #icon><ChevronLeft :size="15" /></template>上一页</TdpButton><TdpButton tone="secondary"
        :disabled="busy || page * (size || 50) >= total"
        @click="go(page + 1)"
      >
        下一页<template #icon><ChevronRight :size="15" /></template>
      </TdpButton>
      <TdpButton tone="secondary" :disabled="busy || page >= pages" @click="go(pages)"><template #icon><ChevronsRight :size="15" /></template>末页</TdpButton>
      <label class="pagination-jump">
        到第
        <input v-model="targetPage" type="number" min="1" :max="pages" step="1"
          aria-label="跳转页码" :disabled="busy || total === 0"
          class="pagination-input"
          @keydown.enter.prevent="go(targetPage)" />
        页
      </label>
      <TdpButton tone="soft" :disabled="busy || total === 0" @click="go(targetPage)"><template #icon><ArrowRight :size="15" /></template>跳转</TdpButton>
    </div>
    <span v-if="busy" class="tdp-pagination-progress" aria-hidden="true" />
  </nav>
</template>
<style scoped>
.pagination-jump { display: inline-flex; align-items: center; gap: 8px; white-space: nowrap; }
.pagination-input { width: 72px; margin: 0; padding: 6px 8px; text-align: center; }
.tdp-pagination { position: relative; padding: 0 12px 8px; font-variant-numeric: tabular-nums; }
.tdp-pagination-progress { position: absolute; left: 12px; right: 12px; bottom: 0; height: 2px; overflow: hidden; background: var(--accent); }
.tdp-pagination-progress::after { content: ''; display: block; width: 28%; height: 100%; background: var(--primary); animation: tdp-pagination-loading 900ms ease-in-out infinite alternate; }
@keyframes tdp-pagination-loading { to { transform: translateX(250%); } }
@media (prefers-reduced-motion: reduce) { .tdp-pagination-progress::after { animation: none; width: 100%; } }
</style>
