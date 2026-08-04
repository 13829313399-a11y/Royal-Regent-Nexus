<script setup lang="ts">
import { Activity, AlertTriangle, CheckCircle2, Database, Gauge, RefreshCw, RotateCcw } from '@lucide/vue'
import type { Phase5AnalyticsRecord, Phase5MetricRecord } from '../types'

const props = defineProps<{
  analytics: Phase5AnalyticsRecord | null
  loading: boolean
  error: string
  canManageRules: boolean
}>()

const emit = defineEmits<{ refresh: []; calibrate: [] }>()

const metricCards: Array<{
  key: 'planAccuracy' | 'moldChangeCount' | 'overdueRate' | 'machineUtilization'
  label: string
  tone: string
}> = [
  { key: 'planAccuracy', label: '计划达成率', tone: 'teal' },
  { key: 'moldChangeCount', label: '换模次数', tone: 'blue' },
  { key: 'overdueRate', label: '超期率', tone: 'red' },
  { key: 'machineUtilization', label: '机台利用率', tone: 'amber' },
]

function formatMetric(metric: Phase5MetricRecord | undefined) {
  if (!metric) return '—'
  if (metric.unit === '%') return `${metric.value.toFixed(1)}%`
  return `${metric.value.toLocaleString('zh-CN')}${metric.unit}`
}

function formatDateTime(value: string) {
  if (!value) return '尚无数据'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false })
}

function integrationLabel(sourceType: 'ERP' | 'DEVICE') {
  return sourceType === 'ERP' ? 'ERP 新单增量同步' : '现场设备生产采集'
}

function integrationStatusLabel(status: string) {
  return status === 'ACTIVE' ? '正常接收' : status === 'ERROR' ? '同步异常' : '未配置接口'
}
</script>

<template>
  <section class="phase5-dashboard">
    <header class="phase5-header">
      <div><span class="view-icon"><Activity :size="18" /></span><div><strong>运营分析与持续校准</strong><p>ERP 增量订单、设备实绩、运营指标与历史周期速度模型</p></div></div>
      <div class="phase5-actions">
        <span v-if="analytics">{{ analytics.dateFrom }} 至 {{ analytics.dateTo }} · {{ formatDateTime(analytics.generatedAt) }}</span>
        <button type="button" :disabled="loading" @click="emit('refresh')"><RefreshCw :size="14" :class="{ spin: loading }" />刷新</button>
        <button type="button" class="primary" :disabled="loading || !canManageRules" :title="canManageRules ? '按历史设备周期重建速度模型' : '需要排产规则管理权限'" @click="emit('calibrate')"><RotateCcw :size="14" />重新校准</button>
      </div>
    </header>

    <div v-if="error" class="phase5-error"><AlertTriangle :size="16" /><span>{{ error }}</span></div>

    <template v-if="analytics">
      <div class="phase5-metrics">
        <article v-for="card in metricCards" :key="card.key" :class="card.tone">
          <span>{{ card.label }}</span>
          <strong>{{ formatMetric(analytics[card.key]) }}</strong>
          <p>样本 {{ analytics[card.key].sampleCount }} · {{ analytics[card.key].formula }}</p>
        </article>
      </div>

      <div class="phase5-columns">
        <section class="integration-panel">
          <header><Database :size="15" /><strong>接口接入状态</strong><span>{{ analytics.deviceInterfaceConfigured ? '设备接口已接入' : '当前未配置设备接口' }}</span></header>
          <div>
            <article v-for="integration in analytics.integrationStatuses" :key="`${integration.sourceType}:${integration.sourceKey}`" :class="integration.status.toLowerCase()">
              <span class="integration-icon"><CheckCircle2 v-if="integration.status === 'ACTIVE'" :size="17" /><AlertTriangle v-else :size="17" /></span>
              <div><strong>{{ integrationLabel(integration.sourceType) }}</strong><p>{{ integration.sourceKey || 'default' }} · {{ integrationStatusLabel(integration.status) }}</p></div>
              <dl><div><dt>接收事件</dt><dd>{{ integration.eventCount }}</dd></div><div><dt>游标</dt><dd>{{ integration.cursor || '—' }}</dd></div><div><dt>最近成功</dt><dd>{{ formatDateTime(integration.lastSuccessAt) }}</dd></div></dl>
              <small v-if="integration.lastError">{{ integration.lastError }}</small>
            </article>
          </div>
        </section>

        <section class="speed-model-panel">
          <header><Gauge :size="15" /><strong>模具速度模型</strong><span>按设备历史周期中位数校准</span></header>
          <div class="speed-model-table">
            <div class="speed-model-head"><span>模具</span><span>周期</span><span>每周期产量</span><span>小时产能</span><span>样本 / 置信度</span><span>状态</span></div>
            <article v-for="model in analytics.speedModels" :key="model.id">
              <strong>{{ model.moldNo }}</strong><span>{{ model.calibratedCycleSeconds.toFixed(1) }} 秒</span><span>{{ model.unitsPerCycle.toFixed(2) }}</span><span>{{ model.calibratedUnitsPerHour.toFixed(1) }}</span><span>{{ model.sampleCount }} / {{ (model.confidence * 100).toFixed(0) }}%</span><em :class="model.status.toLowerCase()">{{ model.status === 'ACTIVE' ? '已启用' : '样本不足' }}</em>
            </article>
            <p v-if="!analytics.speedModels.length" class="empty-copy">尚无设备周期样本；接入设备事件并积累至少 3 个样本后可启用校准速度。</p>
          </div>
        </section>
      </div>

      <section class="phase5-notes"><strong>统计口径</strong><ul><li v-for="note in analytics.notes" :key="note">{{ note }}</li></ul></section>
    </template>

    <div v-else-if="loading" class="phase5-empty"><span class="phase5-spinner"></span><strong>正在计算运营指标…</strong></div>
    <div v-else class="phase5-empty"><Activity :size="28" /><strong>尚未读取运营分析</strong><p>点击刷新读取当前厂区指标与接口状态。</p><button type="button" @click="emit('refresh')">读取数据</button></div>
  </section>
</template>
