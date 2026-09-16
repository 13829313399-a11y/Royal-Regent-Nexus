<script setup lang="ts">
import { computed } from 'vue'
import { Activity, AlertTriangle, Clock, Wrench } from '@lucide/vue'
import type { UvMachine, UvReport } from '../contracts'
import { ADMIN_STATUS, FRESHNESS, RUNTIME_STATUS } from '../domain/status'
import { INK_MATERIAL_LABELS } from '../domain/status'
import { formatDuration, minutesBetween, shanghaiDateTimeString, shanghaiTimeString } from '../domain/businessTime'
import UvStatusPill from './UvStatusPill.vue'
import UvNumber from './UvNumber.vue'

/**
 * 机台卡片：行政状态（正常/维修/停用）与遥测状态（打印/待机/离线/错误/未知）
 * 以及采集新鲜度分别展示，三个维度不互相覆盖。
 *
 * - 没有任务进度就不画假的百分比进度条；进度只在适配器声明支持时显示；
 * - 失联必须同时展示最后心跳，不把失联自动等同于停机；
 * - 卡片上的产品名、今日合格数与运行状态可能来自不同时间尺度，必须带标签。
 */

const props = withDefaults(defineProps<{
  machine: UvMachine
  /** 该机台当天的有效合格件数；null 表示还没有数据，不是 0。 */
  goodQty?: number | null
  reports?: UvReport[]
  selected?: boolean
  /** 当班人员显示名。 */
  crew?: string[]
  asOf?: string
}>(), {
  goodQty: null,
  reports: () => [],
  selected: false,
  crew: () => [],
  asOf: '',
})

const emit = defineEmits<{ open: []; focus: [] }>()

const runtime = computed(() => RUNTIME_STATUS[props.machine.runtime_status])
const admin = computed(() => ADMIN_STATUS[props.machine.admin_status])
const freshness = computed(() => FRESHNESS[props.machine.freshness])

const heartbeatAge = computed(() =>
  props.machine.last_heartbeat_at && props.asOf
    ? minutesBetween(props.machine.last_heartbeat_at, props.asOf)
    : null,
)

const heartbeatLabel = computed(() => {
  if (!props.machine.last_heartbeat_at) return '设备从未上报心跳'
  const time = shanghaiTimeString(props.machine.last_heartbeat_at)
  const age = heartbeatAge.value
  return age === null ? `最后心跳 ${time}` : `最后心跳 ${time}（${formatDuration(age)}前）`
})

/** 需要关注的机台：心跳过期、从未连接、错误、维修。 */
const needsAttention = computed(() =>
  props.machine.freshness !== 'fresh'
  || props.machine.runtime_status === 'error'
  || props.machine.admin_status === 'maintenance',
)

const showProgress = computed(() =>
  props.machine.capabilities.progress && props.machine.progress_pct !== null,
)

/** 下步动作由状态决定，避免放一个能点却没有动作的按钮。 */
const nextAction = computed(() => {
  if (props.machine.admin_status === 'disabled') return '已停用：不参与排产，保留历史记录'
  if (props.machine.admin_status === 'maintenance') return '排查看维修费用记录与恢复时间'
  if (props.machine.freshness === 'never_seen') return '登记采集器与适配器能力后再判断在线'
  if (props.machine.freshness === 'stale') return '确认采集器是否停止，不要当作停机'
  if (props.machine.runtime_status === 'error') return '查看设备报错与最近任务证据'
  if (props.machine.runtime_status === 'printing') return '查看当前任务进度与原始证据'
  return '可安排下一批任务或核对上一班报工'
})

const qualitySplit = computed(() => {
  const reports = props.reports ?? []
  const total = reports.reduce((sum, report) => sum + report.reported_qty, 0)
  const good = reports.reduce((sum, report) => sum + report.good_qty, 0)
  return { total, good }
})
</script>

<template>
  <button
    type="button"
    class="uv-machine-card"
    :class="needsAttention ? 'uv-machine-card--attention' : ''"
    :aria-pressed="selected"
    :data-machine-code="machine.code"
    @click="emit('open')"
    @focus="emit('focus')"
  >
    <div class="uv-machine-card__head">
      <div>
        <p class="uv-machine-card__code">{{ machine.code }}</p>
        <p class="uv-machine-card__name">{{ machine.brand }} {{ machine.model }}</p>
      </div>
      <UvStatusPill :status="runtime" compact />
    </div>

    <div class="uv-machine-card__body">
      <div>
        <p class="uv-machine-card__label">当前任务</p>
        <p v-if="machine.current_task_name">{{ machine.current_task_name }}</p>
        <p v-else class="uv-field__missing">没有采集到的运行任务</p>
      </div>

      <div v-if="showProgress">
        <p class="uv-machine-card__label">适配器进度</p>
        <div class="uv-progress" role="progressbar" :aria-valuenow="machine.progress_pct ?? 0" aria-valuemin="0" aria-valuemax="100">
          <div class="uv-progress__bar" :style="{ width: `${machine.progress_pct}%` }" />
        </div>
        <p class="uv-machine-card__name">{{ machine.progress_pct }}% · 设备提供</p>
      </div>
      <p v-else class="uv-machine-card__name">
        <AlertTriangle class="inline size-3" aria-hidden="true" />
        适配器未提供准确进度
      </p>

      <div>
        <p class="uv-machine-card__label">今日合格件（已确认报工）</p>
        <UvNumber :qty="goodQty" size="md" align="left" :state="goodQty === null ? 'pending' : 'normal'" />
        <p v-if="qualitySplit.total" class="uv-machine-card__name">
          当日报工 {{ qualitySplit.total }} 件 · 合格 {{ qualitySplit.good }} 件
        </p>
      </div>
    </div>

    <div class="uv-machine-card__foot">
      <UvStatusPill :status="admin" compact />
      <UvStatusPill :status="freshness" compact />
      <span>{{ INK_MATERIAL_LABELS[machine.ink_material] }}</span>
      <span v-if="crew.length">当班 {{ crew.join('、') }}</span>
    </div>
    <p class="uv-machine-card__name">
      <Clock class="inline size-3" aria-hidden="true" />
      {{ heartbeatLabel }}
    </p>
    <p class="uv-callout">下一步：{{ nextAction }}</p>
    <p v-if="machine.admin_status === 'maintenance'" class="uv-machine-card__name">
      <Wrench class="inline size-3" aria-hidden="true" />
      维修中不等于采集失联，两个维度分别记录
    </p>
    <p v-else-if="!machine.capabilities.exact_completion" class="uv-machine-card__name">
      <Activity class="inline size-3" aria-hidden="true" />
      设备未提供可信完工信号，完工由人工确认
    </p>
  </button>
</template>
