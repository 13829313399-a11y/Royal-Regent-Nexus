<script setup lang="ts">
import { ExternalLink, FileSearch, ShieldCheck } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import AiActionConfirmationCard from './AiActionConfirmationCard.vue'
import type {
  AIBusinessResult,
  AICartonProcurementSummary,
  AIEntityLink,
  AIInternalQuoteSummary,
  AIMoldingSampleSummary,
  AISourceSummary,
} from './types'

defineProps<{
  results: AIBusinessResult[]
  sources: AISourceSummary[]
}>()

function linkHref(link: AIEntityLink) {
  const query = new URLSearchParams(link.query ?? {}).toString()
  return query ? `${link.route}?${query}` : link.route
}

function numberOrDash(value: number | null | undefined) {
  return value === undefined || value === null ? '—' : String(value)
}

function percentageOrDash(value: number | null | undefined) {
  return value === undefined || value === null ? '—' : `${(value * 100).toFixed(1)}%`
}

function internalQuoteLink(
  quote: AIInternalQuoteSummary,
  factoryId: string | undefined,
): RouteLocationRaw {
  return {
    name: quote.navigationTarget === 'summary'
      ? 'internal-quote-summary'
      : 'internal-quote-collaboration',
    params: { quoteId: quote.quoteId },
    query: factoryId ? { factory: factoryId } : {},
  }
}

function moldingSampleLink(
  order: AIMoldingSampleSummary,
  factoryId: string | undefined,
): RouteLocationRaw {
  return {
    name: 'molding-sample',
    query: {
      order_id: order.orderId,
      ...(factoryId ? { factory: factoryId } : {}),
    },
  }
}

function cartonProcurementLink(_order: AICartonProcurementSummary, factoryId: string | undefined): RouteLocationRaw {
  return {
    name: 'carton-procurement',
    query: {
      tab: 'orders',
      ...(factoryId ? { factory: factoryId } : {}),
    },
  }
}

function cartonStatusLabel(status: string) {
  return {
    DRAFT: '草稿',
    PENDING_SUPPLIER: '待供应商确认',
    CONFIRMED: '已确认',
    PARTIALLY_RECEIVED: '部分收料',
    COMPLETED: '已完成',
    CANCELLED: '已取消',
  }[status] ?? '状态待确认'
}

function rawMaterialLink(tab: 'material' | 'batch', factoryId: string | undefined): RouteLocationRaw {
  return {
    name: 'raw-material-management',
    query: {
      tab,
      ...(factoryId ? { factory: factoryId } : {}),
    },
  }
}

function customerOrderLink(factoryId: string | undefined): RouteLocationRaw {
  return {
    name: 'customer-order-center',
    query: factoryId ? { factory: factoryId } : {},
  }
}
</script>

