<script setup lang="ts">
import { Database, Factory, Layers3 } from '@lucide/vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import {
  injectionDataCenterDatasets,
  injectionMachineProfileRows,
  injectionMoldTargetRows,
  injectionOrderSnapshotRows,
} from '@/data/injectionSchedulingMock'
</script>

<template>
  <div class="space-y-6">
    <SectionPanel
      title="数据底座健康度"
      subtitle="这里先把排产真正依赖的四类主数据拎出来，后面接真实导入与校验规则会很顺"
    >
      <div class="grid gap-4 xl:grid-cols-2">
        <article
          v-for="dataset in injectionDataCenterDatasets"
          :key="dataset.name"
          class="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="flex items-center gap-2">
                <span class="flex size-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                  <Database class="size-4" aria-hidden="true" />
                </span>
                <div>
                  <h3 class="font-semibold text-slate-950">{{ dataset.name }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ dataset.owner }} · {{ dataset.freshness }}</p>
                </div>
              </div>
            </div>
            <StatusPill :label="dataset.status" :tone="dataset.statusTone" />
          </div>

          <div class="mt-5">
            <ProgressMeter :value="dataset.completeness" :tone="dataset.statusTone" label="完整度" />
          </div>

          <p class="mt-4 text-sm leading-6 text-slate-600">{{ dataset.summary }}</p>

          <div class="mt-4 flex flex-wrap gap-2">
            <span
              v-for="issue in dataset.issues"
              :key="issue"
              class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600"
            >
              {{ issue }}
            </span>
          </div>
        </article>
      </div>
    </SectionPanel>

    <div class="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
      <SectionPanel
        title="订单快照池"
        subtitle="先承接待排 / 结转 / 异常订单，一眼能看出今天排机到底要处理什么"
      >
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">单号</th>
                <th class="pb-3 pr-4 font-medium">产品编码</th>
                <th class="pb-3 pr-4 font-medium">模具</th>
                <th class="pb-3 pr-4 font-medium">颜色 / 料型</th>
                <th class="pb-3 pr-4 font-medium">数量</th>
                <th class="pb-3 pr-4 font-medium">交期</th>
                <th class="pb-3 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in injectionOrderSnapshotRows"
                :key="row.orderNo"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.orderNo }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.productCode }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.moldName }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.color }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.material }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">{{ row.quantity }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.due }}</td>
                <td class="py-4">
                  <StatusPill :label="row.state" :tone="row.tone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

      <SectionPanel
        title="机台资料与适配"
        subtitle="把吨位、机械手、车间和适配工艺拉到一个地方，后面才能真正做自动匹配"
      >
        <div class="space-y-3">
          <article
            v-for="machine in injectionMachineProfileRows"
            :key="machine.machine"
            class="rounded-2xl border border-slate-200 bg-slate-50 p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-center gap-3">
                <span class="flex size-10 items-center justify-center rounded-2xl bg-white text-slate-700">
                  <Factory class="size-4" aria-hidden="true" />
                </span>
                <div>
                  <h3 class="font-semibold text-slate-950">{{ machine.machine }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ machine.tonnage }} · {{ machine.armType }} · {{ machine.workshop }}</p>
                </div>
              </div>
              <StatusPill :label="machine.status" :tone="machine.tone" />
            </div>
            <p class="mt-4 text-sm leading-6 text-slate-600">{{ machine.fit }}</p>
          </article>
        </div>
      </SectionPanel>
    </div>

    <SectionPanel
      title="模具目标中心"
      subtitle="24H / 11H 目标是排产天数计算的底层参数，最好单独维护和预警"
    >
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="mold in injectionMoldTargetRows"
          :key="mold.moldCode"
          class="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="flex items-center gap-2">
                <span class="flex size-10 items-center justify-center rounded-2xl bg-amber-50 text-amber-700">
                  <Layers3 class="size-4" aria-hidden="true" />
                </span>
                <h3 class="font-semibold text-slate-950">{{ mold.moldCode }}</h3>
              </div>
            </div>
            <StatusPill :label="mold.health" :tone="mold.tone" />
          </div>

          <div class="mt-5 grid gap-3">
            <div class="rounded-xl bg-slate-50 px-4 py-3">
              <p class="text-xs uppercase tracking-[0.22em] text-slate-500">24H 目标</p>
              <p class="mt-2 text-lg font-semibold text-slate-950">{{ mold.target24h }}</p>
            </div>
            <div class="rounded-xl bg-slate-50 px-4 py-3">
              <p class="text-xs uppercase tracking-[0.22em] text-slate-500">11H 目标</p>
              <p class="mt-2 text-lg font-semibold text-slate-950">{{ mold.target11h }}</p>
            </div>
          </div>

          <p class="mt-4 text-sm text-slate-500">来源：{{ mold.source }}</p>
        </article>
      </div>
    </SectionPanel>
  </div>
</template>
