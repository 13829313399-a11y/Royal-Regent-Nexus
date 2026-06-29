<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import { ArrowLeft } from '@lucide/vue'
import { useRoute } from 'vue-router'
import {
  factoryContexts,
  getMoldingSampleRecord,
  isProductionFactoryContextId,
  productionFactoryContextIds,
  type ProductionFactoryContextId,
  type Tone,
} from '@/data/enterpriseMock'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const appStore = useAppStore()

const toneClasses: Record<Tone, string> = {
  teal: 'border-teal-100 bg-teal-50 text-teal-800',
  blue: 'border-blue-100 bg-blue-50 text-blue-800',
  amber: 'border-amber-100 bg-amber-50 text-amber-800',
  red: 'border-red-100 bg-red-50 text-red-800',
  slate: 'border-slate-200 bg-slate-50 text-slate-800',
  green: 'border-emerald-100 bg-emerald-50 text-emerald-800',
}

const factoryTabs = computed(() => factoryContexts.filter((factory) =>
  productionFactoryContextIds.includes(factory.id as ProductionFactoryContextId),
))
const selectedFactoryId = computed(() => {
  const routeFactory = route.query.factory

  return typeof routeFactory === 'string' && isProductionFactoryContextId(routeFactory)
    ? routeFactory
    : appStore.activeProductionFactory.id
})
const activeFactory = computed(() =>
  factoryContexts.find((factory) => factory.id === selectedFactoryId.value) ?? factoryContexts[1],
)
const activeRecord = computed(() => getMoldingSampleRecord(selectedFactoryId.value))
const activeOrder = computed(() => activeRecord.value.order)
const activeLines = computed(() => activeRecord.value.lines)
const activeStages = computed(() => activeRecord.value.stages)
const totalQuantity = computed(() => activeLines.value.reduce((sum, line) => sum + line.quantity, 0))
const riskCount = computed(() => activeLines.value.filter((line) => line.statusTone === 'red').length)
const colorCount = computed(() => new Set(activeLines.value.map((line) => line.color)).size)
const summaryCards = computed(() => [
  { label: '厂区', value: activeFactory.value.shortName, detail: activeFactory.value.description, tone: activeFactory.value.tone },
  { label: '啤办单', value: activeOrder.value.productNo, detail: `${activeOrder.value.customer} · ${activeOrder.value.productName}`, tone: 'teal' as Tone },
  { label: '明细行', value: String(activeLines.value.length), detail: '按模具与颜色拆分', tone: 'blue' as Tone },
  { label: '需办日期', value: activeOrder.value.requiredDate.slice(5), detail: `落单 ${activeOrder.value.requestDate}`, tone: 'amber' as Tone },
])

watchEffect(() => {
  if (selectedFactoryId.value !== appStore.activeFactoryId) {
    appStore.setActiveFactory(selectedFactoryId.value)
  }
})
</script>

