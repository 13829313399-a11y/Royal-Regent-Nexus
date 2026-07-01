<script setup lang="ts">
import { BarChart3, FileText, Package, RefreshCcw, Truck } from '@lucide/vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { useInjectionModuleData } from '@/factories/injection/useInjectionModuleData'

const {
  injectionInboundWritebackRows,
  injectionReportingMetrics,
  injectionShiftHandoverRows,
  injectionShiftReportChecklistItems,
  injectionShiftReportRows,
  injectionWarehouseInboundRows,
} = useInjectionModuleData()
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

    <SectionPanel
      title="班次回报闭环清单"
      subtitle="这里把班次日报、停机、结转交接和入库回写拆成一屏闭环动作，而不是只放几张说明卡片"
    >
      <div class="grid gap-4 xl:grid-cols-4">
        <article
          v-for="item in injectionShiftReportChecklistItems"
          :key="item.title"
          class="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="flex items-center gap-3">
              <span class="flex size-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                <FileText class="size-5" aria-hidden="true" />
              </span>
              <div>
                <h3 class="font-semibold text-slate-950">{{ item.title }}</h3>
                <p class="mt-1 text-xs text-slate-500">{{ item.owner }}</p>
              </div>
            </div>
            <StatusPill :label="item.status" :tone="item.tone" />
          </div>
          <p class="mt-4 text-sm leading-6 text-slate-600">{{ item.detail }}</p>
        </article>
      </div>
    </SectionPanel>

    <div class="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
      <SectionPanel
        title="班次日报"
        subtitle="这块直接承接车间回报、达成率、停机与责任人分析，后续最适合接真实录入表单"
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
        title="班次交接"
        subtitle="结转单如果交接不清，第二班就很容易乱掉，这块最好单独保留"
      >
        <div class="space-y-3">
          <article
            v-for="row in injectionShiftHandoverRows"
            :key="`${row.shift}-${row.machine}-${row.orderNo}`"
            class="rounded-2xl border border-slate-200 bg-slate-50 p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-center gap-3">
                <span class="flex size-10 items-center justify-center rounded-2xl bg-white text-slate-700">
                  <RefreshCcw class="size-4" aria-hidden="true" />
                </span>
                <div>
                  <h3 class="font-semibold text-slate-950">{{ row.shift }} · {{ row.machine }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ row.orderNo }} · 接手人 {{ row.nextOwner }}</p>
                </div>
              </div>
              <StatusPill :label="row.carryOverQty" :tone="row.tone" compact />
            </div>
            <p class="mt-4 text-sm leading-6 text-slate-600">{{ row.note }}</p>
          </article>
        </div>
      </SectionPanel>
    </div>

    <div class="grid gap-6 xl:grid-cols-[1fr_1fr]">
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

      <SectionPanel
        title="入库回写状态"
        subtitle="这块才是回报页最值得继续接接口的地方，直接决定待排池是否会刷新"
      >
        <div class="space-y-3">
          <article
            v-for="row in injectionInboundWritebackRows"
            :key="`${row.deliveryCode}-${row.orderNo}`"
            class="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-center gap-3">
                <span class="flex size-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                  <Truck class="size-5" aria-hidden="true" />
                </span>
                <div>
                  <h3 class="font-semibold text-slate-950">{{ row.deliveryCode }} · {{ row.orderNo }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ row.owner }}</p>
                </div>
              </div>
              <StatusPill :label="row.schedulerStatus" :tone="row.tone" />
            </div>

            <div class="mt-5 grid gap-3 sm:grid-cols-2">
              <div class="rounded-xl bg-slate-50 px-4 py-3">
                <p class="text-xs uppercase tracking-[0.22em] text-slate-500">入库数量</p>
                <p class="mt-2 text-sm font-semibold text-slate-900">{{ row.inboundQty }}</p>
              </div>
              <div class="rounded-xl bg-slate-50 px-4 py-3">
                <p class="text-xs uppercase tracking-[0.22em] text-slate-500">回写后欠数</p>
                <p class="mt-2 text-sm font-semibold text-slate-900">{{ row.shortageAfter }}</p>
              </div>
            </div>

            <div class="mt-4 flex flex-wrap gap-2">
              <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                仓库：{{ row.warehouseStatus }}
              </span>
              <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                ERP：{{ row.erpStatus }}
              </span>
              <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                排产池：{{ row.schedulerStatus }}
              </span>
            </div>
          </article>
        </div>

        <div class="mt-4 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-5 py-4">
          <div class="flex items-center gap-3">
            <Package class="size-5 text-slate-500" aria-hidden="true" />
            <p class="text-sm text-slate-600">
              下一步最值得接的是“仓库入库成功后自动回写 ERP 与排产欠数”，这样结转和次日待排会明显更准。
            </p>
          </div>
        </div>
      </SectionPanel>
    </div>
  </div>
</template>
