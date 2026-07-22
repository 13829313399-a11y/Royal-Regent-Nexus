<script setup lang="ts">
import {
  calculateExpectedMaterialAmountHkd,
  formatMaterialComposition,
  resolveActualMaterialCostBreakdown,
  resolveMaterialComponents,
  type MoldingSampleMaterialPrice,
} from '@/lib/moldingSampleBusiness'
import { getMoldingSampleFactoryLabel } from '@/lib/moldingSampleFactoryCapabilities'
import { formatBusinessDate, formatBusinessDateTime } from '@/lib/dateTime'
import type { MoldingSampleItem, MoldingSampleWorkflowRecord } from '@/types/moldingSample'
import './moldingSamplePrint.css'

interface Props {
  records: MoldingSampleWorkflowRecord[]
  materialPrices: MoldingSampleMaterialPrice[]
  preview?: boolean
  canViewCost?: (record: MoldingSampleWorkflowRecord) => boolean
}

const props = withDefaults(defineProps<Props>(), {
  preview: false,
})

function formatBlank(value: string | number | null | undefined, fallback = '待填写') {
  return value === null || value === undefined || value === '' ? fallback : String(value)
}

function formatDate(value: string | null | undefined, fallback = '待填写') {
  return formatBusinessDate(value, fallback)
}

function formatTime(value: string | null | undefined, fallback = '待生成') {
  return formatBusinessDateTime(value, { includeSeconds: true, fallback })
}

function formatWeight(value: number | null | undefined) {
  return value === null || value === undefined ? '待填写' : `${Number(value).toFixed(2)} kg`
}

function formatMoney(value: number | null | undefined) {
  return value === null || value === undefined ? '待计算' : `HKD ${Number(value).toFixed(2)}`
}

function formatMoldPresenceStatus(value: MoldingSampleItem['mold_presence_status']) {
  return value === 'in_factory' ? '在厂' : value === 'out_of_factory' ? '不在厂' : '待确认'
}

function getMaterialLabel(item: MoldingSampleItem) {
  const components = resolveMaterialComponents(item)
  return components.length ? formatMaterialComposition(components) : formatBlank(item.material)
}

function getExpectedCost(item: MoldingSampleItem) {
  return calculateExpectedMaterialAmountHkd(item, props.materialPrices)
}

function getActualCost(item: MoldingSampleItem) {
  return item.actual_amount_hkd
    ?? resolveActualMaterialCostBreakdown(item, props.materialPrices).total_amount_hkd
}

function canShowCost(record: MoldingSampleWorkflowRecord) {
  return props.canViewCost?.(record) ?? record.access?.can_view_cost ?? true
}

function hasRejectReason(record: MoldingSampleWorkflowRecord) {
  return Boolean(record.order.reject_reason?.trim())
}
</script>

