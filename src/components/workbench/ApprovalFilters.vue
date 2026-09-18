<script setup lang="ts">
import { ChevronDown, RotateCcw, Search } from '@lucide/vue'
import { Button } from '@/components/ui/button'
</script>

<template>
  <section class="wb-filters enterprise-panel rounded-xl p-4 sm:p-5" aria-label="审批筛选条件">
    <div class="flex flex-wrap items-center gap-2.5">
      <div class="flex h-10 min-w-[240px] flex-1 items-center gap-2.5 rounded-lg border border-slate-200 bg-slate-50/80 px-3.5 text-sm text-slate-500 shadow-[inset_0_1px_2px_rgba(15,23,42,0.03)]">
        <Search class="size-4 shrink-0 text-slate-400" aria-hidden="true" />
        <span class="truncate">订单号 / 客户 / 合同号</span>
      </div>
      <Button type="button" variant="outline" size="lg">
        全部状态
        <ChevronDown class="size-3.5 text-slate-400" aria-hidden="true" />
      </Button>
      <Button type="button" variant="outline" size="lg">
        全部厂区
        <ChevronDown class="size-3.5 text-slate-400" aria-hidden="true" />
      </Button>
      <Button type="button" size="lg" class="px-7">
        查询
      </Button>
      <Button type="button" variant="ghost" size="lg">
        <RotateCcw class="size-3.5" aria-hidden="true" />
        重置
      </Button>
    </div>
  </section>
</template>