<template>
  <main class="min-h-screen bg-slate-100 px-4 py-6 text-slate-950 sm:px-6 xl:px-10">
    <div class="space-y-6">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <RouterLink
          to="/modules"
          class="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-950"
        >
          <ArrowLeft class="size-4" aria-hidden="true" />
          工程部模块
        </RouterLink>
        <h1 class="mt-3 text-3xl font-semibold tracking-tight text-slate-950">啤办进度追踪</h1>
        <p class="mt-2 text-sm text-slate-600">
          {{ activeFactory.name }} · {{ activeOrder.source }} · {{ activeOrder.customer }} · {{ activeOrder.productNo }} {{ activeOrder.productName }}
        </p>
        <div class="mt-4 flex flex-wrap gap-2">
          <RouterLink
            v-for="factory in factoryTabs"
            :key="factory.id"
            :to="{ path: '/modules/molding-sample', query: { factory: factory.id } }"
            class="rounded-lg border px-4 py-2 text-sm font-semibold transition-colors"
            :class="factory.id === selectedFactoryId
              ? 'border-teal-700 bg-teal-700 text-white'
              : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'"
          >
            {{ factory.shortName }}
          </RouterLink>
        </div>
      </div>

      <div class="grid grid-cols-3 gap-3 text-center">
        <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
          <p class="text-xs text-slate-500">目标啤数</p>
          <p class="mt-1 text-lg font-semibold text-slate-950">{{ totalQuantity }}</p>
        </div>
        <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
          <p class="text-xs text-slate-500">颜色数</p>
          <p class="mt-1 text-lg font-semibold text-slate-950">{{ colorCount }}</p>
        </div>
        <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
          <p class="text-xs text-slate-500">风险项</p>
          <p class="mt-1 text-lg font-semibold text-red-700">{{ riskCount }}</p>
        </div>
      </div>
      </div>

      <div class="grid gap-4 md:grid-cols-4">
      <article
        v-for="item in summaryCards"
        :key="item.label"
        class="rounded-lg border bg-white p-4"
        :class="toneClasses[item.tone]"
      >
        <p class="text-xs font-medium opacity-80">{{ item.label }}</p>
        <p class="mt-2 text-2xl font-semibold">{{ item.value }}</p>
        <p class="mt-1 text-xs opacity-80">{{ item.detail }}</p>
      </article>
      </div>

      <div class="grid gap-6 xl:grid-cols-[360px_1fr]">
      <SectionPanel title="开发方向" subtitle="按啤办通知单落成可追踪的现场流程">
        <div class="space-y-4">
          <article
            v-for="stage in activeStages"
            :key="stage.label"
            class="rounded-lg border border-slate-200 bg-slate-50 p-4"
          >
            <div class="flex items-center justify-between gap-3">
              <h3 class="font-semibold text-slate-950">{{ stage.label }}</h3>
              <StatusPill :label="stage.status" :tone="stage.tone" compact />
            </div>
            <p class="mt-2 text-sm leading-6 text-slate-600">{{ stage.detail }}</p>
          </article>
        </div>

        <div class="mt-5 rounded-lg border border-amber-100 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
          {{ activeOrder.note }}
        </div>
      </SectionPanel>

      <SectionPanel title="啤办明细进度" subtitle="由 Excel 表头字段拆分：模具、用料、颜色、PMS、色粉、啤数、交期、状态">
        <div class="overflow-hidden rounded-lg border border-slate-200">
          <div class="overflow-x-auto">
            <table class="min-w-[980px] divide-y divide-slate-200 text-sm">
              <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                <tr>
                  <th class="px-4 py-3">单号</th>
                  <th class="px-4 py-3">客模具编号</th>
                  <th class="px-4 py-3">模具名称</th>
                  <th class="px-4 py-3">用料</th>
                  <th class="px-4 py-3">颜色 / PMS</th>
                  <th class="px-4 py-3">色粉</th>
                  <th class="px-4 py-3 text-right">啤数</th>
                  <th class="px-4 py-3">需办日期</th>
                  <th class="px-4 py-3">状态</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100 bg-white">
                <tr v-for="line in activeLines" :key="line.id" class="hover:bg-slate-50">
                  <td class="px-4 py-3 font-medium text-slate-950">{{ line.id }}</td>
                  <td class="px-4 py-3 text-slate-700">{{ line.customerMoldNo }}</td>
                  <td class="px-4 py-3 text-slate-700">{{ line.moldName }}</td>
                  <td class="px-4 py-3 text-slate-700">{{ line.material }}</td>
                  <td class="px-4 py-3 text-slate-700">{{ line.color }} · {{ line.pms }}</td>
                  <td class="px-4 py-3 text-slate-700">{{ line.toner }}</td>
                  <td class="px-4 py-3 text-right text-slate-700">{{ line.quantity }}</td>
                  <td class="px-4 py-3 text-slate-700">{{ line.requiredDate }}</td>
                  <td class="px-4 py-3">
                    <StatusPill :label="line.status" :tone="line.statusTone" compact />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </SectionPanel>
      </div>
    </div>
  </main>
</template>
