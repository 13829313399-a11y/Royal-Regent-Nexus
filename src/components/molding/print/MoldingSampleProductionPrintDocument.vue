<script setup lang="ts">
import { formatMaterialComposition, resolveMaterialComponents } from '@/lib/moldingSampleBusiness'
import { formatBusinessDate, formatBusinessDateTime } from '@/lib/dateTime'
import type { MoldingSampleAuditLog, MoldingSampleItem, MoldingSampleWorkflowRecord } from '@/types/moldingSample'
import './moldingSamplePrint.css'

const ENGINEERING_ORDER_ACTION_PREFIXES = ['工程提交', '工程开单'] as const

interface Props {
  records: MoldingSampleWorkflowRecord[]
  preview?: boolean
  densityClassForRecord?: (record: MoldingSampleWorkflowRecord) => string
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

function formatDateTime(value: string | null | undefined, fallback = '未记录') {
  return formatBusinessDateTime(value, { fallback })
}

function getOpeningAudit(record: MoldingSampleWorkflowRecord): MoldingSampleAuditLog | undefined {
  return record.audit_logs
    .filter((log) => ENGINEERING_ORDER_ACTION_PREFIXES.some((prefix) => log.action.startsWith(prefix)))
    .sort((left, right) => left.created_at.localeCompare(right.created_at))[0]
}

function getOrderCreator(record: MoldingSampleWorkflowRecord) {
  return getOpeningAudit(record)?.actor_name?.trim() || record.order.eng_name?.trim() || '未记录'
}

function getOrderCreatedAt(record: MoldingSampleWorkflowRecord) {
  return getOpeningAudit(record)?.created_at || record.order.created_at
}

function formatWeight(value: number | null | undefined) {
  return value === null || value === undefined ? '待填写' : `${Number(value).toFixed(2)} kg`
}

function formatMoldPresenceStatus(value: MoldingSampleItem['mold_presence_status']) {
  return value === 'in_factory' ? '在厂' : value === 'out_of_factory' ? '不在厂' : '待确认'
}

function getMaterialLabel(item: MoldingSampleItem) {
  const components = resolveMaterialComponents(item)
  return components.length ? formatMaterialComposition(components) : formatBlank(item.material)
}

function getDensityClass(record: MoldingSampleWorkflowRecord) {
  return props.densityClassForRecord?.(record) ?? ''
}
</script>

<template>
  <section
    class="molding-print-root molding-print-production-root"
    :class="{ 'is-preview': preview }"
    aria-label="啤机部生产任务单打印文档"
  >
    <article
      v-for="(record, recordIndex) in records"
      :key="record.order.id"
      class="molding-print-page molding-print-production-page"
      :class="getDensityClass(record)"
      :data-testid="preview ? 'molding-sample-task-print-preview-notice' : 'molding-sample-task-print-notice'"
    >
      <div class="molding-print-sheet">
        <header class="molding-print-production-header">
          <div class="molding-print-production-heading">
            <strong>ROYAL REGENT NEXUS</strong>
            <h1>啤机部生产任务单</h1>
            <p>MOLDING SAMPLE PRODUCTION TASK</p>
          </div>
          <div class="molding-print-production-document-summary">
            <div class="molding-print-document-number">
              <strong>{{ record.order.id }}</strong>
              <span>{{ record.order.status }} · {{ record.order.stage || '待填写' }}</span>
            </div>
            <div class="molding-print-production-compact-meta" aria-label="生产任务单下单信息">
              <span>
                下单人：<strong data-testid="molding-sample-production-print-creator">{{ getOrderCreator(record) }}</strong>
              </span>
              <span>
                开单时间：<strong data-testid="molding-sample-production-print-created-at">{{ formatDateTime(getOrderCreatedAt(record)) }}</strong>
              </span>
            </div>
          </div>
        </header>

        <section class="molding-print-reason-bar">
          <span>注意事项 / 开单事由</span>
          <strong>{{ formatBlank(record.order.reason) }}</strong>
        </section>

        <section class="molding-print-detail-heading">
          <strong>工程模具明细</strong>
          <span>
            共 {{ record.items.length }} 项 · 不含啤机回填及费用
            <template v-if="records.length > 1"> · 第 {{ recordIndex + 1 }} / {{ records.length }} 张</template>
          </span>
        </section>

        <div v-if="!record.items.length" class="molding-print-empty">暂无工程模具明细</div>
        <table v-else class="molding-print-table molding-print-production-table">
          <colgroup>
            <col class="molding-print-col-index">
            <col class="molding-print-col-production-mold">
            <col class="molding-print-col-production-timing">
            <col class="molding-print-col-production-material">
            <col class="molding-print-col-production-quantity">
            <col class="molding-print-col-production-notes">
          </colgroup>
          <thead>
            <tr class="molding-print-context-row">
              <th colspan="6">{{ record.order.id }} · {{ formatBlank(record.order.product_name) }} / {{ formatBlank(record.order.client_name) }}</th>
            </tr>
            <tr>
              <th>#</th>
              <th>模具信息</th>
              <th>工程时点</th>
              <th>用料与颜色</th>
              <th>数量 / 需料</th>
              <th>工程备注</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in record.items"
              :key="item.id"
              data-testid="molding-sample-production-print-row"
            >
              <td class="molding-print-index-cell">{{ item.sort_order }}</td>
              <td>
                <strong class="molding-print-cell-primary">{{ formatBlank(item.mold_id) }} · {{ formatBlank(item.mold_name) }}</strong>
                <span>工模尺寸：{{ formatBlank(item.mold_dimensions) }}</span>
                <span>模具是否在厂：{{ formatMoldPresenceStatus(item.mold_presence_status) }}</span>
              </td>
              <td>
                <strong class="molding-print-cell-primary">需办：{{ formatDate(item.completion_time) }}</strong>
              </td>
              <td>
                <strong class="molding-print-cell-primary">{{ getMaterialLabel(item) }}</strong>
                <span class="molding-print-usage-type" :class="{ 'is-trial': item.material_usage_type === 'trial' }">
                  {{ item.material_usage_type === 'trial' ? '试料' : '正式生产' }}
                </span>
                <span>{{ formatBlank(item.color) }} / {{ formatBlank(item.pigment_no) }}</span>
              </td>
              <td>
                <span>{{ formatBlank(item.quantity) }} 套 · {{ formatBlank(item.shoot_qty) }} 啤</span>
                <strong class="molding-print-cell-primary">{{ formatWeight(item.required_material_kg) }}</strong>
              </td>
              <td>{{ formatBlank(item.notes) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>
  </section>
</template>
