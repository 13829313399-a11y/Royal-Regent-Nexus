<script setup lang="ts">
import { AlertTriangle, ClipboardList, Database, Factory, Layers3 } from '@lucide/vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { useInjectionModuleData } from '@/factories/injection/useInjectionModuleData'

const {
  injectionDataCenterDatasets,
  injectionMachineMasterRows,
  injectionMachineProfileRows,
  injectionMoldMachineMappingRows,
  injectionMoldTargetDetailRows,
  injectionMoldTargetRows,
  injectionOrderImportTasks,
  injectionPendingOrderDetailRows,
  injectionPendingOrderFieldGroups,
  injectionPendingOrderValidationRules,
} = useInjectionModuleData()
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

    <SectionPanel
      title="真实待排订单字段"
      subtitle="先把排产真正离不开的字段定清楚，后面接真实导入时才不会一边排一边补表"
    >
      <div class="grid gap-4 xl:grid-cols-3">
        <article
          v-for="group in injectionPendingOrderFieldGroups"
          :key="group.title"
          class="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <div class="flex items-center gap-3">
            <span class="flex size-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
              <ClipboardList class="size-5" aria-hidden="true" />
            </span>
            <div>
              <h3 class="font-semibold text-slate-950">{{ group.title }}</h3>
              <p class="mt-1 text-xs text-slate-500">{{ group.owner }}</p>
            </div>
          </div>

          <div class="mt-5 space-y-3">
            <article
              v-for="field in group.fields"
              :key="`${group.title}-${field.label}`"
              class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
            >
              <div class="flex items-center justify-between gap-3">
                <p class="font-medium text-slate-900">{{ field.label }}</p>
                <StatusPill :label="field.required ? '必填' : '建议填'" :tone="field.required ? 'red' : 'blue'" compact />
              </div>
              <p class="mt-2 text-xs text-slate-500">来源：{{ field.source }}</p>
              <p class="mt-2 text-sm leading-6 text-slate-600">{{ field.summary }}</p>
            </article>
          </div>
        </article>
      </div>
    </SectionPanel>

    <div class="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
      <SectionPanel
        title="待排订单真实字段视图"
        subtitle="这里不再只是看单号和数量，而是直接模拟排机前会核对的关键业务字段"
      >
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">单号</th>
                <th class="pb-3 pr-4 font-medium">客户 / 产品</th>
                <th class="pb-3 pr-4 font-medium">模具 / 穴数</th>
                <th class="pb-3 pr-4 font-medium">颜色 / 料型</th>
                <th class="pb-3 pr-4 font-medium">数量 / 啤重</th>
                <th class="pb-3 pr-4 font-medium">交期 / 来源</th>
                <th class="pb-3 pr-4 font-medium">建议机台</th>
                <th class="pb-3 font-medium">异常</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in injectionPendingOrderDetailRows"
                :key="row.orderNo"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.orderNo }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.customer }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.productName }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.moldCode }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.cavity }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.color }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.material }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.quantity }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.unitWeight }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.dueDate }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.source }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.machineAdvice }}</div>
                  <div class="mt-1 text-xs text-slate-500">计划员：{{ row.planner }}</div>
                </td>
                <td class="py-4">
                  <StatusPill :label="row.issue" :tone="row.tone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

      <SectionPanel
        title="字段校验与导入提醒"
        subtitle="排产页真正省时间的关键不是多一个按钮，而是先把缺字段和高风险单筛出来"
      >
        <div class="space-y-3">
          <article
            v-for="rule in injectionPendingOrderValidationRules"
            :key="rule.label"
            class="rounded-2xl border border-slate-200 bg-slate-50 p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-center gap-3">
                <span class="flex size-10 items-center justify-center rounded-2xl bg-white text-slate-700">
                  <AlertTriangle class="size-4" aria-hidden="true" />
                </span>
                <div>
                  <h3 class="font-semibold text-slate-950">{{ rule.label }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ rule.hit }}</p>
                </div>
              </div>
              <StatusPill :label="rule.hit" :tone="rule.tone" />
            </div>
            <p class="mt-4 text-sm leading-6 text-slate-600">{{ rule.detail }}</p>
          </article>
        </div>

        <div class="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-4">
          <p class="text-xs uppercase tracking-[0.22em] text-slate-500">导入建议</p>
          <p class="mt-3 text-sm leading-6 text-slate-600">
            真实接入时建议把 PDF / Excel / 图片导入都先统一到一张“待排订单标准表”，先做字段补齐，再允许进入排机执行。
          </p>
        </div>
      </SectionPanel>
    </div>

    <div class="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <SectionPanel
        title="订单池接入清单"
        subtitle="这块先把华兴真实订单导入拆成几步，后面拿到 Excel / PDF 时就能直接对位承接"
      >
        <div class="space-y-3">
          <article
            v-for="task in injectionOrderImportTasks"
            :key="task.step"
            class="rounded-2xl border border-slate-200 bg-white p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-center gap-3">
                <span class="flex size-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                  <ClipboardList class="size-4" aria-hidden="true" />
                </span>
                <div>
                  <h3 class="font-semibold text-slate-950">{{ task.step }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ task.owner }}</p>
                </div>
              </div>
              <StatusPill :label="task.status" :tone="task.tone" compact />
            </div>
            <p class="mt-4 text-sm leading-6 text-slate-600">{{ task.detail }}</p>
          </article>
        </div>
      </SectionPanel>

      <SectionPanel
        title="模具 → 机台映射承接位"
        subtitle="规则是通用的，但这张表的数据是各厂独立维护的。这里先给华兴做第一版映射看板。"
      >
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">模具</th>
                <th class="pb-3 pr-4 font-medium">客户 / 产品</th>
                <th class="pb-3 pr-4 font-medium">候选池</th>
                <th class="pb-3 pr-4 font-medium">主推荐 / 备选</th>
                <th class="pb-3 pr-4 font-medium">说明</th>
                <th class="pb-3 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in injectionMoldMachineMappingRows"
                :key="`${row.moldCode}-${row.recommendedMachine}`"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.moldCode }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.customer }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.productName }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">{{ row.candidatePool }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.recommendedMachine }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.backupMachine }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">{{ row.detail }}</td>
                <td class="py-4">
                  <StatusPill :label="row.status" :tone="row.tone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>
    </div>

    <div class="grid gap-6 xl:grid-cols-[1fr_1fr]">
      <SectionPanel
        title="机台主数据台账"
        subtitle="把吨位、机械手、工艺范围、颜色策略和维护计划放进同一张主数据表，后面自动匹配才有底"
      >
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">机台</th>
                <th class="pb-3 pr-4 font-medium">吨位 / 螺杆</th>
                <th class="pb-3 pr-4 font-medium">机械手 / 车间</th>
                <th class="pb-3 pr-4 font-medium">工艺范围</th>
                <th class="pb-3 pr-4 font-medium">颜色策略</th>
                <th class="pb-3 pr-4 font-medium">常用模具</th>
                <th class="pb-3 pr-4 font-medium">保养</th>
                <th class="pb-3 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="machine in injectionMachineMasterRows"
                :key="machine.machine"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ machine.machine }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ machine.tonnage }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ machine.screw }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ machine.robot }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ machine.workshop }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">{{ machine.processRange }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ machine.colorPolicy }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ machine.activeMolds }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ machine.maintenance }}</td>
                <td class="py-4">
                  <StatusPill :label="machine.status" :tone="machine.tone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

      <SectionPanel
        title="机台资料卡"
        subtitle="保留当前概览卡，方便首页快速扫一眼设备适配情况"
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
      title="模具目标主数据台账"
      subtitle="华兴模具总表已经接进来了，这里先按真实模具清单展示；24H / 11H、穴数、节拍和优选机台下一步继续补成正式主数据"
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

      <div class="mt-6 overflow-x-auto">
        <table class="min-w-full text-left text-sm">
          <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
            <tr>
              <th class="pb-3 pr-4 font-medium">模具</th>
              <th class="pb-3 pr-4 font-medium">客户 / 产品</th>
              <th class="pb-3 pr-4 font-medium">总表状态</th>
              <th class="pb-3 pr-4 font-medium">穴数 / 节拍</th>
              <th class="pb-3 pr-4 font-medium">24H / 11H</th>
              <th class="pb-3 pr-4 font-medium">优选机台</th>
              <th class="pb-3 pr-4 font-medium">来源</th>
              <th class="pb-3 pr-4 font-medium">最近复核</th>
              <th class="pb-3 font-medium">健康度</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="mold in injectionMoldTargetDetailRows"
              :key="`${mold.moldCode}-${mold.productName}`"
              class="border-b border-slate-100 align-top last:border-b-0"
            >
              <td class="py-4 pr-4 font-semibold text-slate-950">{{ mold.moldCode }}</td>
              <td class="py-4 pr-4 text-slate-600">
                <div>{{ mold.customer }}</div>
                <div class="mt-1 text-xs text-slate-500">{{ mold.productName }}</div>
              </td>
              <td class="py-4 pr-4">
                <StatusPill :label="mold.catalogStatus" :tone="mold.catalogStatus === '废模' ? 'red' : 'blue'" compact />
              </td>
              <td class="py-4 pr-4 text-slate-600">
                <div>{{ mold.cavity }}</div>
                <div class="mt-1 text-xs text-slate-500">{{ mold.cycleTime }}</div>
              </td>
              <td class="py-4 pr-4 text-slate-600">
                <div>{{ mold.target24h }}</div>
                <div class="mt-1 text-xs text-slate-500">{{ mold.target11h }}</div>
              </td>
              <td class="py-4 pr-4 text-slate-600">{{ mold.preferredMachine }}</td>
              <td class="py-4 pr-4 text-slate-600">{{ mold.source }}</td>
              <td class="py-4 pr-4 text-slate-600">{{ mold.lastVerified }}</td>
              <td class="py-4">
                <StatusPill :label="mold.health" :tone="mold.tone" compact />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </SectionPanel>
  </div>
</template>
