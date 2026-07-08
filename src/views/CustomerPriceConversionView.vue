<script setup lang="ts">
import { ArrowLeft } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import QuoteCenterPanel from '@/components/modules/sales/QuoteCenterPanel.vue'
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center gap-2 text-sm text-slate-500">
      <RouterLink
        to="/modules/sales-business/quote-center"
        class="inline-flex items-center gap-2 text-slate-600 hover:text-slate-950"
      >
        <ArrowLeft class="size-4" aria-hidden="true" />
        返回报价与成本中心
      </RouterLink>
      <span>/</span>
      <span>客价转换台</span>
    </div>

    <QuoteCenterPanel />
  </div>
</template>