<template>
  <section
    class="molding-print-root molding-print-engineering-root"
    :class="{ 'is-preview': preview }"
    aria-label="工程啤办通知单打印文档"
  >
    <article
      v-for="(record, recordIndex) in records"
      :key="record.order.id"
      class="molding-print-page molding-print-engineering-page"
      data-testid="molding-sample-engineering-print-document"
    >
      <div class="molding-print-sheet">
        <header class="molding-print-engineering-header">
          <div class="molding-print-brand-block">
            <strong>ROYAL REGENT NEXUS</strong>
            <span>{{ getMoldingSampleFactoryLabel(record.order.factory_id) }} · 工程部</span>
          </div>
          <div class="molding-print-title-block">
            <h1>工程啤办通知单</h1>
            <p>MOLDING SAMPLE ORDER</p>
          </div>
          <div class="molding-print-document-number">
            <span>单据编号</span>
            <strong>{{ record.order.id }}</strong>
          </div>
        </header>

        <div class="molding-print-status-band">
          <span class="molding-print-status-pill">{{ record.order.status }}</span>
          <strong>{{ record.order.stage || '待填写' }} · {{ record.order.order_type }} · 共 {{ record.items.length }} 项模具明细</strong>
          <span v-if="records.length > 1" class="molding-print-batch-index">第 {{ recordIndex + 1 }} / {{ records.length }} 张</span>
        </div>

        <section class="molding-print-meta-grid" aria-label="单头信息">
          <div><span>产品 / 客户</span><strong>{{ formatBlank(record.order.product_name) }} / {{ formatBlank(record.order.client_name) }}</strong></div>
          <div><span>产品编号</span><strong>{{ formatBlank(record.order.order_number) }}</strong></div>
          <div><span>填写部 / 发至</span><strong>{{ formatBlank(record.order.workshop) }} / {{ formatBlank(record.order.send_to, '内部') }}</strong></div>
          <div><span>工程 / 主管</span><strong>{{ formatBlank(record.order.eng_name) }} / {{ formatBlank(record.order.supervisor) }}</strong></div>
          <div><span>开单日期</span><strong>{{ formatDate(record.order.date) }}</strong></div>
          <div><span>流程完成日期</span><strong>{{ formatDate(record.order.completed_date, '未完成') }}</strong></div>
          <div><span>系统提交时间</span><strong>{{ formatTime(record.order.created_at) }}</strong></div>
          <div><span>系统更新时间</span><strong>{{ formatTime(record.order.updated_at) }}</strong></div>
        </section>

        <section class="molding-print-reason-bar">
          <span>注意事项 / 开单事由</span>
          <strong>{{ formatBlank(record.order.reason) }}</strong>
        </section>

        <section v-if="hasRejectReason(record)" class="molding-print-reject-bar">
          <span>驳回原因</span>
          <strong>{{ record.order.reject_reason }}</strong>
        </section>

        <section class="molding-print-detail-heading">
          <strong>模具明细</strong>
          <span>同一产品的多套模具优先排在同一页</span>
        </section>

        <div v-if="!record.items.length" class="molding-print-empty">暂无模具明细</div>
        <table v-else class="molding-print-table molding-print-engineering-table">
          <colgroup>
            <col class="molding-print-col-index">
            <col class="molding-print-col-engineering-mold">
            <col class="molding-print-col-engineering-material">
            <col class="molding-print-col-engineering-quantity">
            <col class="molding-print-col-engineering-usage">
            <col class="molding-print-col-engineering-cost">
          </colgroup>
          <thead>
            <tr class="molding-print-context-row">
              <th colspan="6">{{ record.order.id }} · {{ formatBlank(record.order.product_name) }} / {{ formatBlank(record.order.client_name) }}</th>
            </tr>
            <tr>
              <th>#</th>
              <th>模具信息</th>
              <th>原料与颜色</th>
              <th>数量 / 时点</th>
              <th>用量（kg）</th>
              <th>料费 / 工程备注</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in record.items"
              :key="item.id"
              data-testid="molding-sample-engineering-print-row"
            >
              <td class="molding-print-index-cell">{{ item.sort_order }}</td>
              <td>
                <strong class="molding-print-cell-primary">{{ formatBlank(item.mold_id) }}</strong>
                <strong class="molding-print-cell-primary">{{ formatBlank(item.mold_name) }}</strong>
                <span>工模尺寸：{{ formatBlank(item.mold_dimensions) }}</span>
                <span>模具是否在厂：{{ formatMoldPresenceStatus(item.mold_presence_status) }}</span>
              </td>
              <td>
                <strong class="molding-print-cell-primary">{{ getMaterialLabel(item) }}</strong>
                <span class="molding-print-usage-type" :class="{ 'is-trial': item.material_usage_type === 'trial' }">
                  {{ item.material_usage_type === 'trial' ? '试料' : '正式生产' }}
                </span>
                <span>颜色：{{ formatBlank(item.color) }}</span>
                <span>PMS / 色粉：{{ formatBlank(item.pigment_no) }}</span>
              </td>
              <td>
                <strong class="molding-print-cell-primary">{{ formatBlank(item.quantity) }} 套 · {{ formatBlank(item.shoot_qty) }} 啤</strong>
                <span>需办日期：{{ formatDate(item.completion_time) }}</span>
              </td>
              <td>
                <span>预计：{{ formatWeight(item.required_material_kg) }}</span>
                <span>领料重量：{{ formatWeight(item.collected_weight_kg) }}</span>
                <strong class="molding-print-cell-primary">实际：{{ formatWeight(item.actual_weight_kg) }}</strong>
              </td>
              <td>
                <template v-if="canShowCost(record)">
                  <span>预计料费(HKD)：{{ formatMoney(getExpectedCost(item)) }}</span>
                  <strong class="molding-print-cell-primary">实际料费(HKD)：{{ formatMoney(getActualCost(item)) }}</strong>
                </template>
                <template v-else>
                  <span>预计料费(HKD)：无查看权限</span>
                  <span>实际料费(HKD)：无查看权限</span>
                </template>
                <span>工程备注：{{ formatBlank(item.notes) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>
  </section>
</template>
