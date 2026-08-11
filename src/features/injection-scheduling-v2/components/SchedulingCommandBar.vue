<script setup lang="ts">
import { computed } from 'vue'
import { Bot, CalendarDays, Database, Download, Ellipsis, House, RefreshCw, RotateCcw, Save, Search, Send, Sparkles, Upload } from '@lucide/vue'
import AccountMenu from '../../../components/layout/AccountMenu.vue'
import type { FactoryId, SchedulingSyncHealth } from '../types'
import { planStatusMeta } from '../presentation/schedulingLabels'

type PrimaryActionKind = 'refresh' | 'readonly' | 'save' | 'publish' | 'auto-schedule'

const props = withDefaults(defineProps<{
  factoryId: FactoryId
  factoryName: string
  sourceMode?: 'live' | 'fallback'
  sourceMessage?: string
  syncHealth?: SchedulingSyncHealth
  refreshing?: boolean
  search?: string
  lastSyncedAt?: string
  planStatus?: string
  pendingCount?: number
  saving?: boolean
  canSave?: boolean
  canImport?: boolean
  canExport?: boolean
  hasPlanningDraft?: boolean
  canPublish?: boolean
  publishingPlan?: boolean
  publishDisabledReason?: string
  saveMessage?: string
}>(), {
  sourceMode: 'live',
  sourceMessage: '',
  syncHealth: 'live',
  refreshing: false,
  search: '',
  lastSyncedAt: '',
  planStatus: '',
  pendingCount: 0,
  saving: false,
  canSave: false,
  canImport: false,
  canExport: false,
  hasPlanningDraft: false,
  canPublish: false,
  publishingPlan: false,
  publishDisabledReason: '',
  saveMessage: '',
})
const emit = defineEmits<{ 'update:factoryId': [value: string]; 'update:search': [value: string]; home: []; refresh: []; openAutoSchedule: []; openImport: []; openExport: []; openMasterData: []; publish: []; save: []; discard: [] }>()

const today = computed(() => new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()).replaceAll('/', '-'))
const sourceLabel = computed(() => ({
  live: '正式数据库',
  refreshing: props.sourceMode === 'fallback' ? '演示数据 · 同步中' : '正式数据 · 同步中',
  stale: '正式数据 · 已过期',
  'demo-readonly': '只读演示数据',
  error: '正式数据未加载',
})[props.syncHealth])
const topbarSourceLabel = computed(() => ({
  live: '正式数据', refreshing: '正在同步', stale: '数据已过期', 'demo-readonly': '只读演示', error: '读取失败',
})[props.syncHealth])
const planStatusLabel = computed(() => props.planStatus ? planStatusMeta(props.planStatus).label : '无计划')
const syncSummary = computed(() => props.saveMessage || (props.lastSyncedAt ? `${props.lastSyncedAt} 已同步` : `${props.factoryName} · ${planStatusLabel.value}`))
const publishReason = computed(() => props.publishDisabledReason || (!props.canPublish ? '当前账号无发布权限' : ''))
const primaryAction = computed<{ kind: PrimaryActionKind; label: string; disabled: boolean; reason: string }>(() => {
  if (props.syncHealth === 'stale' || props.syncHealth === 'error' || props.syncHealth === 'refreshing' || props.refreshing) {
    return {
      kind: 'refresh',
      label: props.refreshing || props.syncHealth === 'refreshing' ? '正在同步' : props.syncHealth === 'error' ? '重新加载正式数据' : '重新同步',
      disabled: props.refreshing || props.syncHealth === 'refreshing',
      reason: props.syncHealth === 'stale' ? '当前正式数据已过期；重新同步不会丢失本地草稿。' : props.syncHealth === 'error' ? '正式排产数据尚未加载。' : '',
    }
  }
  if (props.syncHealth === 'demo-readonly' || props.sourceMode === 'fallback') {
    return { kind: 'readonly', label: '只读演示', disabled: true, reason: '只读演示不提供正式业务写操作。' }
  }
  if (props.pendingCount > 0) {
    return {
      kind: 'save',
      label: props.saving ? '保存中' : `保存 ${props.pendingCount} 项修改`,
      disabled: !props.canSave || props.saving,
      reason: !props.canSave ? '当前账号无保存或生产回报权限。' : '',
    }
  }
  if (props.hasPlanningDraft) {
    return {
      kind: 'publish',
      label: props.publishingPlan ? '发布中' : '发布为当前执行',
      disabled: !props.canPublish || props.publishingPlan || Boolean(props.publishDisabledReason),
      reason: publishReason.value,
    }
  }
  return { kind: 'auto-schedule', label: '自动排期', disabled: false, reason: '' }
})
</script>

