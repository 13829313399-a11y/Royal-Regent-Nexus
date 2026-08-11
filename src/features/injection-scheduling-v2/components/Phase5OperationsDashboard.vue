<script setup lang="ts">
import { Activity, AlertTriangle, CheckCircle2, Database, Gauge, RefreshCw, RotateCcw } from '@lucide/vue'
import AnimatedMetricValue from './AnimatedMetricValue.vue'
import SchedulingTechnicalDetails from './SchedulingTechnicalDetails.vue'
import type { IntegrationStatusRecord, Phase5AnalyticsRecord, Phase5MetricRecord, SpeedModelRecord } from '../types'
import { integrationSourceMeta, integrationStatusMeta, speedModelStatusMeta } from '../presentation/schedulingLabels'

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

function formatDateTime(value: string) {
  if (!value) return '尚无数据'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false })
}

function metricTechnicalItems(metric: Phase5MetricRecord) {
  return [
    { label: '计算公式', rawValue: metric.formula || '—' },
    { label: '分子', rawValue: String(metric.numerator) },
    { label: '分母', rawValue: String(metric.denominator) },
    { label: '单位', rawValue: metric.unit || '—' },
  ]
}

function integrationTechnicalItems(integration: IntegrationStatusRecord) {
  return [
    { label: '来源原始类型', rawValue: integration.sourceType },
    { label: '来源 key', rawValue: integration.sourceKey || '—' },
    { label: '原始状态', rawValue: integration.status },
    { label: '游标', rawValue: integration.cursor || '—' },
    { label: 'revision', rawValue: String(integration.revision) },
    { label: '最近接收时间', rawValue: integration.lastReceivedAt || '—' },
  ]
}

function speedModelTechnicalItems(model: SpeedModelRecord) {
  return [
    { label: '模型 ID', rawValue: model.id },
    { label: '模具 ID', rawValue: model.moldId },
    { label: '原始状态', rawValue: model.status },
    { label: '来源窗口开始', rawValue: model.sourceWindowStart || '—' },
    { label: '来源窗口结束', rawValue: model.sourceWindowEnd || '—' },
    { label: '最近观测时间', rawValue: model.lastObservedAt || '—' },
    { label: 'revision', rawValue: String(model.revision) },
  ]
}
</script>

<template>
  <section class="phase5-dashboard">
    <header class="phase5-header">
      <div><span class="view-icon"><Activity :size="18" /></span><div><strong>运营分析与持续校准</strong><p>ERP 增量订单、设备实绩、运营指标与历史周期速度模型</p></div></div>
      <div class="phase5-actions">
        <span v-if="analytics">{{ analytics.dateFrom }} 至 {{ analytics.dateTo }} · {{ formatDateTime(analytics.generatedAt) }}</span>
        <button type="button" :disabled="loading" @click="emit('refresh')"><RefreshCw :size="14" :class="{ spin: loading }" />刷新</button>
        <button type="button" class="primary" :disabled="loading || !canManageRules" :title="canManageRules ? '按历史设备周期重建速度模型' : '需要排产规则管理权限'" @click="emit('calibrate')"><RotateCcw :size="14" :class="{ spin: loading }" />{{ loading ? '校准中' : '重新校准' }}</button>
      </div>
    </header>

    <div v-if="error" class="phase5-error"><AlertTriangle :size="16" /><span>{{ error }}</span></div>

    <template v-if="analytics">
      <div class="phase5-metrics">
        <article v-for="card in metricCards" :key="card.key" :class="card.tone">
          <span>{{ card.label }}</span>
          <strong><AnimatedMetricValue :value="analytics[card.key].value" :decimals="analytics[card.key].unit === '%' ? 1 : 0" />{{ analytics[card.key].unit }}</strong>
          <p>样本 {{ analytics[card.key].sampleCount }}</p>
          <SchedulingTechnicalDetails :items="metricTechnicalItems(analytics[card.key])" summary="统计口径技术信息" />
        </article>
      </div>

      <div class="phase5-columns">
        <section class="integration-panel">
          <header><Database :size="15" /><strong>接口接入状态</strong><span>{{ analytics.deviceInterfaceConfigured ? '设备接口已接入' : '当前未配置设备接口' }}</span></header>
          <div>
            <article v-for="integration in analytics.integrationStatuses" :key="`${integration.sourceType}:${integration.sourceKey}`" :class="integrationStatusMeta(integration.status).cssToken">
              <span class="integration-icon"><CheckCircle2 v-if="integration.status === 'ACTIVE'" :size="17" /><AlertTriangle v-else :size="17" /></span>
              <div><strong>{{ integrationSourceMeta(integration.sourceType).label }}</strong><p>{{ integrationStatusMeta(integration.status).label }}</p></div>
              <dl><div><dt>接收事件</dt><dd>{{ integration.eventCount }}</dd></div><div><dt>最近成功</dt><dd>{{ formatDateTime(integration.lastSuccessAt) }}</dd></div></dl>
              <small v-if="integration.lastError">{{ integration.lastError }}</small>
              <SchedulingTechnicalDetails :items="integrationTechnicalItems(integration)" summary="接口技术信息" />
            </article>
          </div>
        </section>

        <section class="speed-model-panel">
          <header><Gauge :size="15" /><strong>模具速度模型</strong><span>按设备历史周期中位数校准</span></header>
          <div class="speed-model-table">
            <div class="speed-model-head"><span>模具</span><span>周期</span><span>每周期产量</span><span>小时产能</span><span>样本 / 置信度</span><span>状态</span></div>
            <template v-for="model in analytics.speedModels" :key="model.id">
              <article>
                <strong>{{ model.moldNo }}</strong><span>{{ model.calibratedCycleSeconds.toFixed(1) }} 秒</span><span>{{ model.unitsPerCycle.toFixed(2) }}</span><span>{{ model.calibratedUnitsPerHour.toFixed(1) }}</span><span>{{ model.sampleCount }} / {{ (model.confidence * 100).toFixed(0) }}%</span><em :class="speedModelStatusMeta(model.status).cssToken">{{ speedModelStatusMeta(model.status).label }}</em>
              </article>
              <SchedulingTechnicalDetails :items="speedModelTechnicalItems(model)" :summary="`${model.moldNo} 技术信息`" />
            </template>
            <p v-if="!analytics.speedModels.length" class="empty-copy">尚无设备周期样本；接入设备事件并积累至少 3 个样本后可启用校准速度。</p>
          </div>
        </section>
      </div>

      <section class="phase5-notes"><strong>统计口径</strong><ul><li v-for="note in analytics.notes" :key="note">{{ note }}</li></ul></section>
    </template>

    <div v-else-if="loading" class="phase5-skeleton" role="status" aria-label="正在计算运营指标"><span v-for="item in 6" :key="item"></span></div>
    <div v-else class="phase5-empty"><Activity :size="28" /><strong>尚未读取运营分析</strong><p>点击刷新读取当前厂区指标与接口状态。</p><button type="button" @click="emit('refresh')">读取数据</button></div>
  </section>
</template>

<style scoped>
.phase5-metrics article :deep(.scheduling-technical-details){margin-top:7px}.integration-panel article :deep(.scheduling-technical-details){grid-column:1/-1}.speed-model-table>:deep(.scheduling-technical-details){margin:5px 10px 8px}
</style>
