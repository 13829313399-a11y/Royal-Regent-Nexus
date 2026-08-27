<script setup lang="ts">
import { ShieldCheck } from '@lucide/vue'
</script>

<template>
  <div class="rounded-xl border border-slate-200 bg-slate-50 p-3">
    <div class="flex items-center gap-2 text-sm font-semibold text-slate-800"><ShieldCheck class="size-4 text-teal-700" aria-hidden="true" />本地确定性处理</div>
    <p class="mt-1.5 text-xs leading-5 text-slate-600">由 LibreOffice 在本地生成 PDF；缺失字体会使用替代字体并在结果中提示。</p>
  </div>
</template>
