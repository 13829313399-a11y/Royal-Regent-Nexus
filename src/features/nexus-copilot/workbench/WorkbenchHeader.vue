<script setup lang="ts">
import { ArrowLeft, Bot, ShieldCheck } from '@lucide/vue'
import { RouterLink } from 'vue-router'

defineProps<{
  factoryLabel: string
}>()
</script>

<template>
  <header class="flex shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
    <RouterLink
      to="/"
      class="flex size-9 items-center justify-center rounded-xl text-slate-500 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
      aria-label="返回业务首页"
    >
      <ArrowLeft class="size-4" aria-hidden="true" />
    </RouterLink>
    <span class="flex size-10 items-center justify-center rounded-2xl bg-slate-950 text-white" aria-hidden="true">
      <Bot class="size-5" />
    </span>
    <div class="min-w-0 flex-1">
      <h1 class="text-base font-bold">Nexus AI 工作台</h1>
      <p class="mt-0.5 flex items-center gap-1 text-[11px] text-slate-500">
        <ShieldCheck class="size-3 text-emerald-600" aria-hidden="true" />
        上下文和正式业务事实每次请求都按当前权限重新验证
      </p>
    </div>
    <slot />
    <span class="hidden text-xs text-slate-500 sm:inline">{{ factoryLabel }}厂区</span>
  </header>
</template>