<template>
  <div
    v-if="results.length || sources.length"
    data-ai-business-results
    class="mx-4 mt-3 space-y-2 sm:mx-5"
  >
    <article
      v-for="result in results"
      :key="result.id"
      class="rounded-xl border border-sky-200 bg-sky-50/80 p-3"
    >
      <div class="flex items-start gap-2">
        <FileSearch class="mt-0.5 size-4 shrink-0 text-sky-700" aria-hidden="true" />
        <div class="min-w-0 flex-1">
          <h3 class="text-xs font-semibold text-slate-900">{{ result.title }}</h3>
          <div v-if="result.kind === 'plan_context' && result.planContext" class="mt-2 grid gap-2 sm:grid-cols-2">
            <section class="rounded-lg border border-emerald-200 bg-white p-2.5" data-plan-kind="published">
              <p class="text-[11px] font-bold text-emerald-700">当前执行 PUBLISHED</p>
              <template v-if="result.planContext.executionPublished">
                <p class="mt-1 text-[11px] text-slate-600">
                  日期 {{ result.planContext.executionPublished.businessDate || '—' }}
                  · 版本 {{ numberOrDash(result.planContext.executionPublished.revision) }}
                </p>
                <p class="mt-1 text-[11px] text-slate-600">
                  任务 {{ numberOrDash(result.planContext.executionPublished.taskCount) }}
                  · 运行中 {{ numberOrDash(result.planContext.executionPublished.runningCount) }}
                </p>
              </template>
              <p v-else class="mt-1 text-[11px] text-slate-500">当前没有已发布执行计划</p>
            </section>
            <section class="rounded-lg border border-amber-200 bg-white p-2.5" data-plan-kind="draft">
              <p class="text-[11px] font-bold text-amber-700">规划草案 DRAFT</p>
              <template v-if="result.planContext.planningDraft">
                <p class="mt-1 text-[11px] text-slate-600">
                  日期 {{ result.planContext.planningDraft.businessDate || '—' }}
                  · 版本 {{ numberOrDash(result.planContext.planningDraft.revision) }}
                </p>
                <p class="mt-1 text-[11px] text-slate-600">
                  任务 {{ numberOrDash(result.planContext.planningDraft.taskCount) }}
                </p>
              </template>
              <p v-else class="mt-1 text-[11px] text-slate-500">当前没有规划草案</p>
            </section>
          </div>
          <dl v-if="result.kind === 'backlog' && result.backlog" class="mt-2 grid grid-cols-2 gap-2 rounded-lg border border-sky-200 bg-white p-2.5 text-[11px] sm:grid-cols-3">
            <div>
              <dt class="text-slate-500">全部待排</dt>
              <dd class="mt-0.5 font-bold text-slate-900">{{ numberOrDash(result.backlog.total) }}</dd>
            </div>
            <div>
              <dt class="text-slate-500">本次返回</dt>
              <dd class="mt-0.5 font-bold text-slate-900">{{ numberOrDash(result.backlog.returned) }}</dd>
            </div>
            <div class="col-span-2 sm:col-span-1">
              <dt class="text-slate-500">数据范围</dt>
              <dd class="mt-0.5 break-words font-semibold text-slate-700">
                {{ result.backlog.sourceBusinessLabel || result.backlog.sourceScope || '当前已验证厂区' }}
              </dd>
            </div>
          </dl>
          <section
            v-if="result.kind === 'internal_quote_list' && result.internalQuote"
            class="mt-2 space-y-2"
            data-ai-internal-quote-list
          >
            <p class="rounded-lg border border-sky-200 bg-white px-2.5 py-2 text-[11px] text-slate-600">
              共 {{ result.internalQuote.total }} 条，本次返回 {{ result.internalQuote.returned }} 条
            </p>
            <ul v-if="result.internalQuote.quotes.length" class="space-y-2">
              <li
                v-for="quote in result.internalQuote.quotes"
                :key="quote.quoteId"
                class="rounded-lg border border-sky-200 bg-white p-2.5"
              >
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="min-w-0">
                    <p class="break-words text-xs font-bold text-slate-900">{{ quote.quoteNo }}</p>
                    <p class="mt-0.5 break-words text-[11px] text-slate-600">
                      客户：{{ quote.customer || '—' }} · 版本：{{ quote.versionLabel || '—' }}
                    </p>
                  </div>
                  <span class="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-800">
                    {{ quote.statusLabel }}
                  </span>
                </div>
                <p class="mt-1 text-[11px] text-slate-600">
                  当前环节：{{ quote.currentStageLabel }}
                </p>
                <p class="mt-1 text-[10px] text-slate-500">
                  更新时间：{{ quote.updatedAt || '—' }}
                </p>
                <RouterLink
                  :to="internalQuoteLink(quote, result.factoryId)"
                  class="mt-2 inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-700 ring-1 ring-inset ring-sky-200 hover:bg-sky-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
                >
                  打开内部报价
                  <ExternalLink class="size-3" aria-hidden="true" />
                </RouterLink>
              </li>
            </ul>
            <p v-else class="rounded-lg border border-dashed border-slate-300 bg-white p-3 text-center text-[11px] text-slate-500">
              当前筛选条件下没有内部报价
            </p>
          </section>
          <section
            v-if="result.kind === 'molding_sample_list' && result.moldingSample"
            class="mt-2 space-y-2"
            data-ai-molding-sample-list
          >
            <p class="rounded-lg border border-sky-200 bg-white px-2.5 py-2 text-[11px] text-slate-600">
              共 {{ result.moldingSample.total }} 条，本次返回 {{ result.moldingSample.returned }} 条
            </p>
            <ul v-if="result.moldingSample.orders.length" class="space-y-2">
              <li
                v-for="order in result.moldingSample.orders"
                :key="order.orderId"
                class="rounded-lg border border-sky-200 bg-white p-2.5"
              >
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="min-w-0">
                    <p class="break-words text-xs font-bold text-slate-900">
                      {{ order.orderNumber || order.orderId }}
                    </p>
                    <p class="mt-0.5 break-words text-[11px] text-slate-600">
                      {{ order.productName || '产品待补充' }} · {{ order.clientName || '客户待补充' }}
                    </p>
                  </div>
                  <span class="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-800">
                    {{ order.status || '状态待确认' }}
                  </span>
                </div>
                <p class="mt-1 text-[11px] text-slate-600">
                  阶段：{{ order.stage || '—' }} · 开单日期：{{ order.orderDate || '—' }}
                </p>
                <p class="mt-1 text-[10px] text-slate-500">
                  生产厂区：{{ order.productionFactoryId || '未分配' }} · 更新时间：{{ order.updatedAt || '—' }}
                </p>
                <RouterLink
                  :to="moldingSampleLink(order, result.factoryId)"
                  class="mt-2 inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-700 ring-1 ring-inset ring-sky-200 hover:bg-sky-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
                >
                  打开啤办追踪
                  <ExternalLink class="size-3" aria-hidden="true" />
                </RouterLink>
              </li>
            </ul>
            <p v-else class="rounded-lg border border-dashed border-slate-300 bg-white p-3 text-center text-[11px] text-slate-500">
              当前筛选条件下没有啤办任务
            </p>
          </section>
          <section
            v-if="result.kind === 'carton_procurement_list' && result.cartonProcurement"
            class="mt-2 space-y-2"
            data-ai-carton-procurement-list
          >
            <p class="rounded-lg border border-sky-200 bg-white px-2.5 py-2 text-[11px] text-slate-600">
              共 {{ result.cartonProcurement.total }} 条，本次返回 {{ result.cartonProcurement.returned }} 条
            </p>
            <ul v-if="result.cartonProcurement.orders.length" class="space-y-2">
              <li
                v-for="order in result.cartonProcurement.orders"
                :key="order.orderId"
                class="rounded-lg border border-sky-200 bg-white p-2.5"
              >
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="min-w-0">
                    <p class="break-words text-xs font-bold text-slate-900">{{ order.orderNo }}</p>
                    <p class="mt-0.5 break-words text-[11px] text-slate-600">
                      {{ order.customerName || '客户待补充' }} · {{ order.productName || order.itemNo || '产品待补充' }}
                    </p>
                  </div>
                  <span class="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-800">
                    {{ cartonStatusLabel(order.status) }}
                  </span>
                </div>
                <p class="mt-1 text-[11px] text-slate-600">
                  合同：{{ order.contractNo || '—' }} · 货号：{{ order.itemNo || '—' }}
                </p>
                <p class="mt-1 text-[10px] text-slate-500">
                  订单日 {{ order.orderDate || '—' }} · 交期 {{ order.dueDate || '—' }} · 版本 {{ order.revision }}
                </p>
                <RouterLink
                  :to="cartonProcurementLink(order, result.factoryId)"
                  class="mt-2 inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-700 ring-1 ring-inset ring-sky-200 hover:bg-sky-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
                >
                  打开纸箱采购订单
                  <ExternalLink class="size-3" aria-hidden="true" />
                </RouterLink>
              </li>
            </ul>
            <p v-else class="rounded-lg border border-dashed border-slate-300 bg-white p-3 text-center text-[11px] text-slate-500">
              当前筛选条件下没有纸箱采购订单
            </p>
          </section>
          <section
            v-if="result.kind === 'raw_material_master_list' && result.rawMaterialMaster"
            class="mt-2 space-y-2"
            data-ai-raw-material-master-list
          >
            <p class="rounded-lg border border-sky-200 bg-white px-2.5 py-2 text-[11px] text-slate-600">
              全厂共享目录共 {{ result.rawMaterialMaster.total }} 条，本次返回 {{ result.rawMaterialMaster.returned }} 条
            </p>
            <ul v-if="result.rawMaterialMaster.materials.length" class="space-y-2">
              <li v-for="material in result.rawMaterialMaster.materials" :key="material.materialId" class="rounded-lg border border-sky-200 bg-white p-2.5">
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="min-w-0">
                    <p class="break-words text-xs font-bold text-slate-900">{{ material.materialCode }} · {{ material.materialName }}</p>
                    <p class="mt-0.5 break-words text-[11px] text-slate-600">{{ material.category || '类别待补充' }} · {{ material.spec || '规格待补充' }}</p>
                  </div>
                  <span class="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-800">{{ material.status }}</span>
                </div>
                <p class="mt-1 text-[10px] text-slate-500">单位 {{ material.unit || '—' }} · 安全库存 {{ material.safetyStockKg ?? '待维护' }} kg</p>
              </li>
            </ul>
            <RouterLink :to="rawMaterialLink('material', result.factoryId)" class="inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-700 ring-1 ring-inset ring-sky-200">
              打开原料主数据
              <ExternalLink class="size-3" aria-hidden="true" />
            </RouterLink>
          </section>
          <section
            v-if="result.kind === 'raw_material_inventory_list' && result.rawMaterialInventory"
            class="mt-2 space-y-2"
            data-ai-raw-material-inventory-list
          >
            <p class="rounded-lg border border-sky-200 bg-white px-2.5 py-2 text-[11px] text-slate-600">
              共 {{ result.rawMaterialInventory.total }} 个批次，本次返回 {{ result.rawMaterialInventory.returned }} 个
            </p>
            <ul v-if="result.rawMaterialInventory.batches.length" class="space-y-2">
              <li v-for="batch in result.rawMaterialInventory.batches" :key="batch.batchId" class="rounded-lg border border-sky-200 bg-white p-2.5">
                <p class="break-words text-xs font-bold text-slate-900">{{ batch.materialName }} · {{ batch.batchNo || '批次待补充' }}</p>
                <p class="mt-1 text-[11px] text-slate-600">库位：{{ batch.location || '—' }}</p>
                <p class="mt-1 text-[10px] text-slate-500">初始 {{ batch.initialWeightKg }} kg · 可用 {{ batch.availableWeightKg }} kg</p>
              </li>
            </ul>
            <RouterLink :to="rawMaterialLink('batch', result.factoryId)" class="inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-700 ring-1 ring-inset ring-sky-200">
              打开库存批次
              <ExternalLink class="size-3" aria-hidden="true" />
            </RouterLink>
          </section>
          <section
            v-if="result.kind === 'customer_order_capabilities' && result.customerOrderCapabilities"
            class="mt-2 space-y-2"
            data-ai-customer-order-capabilities
          >
            <p class="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-[11px] font-medium text-amber-900">
              当前没有权威订单总台账，不能提供官方订单总数。
            </p>
            <ul v-if="result.customerOrderCapabilities.customers.length" class="grid gap-2 sm:grid-cols-2">
              <li
                v-for="customer in result.customerOrderCapabilities.customers"
                :key="customer.customerCode"
                class="rounded-lg border border-sky-200 bg-white p-2.5"
              >
                <p class="break-words text-xs font-bold text-slate-900">{{ customer.customerName }}</p>
                <p class="mt-1 text-[10px] text-slate-500">
                  {{ customer.customerCode }} · 支持批量预览与受控导出
                </p>
              </li>
            </ul>
            <p v-else class="rounded-lg border border-dashed border-slate-300 bg-white p-3 text-center text-[11px] text-slate-500">
              当前厂区尚未配置客户订单映射
            </p>
            <RouterLink :to="customerOrderLink(result.factoryId)" class="inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-700 ring-1 ring-inset ring-sky-200">
              打开客户订单中心
              <ExternalLink class="size-3" aria-hidden="true" />
            </RouterLink>
          </section>
          <section
            v-if="result.kind === 'customer_order_export_audit_list' && result.customerOrderExportAudits"
            class="mt-2 space-y-2"
            data-ai-customer-order-export-audits
          >
            <p class="rounded-lg border border-sky-200 bg-white px-2.5 py-2 text-[11px] text-slate-600">
              本次返回 {{ result.customerOrderExportAudits.returned }} 条导出审计；这不是订单总数
            </p>
            <ul v-if="result.customerOrderExportAudits.audits.length" class="space-y-2">
              <li
                v-for="audit in result.customerOrderExportAudits.audits"
                :key="audit.auditId"
                class="rounded-lg border border-sky-200 bg-white p-2.5"
              >
                <p class="break-words text-xs font-bold text-slate-900">
                  {{ audit.customerCode }} · {{ audit.outputFileName || '输出文件待确认' }}
                </p>
                <p class="mt-1 break-words text-[11px] text-slate-600">
                  模板：{{ audit.outputTemplate || '—' }} · 来单日期：{{ audit.receivedDate || '—' }}
                </p>
                <p class="mt-1 text-[10px] text-slate-500">
                  确认问题 {{ audit.confirmedIssueCount }} · 人工修改 {{ audit.manualOverrideCount }} · {{ audit.createdAt || '—' }}
                </p>
              </li>
            </ul>
            <p v-else class="rounded-lg border border-dashed border-slate-300 bg-white p-3 text-center text-[11px] text-slate-500">
              当前筛选条件下没有导出审计
            </p>
            <RouterLink :to="customerOrderLink(result.factoryId)" class="inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-700 ring-1 ring-inset ring-sky-200">
              打开客户订单中心
              <ExternalLink class="size-3" aria-hidden="true" />
            </RouterLink>
          </section>
          <section
            v-if="(result.kind === 'scheduling_preview' || result.kind === 'scheduling_comparison') && result.schedulingPreviews"
            class="mt-2 space-y-2"
            data-ai-scheduling-preview
          >
            <p class="rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-2 text-[11px] font-bold text-amber-900">
              {{ result.schedulingPreviews.candidateLabel }}
            </p>
            <p
              v-if="result.schedulingPreviews.comparableSnapshot === false"
              class="rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-2 text-[11px] font-medium text-rose-800"
            >
              {{ result.schedulingPreviews.comparisonWarning }}
            </p>
            <ul class="space-y-2">
              <li
                v-for="run in result.schedulingPreviews.runs"
                :key="run.runId"
                class="rounded-lg border border-sky-200 bg-white p-2.5"
              >
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="min-w-0">
                    <p class="break-words text-xs font-bold text-slate-900">
                      {{ run.scenarioName }} · 方案 {{ run.alternativeNo }}
                    </p>
                    <p class="mt-0.5 break-words text-[10px] text-slate-500">
                      Run {{ run.runId }} · DRAFT revision {{ run.planRevision }}
                    </p>
                  </div>
                  <span class="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-800">
                    {{ run.actualSolver }} / {{ run.solverStatus }}
                  </span>
                </div>
                <dl class="mt-2 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
                  <div><dt class="text-slate-500">已安排</dt><dd class="font-bold text-slate-900">{{ numberOrDash(run.metrics.scheduledCount) }}</dd></div>
                  <div><dt class="text-slate-500">需复核</dt><dd class="font-bold text-slate-900">{{ numberOrDash(run.metrics.reviewCount) }}</dd></div>
                  <div><dt class="text-slate-500">未安排</dt><dd class="font-bold text-slate-900">{{ numberOrDash(run.metrics.unassignedCount) }}</dd></div>
                  <div><dt class="text-slate-500">平均负载</dt><dd class="font-bold text-slate-900">{{ percentageOrDash(run.metrics.loadRatioAverage) }}</dd></div>
                  <div><dt class="text-slate-500">逾期变化</dt><dd class="font-bold text-slate-900">{{ numberOrDash(run.metrics.overdue.change) }}</dd></div>
                  <div><dt class="text-slate-500">换模变化</dt><dd class="font-bold text-slate-900">{{ numberOrDash(run.metrics.moldChanges.change) }}</dd></div>
                  <div><dt class="text-slate-500">计划 revision</dt><dd class="font-bold text-slate-900">{{ run.planRevision }}</dd></div>
                  <div><dt class="text-slate-500">规则 revision</dt><dd class="font-bold text-slate-900">{{ run.ruleRevision }}</dd></div>
                </dl>
              </li>
            </ul>
            <p class="text-[10px] leading-4 text-slate-500">
              指标来自已持久化 PREVIEW Run。请在正式排产页面选择；此处不会 Apply 或 Publish。
            </p>
          </section>
          <AiActionConfirmationCard
            v-if="result.kind === 'action_confirmation' && result.actionConfirmation"
            :confirmation="result.actionConfirmation"
          />
          <p v-if="result.summary" class="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-slate-600">
            {{ result.summary }}
          </p>
          <p v-if="result.factoryId || result.asOf" class="mt-2 text-[11px] text-slate-500">
            <span v-if="result.factoryId">厂区：{{ result.factoryId }}</span>
            <span v-if="result.factoryId && result.asOf"> · </span>
            <span v-if="result.asOf">数据时间：{{ result.asOf }}</span>
          </p>
          <p v-if="result.truncated" class="mt-1 text-[11px] font-medium text-amber-700">
            结果已按安全上限截断
          </p>
          <div v-if="result.links.length" class="mt-2 flex flex-wrap gap-2">
            <a
              v-for="link in result.links"
              :key="`${link.route}:${link.label}`"
              :href="linkHref(link)"
              class="inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 text-[11px] font-semibold text-sky-700 ring-1 ring-inset ring-sky-200 hover:bg-sky-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
            >
              {{ link.label }}
              <ExternalLink class="size-3" aria-hidden="true" />
            </a>
          </div>
        </div>
      </div>
    </article>

    <section v-if="sources.length" class="rounded-xl border border-slate-200 bg-white p-3" aria-label="回答来源">
      <div class="flex items-center gap-2 text-xs font-semibold text-slate-800">
        <ShieldCheck class="size-4 text-emerald-600" aria-hidden="true" />
        回答来源
      </div>
      <ul class="mt-2 space-y-2">
        <li v-for="source in sources" :key="source.id" class="text-[11px] leading-5 text-slate-600">
          <span class="font-medium text-slate-700">{{ source.label }}</span>
          <span v-if="source.factoryId"> · {{ source.factoryId }}</span>
          <span v-if="source.updatedAt"> · {{ source.updatedAt }}</span>
          <span v-if="source.links.length" class="ml-2 inline-flex flex-wrap gap-1.5">
            <a
              v-for="link in source.links"
              :key="`${link.route}:${link.label}`"
              :href="linkHref(link)"
              class="font-semibold text-sky-700 underline decoration-sky-300 underline-offset-2"
            >
              {{ link.label }}
            </a>
          </span>
        </li>
      </ul>
    </section>
  </div>
</template>