<template>
  <header class="scheduling-topbar">
    <div class="brand-mark"><Bot :size="22" /></div>
    <div class="brand-copy"><strong>Royal Regent Nexus</strong><span>ROYAL REGENT · PRODUCTION INTELLIGENCE</span></div>
    <button type="button" class="topbar-home-button" aria-label="返回主页" @click="emit('home')"><House :size="15" /><span>返回主页</span></button>
    <div class="topbar-live" :class="syncHealth"><span class="live-dot"></span><span>智能排产中枢在线</span><b>{{ topbarSourceLabel }}</b></div>
    <AccountMenu compact class="scheduling-account-menu" />
  </header>

  <section class="scheduling-commandbar" aria-label="排产命令栏">
    <div class="command-zone command-context" data-command-zone="context">
      <div class="page-identity"><span class="eyebrow">生产部 / 注塑排产</span><strong>注塑排产中枢</strong><span class="readonly-badge editable">智能优化引擎</span></div>
      <label class="command-field factory-field"><span>厂区</span><select :value="factoryId" @change="emit('update:factoryId', ($event.target as HTMLSelectElement).value)"><option value="huaxing">华兴</option><option value="huakang-a">华康 A</option><option value="huakang-b">华康 B</option><option value="huakang-c">华康 C</option><option value="huakang-d">华康 D</option><option value="huadeng">华登</option></select></label>
      <div class="command-field date-field"><CalendarDays :size="15" /><span>{{ today }}</span></div>
    </div>

    <div class="command-zone command-center" data-command-zone="search">
      <label class="command-search"><Search :size="16" /><input type="search" :value="search" aria-label="全局搜索排产任务" placeholder="搜索机台、工模、订单、货号…" @input="emit('update:search', ($event.target as HTMLInputElement).value)" /></label>
      <div class="source-pill command-source-status" :class="syncHealth" role="status"><Database :size="15" /><span>{{ sourceLabel }}</span></div>
      <span class="sync-time" aria-live="polite">{{ syncSummary }}</span>
    </div>

    <div class="command-zone command-actions" data-command-zone="actions">
      <button
        v-if="primaryAction.kind === 'refresh'"
        type="button"
        class="command-button command-primary"
        data-testid="command-primary-action"
        :disabled="primaryAction.disabled"
        :aria-busy="refreshing"
        :aria-describedby="primaryAction.reason ? 'command-primary-reason' : undefined"
        @click="emit('refresh')"
      ><RefreshCw :size="15" :class="{ spinning: refreshing }" />{{ primaryAction.label }}</button>
      <button v-else-if="primaryAction.kind === 'readonly'" type="button" class="command-button command-primary is-readonly" data-testid="command-primary-action" disabled aria-describedby="command-primary-reason"><Database :size="15" />{{ primaryAction.label }}</button>
      <button v-else-if="primaryAction.kind === 'save'" type="button" class="command-button command-primary" data-testid="command-primary-action" :disabled="primaryAction.disabled" :aria-busy="saving" :aria-describedby="primaryAction.reason ? 'command-primary-reason' : undefined" @click="emit('save')"><Save :size="15" />{{ primaryAction.label }}</button>
      <button v-else-if="primaryAction.kind === 'publish'" type="button" class="command-button command-primary" data-testid="command-primary-action" :disabled="primaryAction.disabled" :aria-busy="publishingPlan" :aria-describedby="primaryAction.reason ? 'command-primary-reason' : undefined" @click="emit('publish')"><RefreshCw v-if="publishingPlan" :size="15" class="spinning" /><Send v-else :size="15" />{{ primaryAction.label }}</button>
      <button v-else type="button" class="command-button command-primary" data-testid="command-primary-action" @click="emit('openAutoSchedule')"><Sparkles :size="15" />{{ primaryAction.label }}</button>

      <button v-if="pendingCount" type="button" class="command-button is-secondary command-context-action" @click="emit('discard')"><RotateCcw :size="15" />撤销 {{ pendingCount }}</button>
      <button v-if="hasPlanningDraft && primaryAction.kind !== 'publish'" type="button" class="command-button is-secondary command-context-action" :disabled="!canPublish || publishingPlan || Boolean(publishDisabledReason)" :aria-describedby="publishReason ? 'command-publish-reason' : undefined" @click="emit('publish')"><Send :size="15" />发布</button>
      <button v-if="primaryAction.kind !== 'auto-schedule' && primaryAction.kind !== 'readonly'" type="button" class="command-button is-secondary command-context-action" @click="emit('openAutoSchedule')"><Sparkles :size="15" />自动排期</button>

      <div class="command-quick-actions" aria-label="快捷数据操作">
        <button v-if="primaryAction.kind !== 'refresh'" type="button" class="command-button is-secondary" :disabled="refreshing" :aria-busy="refreshing" @click="emit('refresh')"><RefreshCw :size="15" :class="{ spinning: refreshing }" />刷新</button>
        <button type="button" class="command-button is-secondary" :disabled="!canImport" @click="emit('openImport')"><Upload :size="15" />导入</button>
        <button type="button" class="command-button is-secondary" :disabled="!canExport" @click="emit('openExport')"><Download :size="15" />导出</button>
      </div>

      <details class="command-more">
        <summary class="command-button is-secondary"><Ellipsis :size="16" />更多</summary>
        <div class="command-more-menu" data-testid="command-more-menu" aria-label="更多排产操作">
          <button v-if="primaryAction.kind !== 'refresh'" type="button" class="command-more-responsive" data-command-action="refresh" :disabled="refreshing" @click="emit('refresh')"><RefreshCw :size="15" /><span><strong>刷新同步</strong><small>重新读取当前厂区数据</small></span></button>
          <button type="button" class="command-more-responsive" data-command-action="import" :disabled="!canImport" @click="emit('openImport')"><Upload :size="15" /><span><strong>导入计划 / 下单表</strong><small>{{ canImport ? '打开导入流程' : '当前账号无导入权限' }}</small></span></button>
          <button type="button" class="command-more-responsive" data-command-action="export" :disabled="!canExport" @click="emit('openExport')"><Download :size="15" /><span><strong>导出计划表</strong><small>{{ canExport ? '按当前计划导出' : '当前计划或权限不允许导出' }}</small></span></button>
          <button type="button" data-command-action="master-data" :disabled="sourceMode !== 'live'" @click="emit('openMasterData')"><Database :size="15" /><span><strong>共享模具库</strong><small>{{ sourceMode === 'live' ? '打开共享模具数据库' : '演示数据不能进入正式主数据' }}</small></span></button>
        </div>
      </details>

      <span v-if="primaryAction.reason" id="command-primary-reason" class="command-action-reason" data-testid="command-primary-reason">{{ primaryAction.reason }}</span>
      <span v-if="hasPlanningDraft && primaryAction.kind !== 'publish' && publishReason" id="command-publish-reason" class="command-action-reason command-publish-reason">{{ publishReason }}</span>
    </div>
  </section>
</template>
