<script lang="ts">
import type { UvInkMovement, UvInkSku } from '../contracts'

/** 流水行 = 流水事实 + 该流水的 SKU（用于包装容量换算）+ 机台显示名。 */
export interface InkMovementRow {
  movement: UvInkMovement
  sku: UvInkSku | null
  machineCode: string
}

/** 成本单元格的三种状态：未授权 / 待核 / 有值。缺失不是 0。 */
export interface InkCostCell {
  kind: 'unauthorized' | 'pending' | 'missing' | 'value'
  text: string
}
</script>

<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import type { Tone } from '@/data/enterpriseMock'
import type { StatusView } from '../domain/status'
import { INK_MOVEMENT_LABELS } from '../domain/status'
import { bottlesFromMl, formatDecimal, formatMoney } from '../domain/decimal'
import UvNumber from './UvNumber.vue'
import UvStatusPill from './UvStatusPill.vue'
import UvTable, { type UvColumn } from './UvTable.vue'

/**
 * 墨水流水表。
 *
 * - 数量以有符号 ml 展示，正负号是文字信号，颜色只是辅助；
 * - 折合瓶按 SKU 自己的包装容量换算，包装容量未知时写「包装容量未知」，不假设 1000ml；
 * - 单价与金额是成本字段：无 uv_printing:cost_read 显示「未授权」且不渲染数值，
 *   缺单价显示「待核」，绝不显示 0；
 * - 冲销动作只在「本身不是冲销、且没有被冲销过」的流水上出现；冲销行必须带原单链接，
 *   原流水被冲销后仍然保留在列表里。
 */

const props = withDefaults(defineProps<{
  rows: InkMovementRow[]
  canCostRead: boolean
  canWrite: boolean
  busyId?: string | null
  highlightId?: string | null
}>(), {
  busyId: null,
  highlightId: null,
})

const emit = defineEmits<{ reverse: [movement: UvInkMovement]; focus: [movementId: string] }>()

const columns = computed<UvColumn[]>(() => {
  const base: UvColumn[] = [
    { key: 'occurred_on', label: '发生日', width: 104 },
    { key: 'kind', label: '类型', width: 150 },
    { key: 'sku', label: 'SKU（供应商 · 材质 · 颜色）', width: 210 },
    { key: 'quantity', label: '数量 ml（有符号）', width: 132, align: 'right' },
    { key: 'bottles', label: '折合瓶', width: 102, align: 'right' },
  ]
  if (props.canCostRead) {
    base.push(
      { key: 'unit_cost', label: '单价', width: 116, align: 'right' },
      { key: 'amount', label: '金额', width: 132, align: 'right' },
    )
  }
  base.push(
    { key: 'machine', label: '机台 · 用途', width: 210 },
    { key: 'source', label: '来源单号', width: 150 },
    { key: 'created_by', label: '创建人', width: 120 },
    { key: 'action', label: '操作', width: 104, align: 'right' },
  )
  return base
})

function kindLabel(movement: UvInkMovement): string {
  return INK_MOVEMENT_LABELS[movement.kind] ?? '类型未标注'
}

/** 类型沿用业务语言；色调只是辅助，正负号与文字才是主要信号。 */
function kindStatus(movement: UvInkMovement): StatusView {
  const tone: Tone = movement.kind === 'reversal'
    ? 'amber'
    : movement.signed_ml.trim().startsWith('-')
      ? 'blue'
      : 'teal'
  return { label: kindLabel(movement), tone }
}

function signedText(movement: UvInkMovement): string {
  const raw = movement.signed_ml.trim()
  const negative = raw.startsWith('-')
  const body = negative || raw.startsWith('+') ? raw.slice(1) : raw
  return `${negative ? '-' : '+'}${formatDecimal(body, 1)}`
}

function bottleText(row: InkMovementRow): string | null {
  if (!row.sku) return null
  return bottlesFromMl(row.movement.quantity_ml, row.sku.package_ml)
}

function unitCostCell(movement: UvInkMovement): InkCostCell {
  if (!props.canCostRead) return { kind: 'unauthorized', text: '未授权' }
  if (movement.cost_pending) return { kind: 'pending', text: '待核' }
  if (movement.unit_cost) return { kind: 'value', text: formatDecimal(movement.unit_cost, 4) }
  return { kind: 'missing', text: '—' }
}

function amountCell(movement: UvInkMovement): InkCostCell {
  if (!props.canCostRead) return { kind: 'unauthorized', text: '未授权' }
  if (movement.cost_pending) return { kind: 'pending', text: '待核' }
  if (movement.amount) return { kind: 'value', text: formatMoney(movement.amount) }
  return { kind: 'missing', text: '—' }
}

/** 冲销只允许一次，且冲销产生的流水不能再被冲销。 */
function canReverse(movement: UvInkMovement): boolean {
  return movement.kind !== 'reversal' && !movement.reversed_by_id
}

