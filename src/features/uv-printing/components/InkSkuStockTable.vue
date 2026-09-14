<script lang="ts">
import type { UvInkBalance, UvInkSku } from '../contracts'

/**
 * 库存行 = SKU 主数据 + 该 SKU 自己的余额。
 * 同色不同供应商、同色不同材质是两个 SKU、两行，永远不合并、不互相抵扣。
 */
export interface InkStockRow {
  sku: UvInkSku
  balance: UvInkBalance
}

/** 刻度条几何：以「可用量 / 阈值」中较大者为基准，阈值刻度线始终可见。 */
export interface InkMeterGeometry {
  /** 可用量占基准的百分比，0–100。 */
  fillPercent: number
  /** 阈值刻度线位置，0–100。 */
  thresholdPercent: number
  low: boolean
  /** 与阈值的差额，正数表示高于阈值。 */
  differenceMl: string
}

export const INK_LOW_STOCK_STATUS = { label: '低于预警阈值', tone: 'red' } as const
export const INK_NORMAL_STOCK_STATUS = { label: '库存正常', tone: 'green' } as const
</script>

<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import type { StatusView } from '../domain/status'
import { INK_MATERIAL_LABELS } from '../domain/status'
import {
  bottlesFromMl,
  decimalCompare,
  decimalDivide,
  decimalMax,
  decimalMultiply,
  decimalSubtract,
  decimalToNumber,
  formatDecimal,
} from '../domain/decimal'
import UvNumber from './UvNumber.vue'
import UvStatusPill from './UvStatusPill.vue'
import UvTable, { type UvColumn } from './UvTable.vue'

/**
 * 墨水 SKU 库存表。
 *
 * - 可用 ml、折合瓶数、预警阈值三列直接可见，不藏在悬浮提示里；
 * - 每行给一条刻度条对比阈值，阈值刻度线可见，低于阈值的行同时给出文字原因与数量差；
 * - 折合瓶数按 SKU 自己的包装容量换算，500ml 包装不会按 1000ml 计算；
 * - 单位成本是成本字段：没有 uv_printing:cost_read 时显示「未授权」，绝不渲染数值；
 * - 数量永远不用「0」代替缺失：余额缺失时明确写「余额未知」。
 */

const props = withDefaults(defineProps<{
  rows: InkStockRow[]
  canWrite: boolean
  canCostRead: boolean
  /** 正在提交的 SKU，避免重复点击。 */
  busySkuId?: string | null
}>(), {
  busySkuId: null,
})

const emit = defineEmits<{ issue: [skuId: string] }>()

const columns = computed<UvColumn[]>(() => {
  const base: UvColumn[] = [
    { key: 'sku', label: '墨水 SKU', width: 220 },
    { key: 'location', label: '库位', width: 96 },
    { key: 'package', label: '包装容量', width: 118, align: 'right', hint: 'SKU 配置，不假定 1000ml' },
    { key: 'available', label: '可用 ml', width: 128, align: 'right' },
    { key: 'bottles', label: '折合瓶数', width: 110, align: 'right' },
    { key: 'threshold', label: '预警阈值', width: 112, align: 'right' },
    { key: 'meter', label: '对比阈值', width: 196 },
  ]
  if (props.canCostRead) base.push({ key: 'cost', label: '单位成本', width: 122, align: 'right' })
  base.push({ key: 'state', label: '库存状态', width: 132 })
  base.push({ key: 'action', label: '操作', width: 110, align: 'right' })
  return base
})

function materialLabel(row: InkStockRow): string {
  return INK_MATERIAL_LABELS[row.sku.material] ?? '材质未标注'
}

function statusOf(row: InkStockRow): StatusView {
  return row.balance.low_stock ? INK_LOW_STOCK_STATUS : INK_NORMAL_STOCK_STATUS
}

/** 刻度几何按十进制字符串计算，不用二进制浮点做库存比较。 */
function meterOf(row: InkStockRow): InkMeterGeometry {
  const available = row.balance.available_ml
  const threshold = row.balance.threshold_ml
  const scale = decimalMultiply(decimalMax(available, threshold), '1.25')
  const percentOf = (value: string): number => {
    if (decimalCompare(scale, '0') <= 0) return 0
    const ratio = decimalToNumber(decimalDivide(value, scale, 6))
    if (!Number.isFinite(ratio)) return 0
    return Math.min(100, Math.max(0, Math.round(ratio * 1000) / 10))
  }
  return {
    fillPercent: percentOf(available),
    thresholdPercent: percentOf(threshold),
    low: row.balance.low_stock,
    differenceMl: decimalSubtract(available, threshold),
  }
}

