<script setup lang="ts">
import { BarChart3, FileText, Package } from '@lucide/vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import {
  injectionReportingMetrics,
  injectionShiftReportRows,
  injectionWarehouseInboundRows,
} from '@/data/injectionSchedulingMock'
</script>

<template>
  <div class="space-y-6">
    <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <article
        v-for="metric in injectionReportingMetrics"
        :key="metric.label"
        class="rounded-2xl border border-slate-200 bg-white p-5"
      >
        <div class="flex items-center gap-3">
          <span class="flex size-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
            <BarChart3 class="size-4" aria-hidden="true" />
          </span>
          <p class="text-sm text-slate-500">{{ metric.label }}</p>
        </div>
        <p class="mt-5 text-4xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
        <p class="mt-3 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
      </article>
    </section>

    <div class="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
      <SectionPanel
        title="班次日报"
        subtitle="这块建议后面直接承接车间回报、达成率、停机与责任人分析"
      >
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">机台</th>
                <th class="pb-3 pr-4 font-medium">操作员</th>
                <th class="pb-3 pr-4 font-medium">11H 目标</th>
                <th class="pb-3 pr-4 font-medium">实际</th>
                <th class="pb-3 pr-4 font-medium">差异</th>
                <th class="pb-3 font-medium">停机</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in injectionShiftReportRows"
                :key="`${row.machine}-${row.worker}`"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.machine }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.worker }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.target11h }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.actual }}</td>
                <td class="py-4 pr-4">
                  <StatusPill :label="row.variance" :tone="row.tone" compact />
                </td>
                <td class="py-4 text-slate-600">{{ row.downtime }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

      <SectionPanel
        title="回报动作"
        subtitle="这页不是只看数字，而是要推进回报、入库和月结闭环"
      >
        <div class="space-y-4">
          <article class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div class="flex items-center gap-3">
              <span class="flex size-10 items-center justify-center rounded-2xl bg-white text-slate-700">
                <FileText class="size-4" aria-hidden="true" />
              </span>
              <div>
                <h3 class="font-semibold text-slate-950">车间日报回报</h3>
                <p class="mt-1 text-xs text-slate-500">按班次提交实际产量、停机、报废与交接班备注</p>
              </div>
            </div>
          </article>
          <article class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div class="flex items-center gap-3">
              <span class="flex size-10 items-center justify-center rounded-2xl bg-white text-slate-700">
                <Package class="size-4" aria-hidden="true" />
              </span>
              <div>
                <h3 class="font-semibold text-slate-950">入库与欠数回写</h3>
                <p class="mt-1 text-xs text-slate-500">同步入库数量、剩余欠数，并回写下一轮排产池</p>
              </div>
            </div>
          </article>
          <article class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div class="flex items-center gap-3">
              <span class="flex size-10 items-center justify-center rounded-2xl bg-white text-slate-700">
                <BarChart3 class="size-4" aria-hidden="true" />
              </span>
              <div>
                <h3 class="font-semibold text-slate-950">月结与绩效口径</h3>
                <p class="mt-1 text-xs text-slate-500">沉淀啤货工资、效率和异常损耗的统计口径</p>
              </div>
            </div>
          </article>
        </div>
      </SectionPanel>
    </div>

    <SectionPanel
      title="入库与 PMC 闭环"
      subtitle="把入库、PMC、交付状态拉通后，排产才真正闭环"
    >
      <div class="overflow-x-auto">
        <table class="min-w-full text-left text-sm">
          <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
            <tr>
              <th class="pb-3 pr-4 font-medium">送货单</th>
              <th class="pb-3 pr-4 font-medium">单号</th>
              <th class="pb-3 pr-4 font-medium">啤数</th>
              <th class="pb-3 pr-4 font-medium">用料 KG</th>
              <th class="pb-3 pr-4 font-medium">PMC</th>
              <th class="pb-3 font-medium">状态</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in injectionWarehouseInboundRows"
              :key="row.deliveryCode"
              class="border-b border-slate-100 align-top last:border-b-0"
            >
              <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.deliveryCode }}</td>
              <td class="py-4 pr-4 text-slate-600">{{ row.orderNo }}</td>
              <td class="py-4 pr-4 text-slate-600">{{ row.shots }}</td>
              <td class="py-4 pr-4 text-slate-600">{{ row.materialKg }}</td>
              <td class="py-4 pr-4 text-slate-600">{{ row.pmc }}</td>
              <td class="py-4">
                <StatusPill :label="row.status" :tone="row.tone" compact />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </SectionPanel>
  </div>
</template>