function reverseDisabledReason(): string {
  return '缺少 uv_printing:ink_write 权限，冲销按钮已停用'
}

/** 成本列不显示时，用一条说明代替，避免用户以为金额是 0。 */
const costColumnNote = computed(() =>
  props.canCostRead ? '' : '当前账号没有 uv_printing:cost_read 权限：单价与金额列不显示，服务端也不下发这些字段。',
)
</script>

<template>
  <div>
    <p v-if="costColumnNote" class="uv-readonly-note" role="note">{{ costColumnNote }}</p>

    <UvTable
      :columns="columns"
      :min-width="1460"
      caption="墨水收发流水"
      keyboard-hint="冲销只影响被选中的那一条；冲销会新增一条反向流水，原流水保留在列表中。"
    >
      <tr
        v-for="row in props.rows"
        :key="row.movement.id"
        :aria-selected="props.highlightId === row.movement.id ? 'true' : undefined"
        :data-movement-id="row.movement.id"
      >
        <td>{{ row.movement.occurred_on }}</td>
        <td>
          <UvStatusPill :status="kindStatus(row.movement)" compact />
          <p v-if="row.movement.reverses_movement_id" class="uv-row-sub">
            原单
            <button
              type="button"
              class="uv-row-button"
              style="display: inline"
              :aria-label="`查看被冲销的原单 ${row.movement.reverses_movement_id}`"
              @click="emit('focus', row.movement.reverses_movement_id)"
            >
              <span class="uv-mono">{{ row.movement.reverses_movement_id }}</span>
            </button>
          </p>
          <p v-else-if="row.movement.reversed_by_id" class="uv-row-sub">
            已冲销 → <span class="uv-mono">{{ row.movement.reversed_by_id }}</span>（原流水保留）
          </p>
        </td>
        <td>
          <p class="uv-row-primary">{{ row.movement.sku_label }}</p>
          <p class="uv-row-sub">SKU {{ row.movement.sku_id }}</p>
        </td>
        <td style="text-align: right">
          <UvNumber :value="signedText(row.movement)" size="md" emphasis unit="ml" />
        </td>
        <td style="text-align: right">
          <UvNumber v-if="bottleText(row)" :decimal="bottleText(row)" :decimal-scale="2" size="sm" unit="瓶" />
          <span v-else class="uv-num--pending">包装容量未知</span>
        </td>
        <td v-if="props.canCostRead" style="text-align: right">
          <span v-if="unitCostCell(row.movement).kind === 'value'" class="uv-num">{{ unitCostCell(row.movement).text }}</span>
          <span v-else-if="unitCostCell(row.movement).kind === 'pending'" class="uv-num--pending">待核</span>
          <span v-else class="uv-num--placeholder">{{ unitCostCell(row.movement).text }}</span>
        </td>
        <td v-if="props.canCostRead" style="text-align: right">
          <span v-if="amountCell(row.movement).kind === 'value'" class="uv-num uv-num--emphasis">{{ amountCell(row.movement).text }}</span>
          <span v-else-if="amountCell(row.movement).kind === 'pending'" class="uv-num--pending">待核</span>
          <span v-else class="uv-num--placeholder">{{ amountCell(row.movement).text }}</span>
        </td>
        <td>
          <p class="uv-row-primary">{{ row.machineCode || '未指定机台' }}</p>
          <p class="uv-row-sub">{{ row.movement.purpose || '未填写用途' }}</p>
        </td>
        <td>
          <span v-if="row.movement.source_doc" class="uv-mono">{{ row.movement.source_doc }}</span>
          <span v-else class="uv-num--placeholder">无来源单号</span>
          <p v-if="row.movement.evidence" class="uv-row-sub">凭证 {{ row.movement.evidence }}</p>
        </td>
        <td>
          <span>{{ row.movement.created_by_name || '未记录创建人' }}</span>
          <p class="uv-row-sub">登记于 {{ row.movement.posted_on }}</p>
        </td>
        <td style="text-align: right">
          <Button
            v-if="canReverse(row.movement)"
            variant="outline"
            size="sm"
            type="button"
            :disabled="!props.canWrite || props.busyId === row.movement.id"
            :title="props.canWrite ? '冲销这一条流水，会新增关联的反向记录' : reverseDisabledReason()"
            :aria-label="props.canWrite ? undefined : `冲销（不可用：${reverseDisabledReason()}）`"
            @click="emit('reverse', row.movement)"
          >
            {{ props.busyId === row.movement.id ? '提交中…' : '冲销' }}
          </Button>
          <span v-else-if="row.movement.kind === 'reversal'" class="uv-row-sub">冲销记录不可再冲销</span>
          <span v-else class="uv-row-sub">已冲销，不能重复冲销</span>
        </td>
      </tr>
    </UvTable>
  </div>
</template>