function meterLabel(row: InkStockRow): string {
  const geometry = meterOf(row)
  const relation = geometry.low
    ? `低于阈值 ${formatDecimal(decimalSubtract(row.balance.threshold_ml, row.balance.available_ml), 1)} ml`
    : `高于阈值 ${formatDecimal(geometry.differenceMl, 1)} ml`
  return `可用 ${formatDecimal(row.balance.available_ml, 1)} ml，阈值 ${formatDecimal(row.balance.threshold_ml, 1)} ml，${relation}`
}

function reasonText(row: InkStockRow): string {
  const geometry = meterOf(row)
  return geometry.low
    ? `低于阈值 ${formatDecimal(decimalSubtract(row.balance.threshold_ml, row.balance.available_ml), 1)} ml，需要补货`
    : `高于阈值 ${formatDecimal(geometry.differenceMl, 1)} ml`
}

function bottleText(row: InkStockRow): string | null {
  return bottlesFromMl(row.balance.available_ml, row.balance.package_ml)
}

function writeReason(): string {
  return '缺少 uv_printing:ink_write 权限，领用与入库按钮已停用'
}
</script>

<template>
  <UvTable
    :columns="columns"
    :min-width="1240"
    caption="墨水 SKU 库存与预警阈值"
    keyboard-hint="可用量、折合瓶数与阈值直接可见；刻度条以较大值为基准，竖线是阈值位置。"
  >
    <tr v-for="row in props.rows" :key="row.sku.id" :data-sku-id="row.sku.id">
      <td>
        <p class="uv-row-primary">{{ row.sku.supplier }} · {{ row.sku.color }}</p>
        <p class="uv-row-sub">
          {{ materialLabel(row) }}
          <template v-if="row.sku.color_aliases.length"> · 别名 {{ row.sku.color_aliases.join('、') }}</template>
          <template v-if="!row.sku.is_active"> · 已停用 SKU</template>
        </p>
      </td>
      <td>{{ row.sku.location || '未登记库位' }}</td>
      <td style="text-align: right">
        <UvNumber
          v-if="decimalCompare(row.balance.package_ml, '0') > 0"
          :decimal="row.balance.package_ml"
          :decimal-scale="0"
          size="sm"
          unit="ml/瓶"
        />
        <span v-else class="uv-num--pending">包装容量未配置</span>
      </td>
      <td style="text-align: right">
        <UvNumber :decimal="row.balance.available_ml" :decimal-scale="1" size="md" emphasis unit="ml" />
      </td>
      <td style="text-align: right">
        <UvNumber
          v-if="bottleText(row)"
          :decimal="bottleText(row)"
          :decimal-scale="2"
          size="sm"
          unit="瓶"
        />
        <span v-else class="uv-num--pending">包装容量未知</span>
      </td>
      <td style="text-align: right">
        <UvNumber :decimal="row.balance.threshold_ml" :decimal-scale="1" size="sm" unit="ml" />
      </td>
      <td>
        <div class="uv-meter" role="img" :aria-label="meterLabel(row)">
          <span class="uv-meter__track">
            <span
              class="uv-meter__fill"
              :class="meterOf(row).low ? 'uv-meter__fill--low' : ''"
              :style="{ width: `${meterOf(row).fillPercent}%` }"
            />
            <span class="uv-meter__threshold" :style="{ left: `${meterOf(row).thresholdPercent}%` }" />
          </span>
        </div>
        <p class="uv-row-sub" :class="meterOf(row).low ? 'uv-num--pending' : ''">
          {{ reasonText(row) }}
        </p>
      </td>
      <td v-if="props.canCostRead" style="text-align: right">
        <UvNumber
          v-if="row.sku.unit_cost"
          :decimal="row.sku.unit_cost"
          :decimal-scale="4"
          size="sm"
          :unit="row.sku.currency ?? ''"
        />
        <span v-else class="uv-num--pending">待核</span>
      </td>
      <td>
        <UvStatusPill :status="statusOf(row)" compact />
        <p v-if="row.balance.cost_pending" class="uv-row-sub">有流水缺单价，成本待核</p>
      </td>
      <td style="text-align: right">
        <Button
          variant="outline"
          size="sm"
          type="button"
          :disabled="!props.canWrite || props.busySkuId === row.sku.id"
          :title="props.canWrite ? `领用 ${row.sku.supplier} · ${row.sku.color}` : writeReason()"
          :aria-label="props.canWrite ? undefined : `领用（不可用：${writeReason()}）`"
          @click="emit('issue', row.sku.id)"
        >
          {{ props.busySkuId === row.sku.id ? '提交中…' : '领用' }}
        </Button>
      </td>
    </tr>
  </UvTable>
</template>
