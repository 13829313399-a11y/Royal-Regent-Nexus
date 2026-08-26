<script setup lang="ts">
import { ArrowLeft, Blocks, Construction } from '@lucide/vue'
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { factoryContexts, isFactoryContextId } from '@/data/enterpriseMock'

const route = useRoute()

const factoryId = computed(() => {
  const value = String(route.query.factory ?? '')
  return isFactoryContextId(value) ? value : 'huaxing'
})

const factoryName = computed(() => (
  factoryContexts.find((factory) => factory.id === factoryId.value)?.shortName ?? '当前厂区'
))

const moduleCenterRoute = computed(() => ({
  path: '/modules/production',
  query: { factory: factoryId.value },
}))
</script>

<template>
  <main class="min-h-screen bg-slate-50 px-6 py-10 text-slate-900 sm:px-10 lg:px-16">
    <div class="mx-auto flex min-h-[calc(100vh-5rem)] max-w-4xl items-center justify-center">
      <section class="w-full rounded-3xl border border-slate-200 bg-white p-8 shadow-sm sm:p-12" aria-labelledby="rebuild-title">
        <div class="flex size-14 items-center justify-center rounded-2xl bg-teal-50 text-teal-700 ring-1 ring-inset ring-teal-100">
          <Construction class="size-7" aria-hidden="true" />
        </div>

        <p class="mt-8 text-sm font-semibold text-teal-700">{{ factoryName }} · 生产部</p>
        <h1 id="rebuild-title" class="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
          注塑排产中枢正在重构
        </h1>
        <p class="mt-4 max-w-2xl text-base leading-7 text-slate-600">
          原有排产页面已下线，当前入口暂不提供计划、导入、机台或模具操作。新的业务流程与界面完成后会从这里重新开放。
        </p>

        <div class="mt-8 flex flex-wrap gap-3">
          <RouterLink
            :to="moduleCenterRoute"
            class="inline-flex h-10 items-center gap-2 rounded-xl bg-teal-700 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
          >
            <ArrowLeft class="size-4" aria-hidden="true" />
            返回生产部模块中心
          </RouterLink>
          <span class="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 text-sm font-medium text-slate-600">
            <Blocks class="size-4" aria-hidden="true" />
            卡片入口已保留
          </span>
        </div>
      </section>
    </div>
  </main>
</template>
