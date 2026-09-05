<script setup lang="ts">
defineProps<{ page: number; total: number; size?: number; busy?: boolean }>();
defineEmits<{ change: [page: number] }>();
</script>
<template>
  <nav
    aria-label="列表分页"
    class="my-3 flex items-center justify-between gap-3 text-sm"
  >
    <span
      >共 {{ total }} 条 · 第 {{ page }} /
      {{ Math.max(1, Math.ceil(total / (size || 50))) }} 页</span
    >
    <div class="flex gap-3">
      <button
        type="button"
        :disabled="busy || page <= 1"
        @click="$emit('change', page - 1)"
      >
        上一页</button
      ><button
        type="button"
        :disabled="busy || page * (size || 50) >= total"
        @click="$emit('change', page + 1)"
      >
        下一页
      </button>
    </div>
  </nav>
</template>
