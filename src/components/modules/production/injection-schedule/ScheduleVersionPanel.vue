<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  GitCompareArrows,
  History,
  LoaderCircle,
  LockKeyhole,
  RefreshCcw,
  RotateCcw,
  ShieldCheck,
} from '@lucide/vue'

export interface Phase2VersionView {
  id: string
  versionNo: number
  name: string
  status: 'draft' | 'published' | 'superseded'
  revision: number
  taskCount: number
  conflictCount: number | null
  updatedAt: string
  updatedByName: string
}

export interface Phase2VersionDiffView {
  baseVersionNo: number | null
  targetVersionNo: number
  movedOrders: number
  reorderedTasks: number
  splitOrders: number
  lockedChanges: number
  changedDeliveryDates: number
  addedConflicts: number
  resolvedConflicts: number
  changeoverDelta: number
  affectedOrders: Array<{
    id: string
    orderNo: string
    summary: string
    deliveryDeltaHours: number | null
  }>
}

export interface Phase2ConflictView {
  id: string
  severity: 'warning' | 'error'
  blocking: boolean
  code: string
  message: string
}

const props = withDefaults(defineProps<{
  versions?: Phase2VersionView[]
  currentVersionId?: string
  diff?: Phase2VersionDiffView | null
  conflicts?: Phase2ConflictView[]
  publishReady?: boolean
  busy?: boolean
  error?: string
}>(), {
  versions: () => [],
  currentVersionId: '',
  diff: null,
  conflicts: () => [],
  publishReady: false,
  busy: false,
  error: '',
})

const emit = defineEmits<{
  selectVersion: [versionId: string]
  createDraft: []
  cloneAsDraft: [versionId: string]
  refreshMasters: [versionId: string]
  validate: [versionId: string]
  publish: [payload: { versionId: string; reason: string }]
}>()

const publishReason = ref('')
const showPublish = ref(false)

const currentVersion = computed(() => (
  props.versions.find((version) => version.id === props.currentVersionId) ?? null
))
const blockingConflicts = computed(() => props.conflicts.filter((conflict) => conflict.blocking))
const publishDisabledReason = computed(() => {
  if (!currentVersion.value) return '请先选择草稿版本'
  if (currentVersion.value.status !== 'draft') return '只有草稿可以发布'
  if (!props.publishReady) return '请先校验当前 revision，并审核版本差异与受影响订单'
  if (blockingConflicts.value.length > 0) return `仍有 ${blockingConflicts.value.length} 条阻断冲突`
  if (publishReason.value.trim().length < 4) return '发布原因至少填写 4 个字'
  return ''
})

watch(() => props.currentVersionId, () => {
  showPublish.value = false
  publishReason.value = ''
})

watch(() => props.publishReady, (ready) => {
  if (!ready) showPublish.value = false
})

function versionStatusLabel(status: Phase2VersionView['status']) {
  if (status === 'published') return '已发布'
  if (status === 'superseded') return '历史'
  return '草稿'
}

function formatDateTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value || '—'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function publishCurrent() {
  const version = currentVersion.value
  if (!version || publishDisabledReason.value) return
  emit('publish', { versionId: version.id, reason: publishReason.value.trim() })
}
</script>

<template>
  <section class="phase2-versions" aria-label="计划版本与发布">
    <section class="phase2-versions__list" aria-labelledby="phase2-version-list-title">
      <header>
        <div>
          <span>Phase 2 · 服务端版本</span>
          <h2 id="phase2-version-list-title">计划版本</h2>
          <p>草稿按 revision 保存；已发布版本不可原地修改。</p>
        </div>
        <button type="button" :disabled="busy" @click="emit('createDraft')">
          <LoaderCircle v-if="busy" class="spin" aria-hidden="true" />
          <CalendarClock v-else aria-hidden="true" />
          新建草稿
        </button>
      </header>

      <div v-if="versions.length" class="phase2-versions__cards">
        <button
          v-for="version in versions"
          :key="version.id"
          type="button"
          class="phase2-version-card"
          :class="{
            'phase2-version-card--selected': version.id === currentVersionId,
            'phase2-version-card--published': version.status === 'published',
          }"
          :aria-pressed="version.id === currentVersionId"
          @click="emit('selectVersion', version.id)"
        >
          <span class="phase2-version-card__icon">
            <ShieldCheck v-if="version.status === 'published'" aria-hidden="true" />
            <History v-else-if="version.status === 'superseded'" aria-hidden="true" />
            <CalendarClock v-else aria-hidden="true" />
          </span>
          <span class="phase2-version-card__copy">
            <strong>V{{ version.versionNo }} · {{ version.name }}</strong>
            <small>
              {{ version.taskCount }} 条任务 ·
              {{ version.conflictCount == null ? '冲突待校验' : `${version.conflictCount} 条冲突` }} ·
              revision {{ version.revision }}
            </small>
            <small>{{ formatDateTime(version.updatedAt) }} · {{ version.updatedByName || '系统' }}</small>
          </span>
          <span :class="`phase2-version-card__state phase2-version-card__state--${version.status}`">
            {{ versionStatusLabel(version.status) }}
          </span>
        </button>
      </div>

      <div v-else class="phase2-versions__empty">
        <CalendarClock aria-hidden="true" />
        <h3>还没有计划版本</h3>
        <p>确认 Excel 导入后会建立首个草稿，也可以从已发布版本复制新草稿。</p>
      </div>

      <footer v-if="currentVersion">
        <button
          v-if="currentVersion.status !== 'draft'"
          type="button"
          class="phase2-versions__secondary"
          :disabled="busy"
          @click="emit('cloneAsDraft', currentVersion.id)"
        >
          <RotateCcw aria-hidden="true" />
          从 V{{ currentVersion.versionNo }} 建立新草稿
        </button>
        <button
          v-else
          type="button"
          class="phase2-versions__secondary"
          :disabled="busy"
          @click="emit('validate', currentVersion.id)"
        >
          <ShieldCheck aria-hidden="true" />
          重新校验草稿
        </button>
        <button
          v-if="currentVersion.status === 'draft'"
          type="button"
          class="phase2-versions__secondary"
          :disabled="busy"
          @click="emit('refreshMasters', currentVersion.id)"
        >
          <RefreshCcw aria-hidden="true" />
          同步最新主数据
        </button>
      </footer>
    </section>

    <aside class="phase2-versions__diff" aria-labelledby="phase2-version-diff-title">
      <header>
        <div>
          <span>发布前差异</span>
          <h2 id="phase2-version-diff-title">
            V{{ diff?.targetVersionNo ?? currentVersion?.versionNo ?? '—' }}
            对比 {{ diff?.baseVersionNo == null ? '空版本' : `V${diff.baseVersionNo}` }}
          </h2>
          <p>移动、排序、拆单、交期和冲突变化来自服务端版本快照。</p>
        </div>
        <GitCompareArrows aria-hidden="true" />
      </header>

      <div v-if="diff" class="phase2-versions__metrics">
        <span><strong>{{ diff.movedOrders }}</strong><small>移动订单</small></span>
        <span><strong>{{ diff.reorderedTasks }}</strong><small>顺序变化</small></span>
        <span><strong>{{ diff.splitOrders }}</strong><small>拆单</small></span>
        <span :class="{ danger: diff.addedConflicts > 0 }">
          <strong>{{ diff.addedConflicts }}</strong><small>新增冲突</small>
        </span>
        <span><strong>{{ diff.resolvedConflicts }}</strong><small>解除冲突</small></span>
        <span>
          <strong>{{ diff.changeoverDelta > 0 ? '+' : '' }}{{ diff.changeoverDelta }}</strong>
          <small>换模变化</small>
        </span>
      </div>

      <div v-if="diff?.affectedOrders.length" class="phase2-versions__affected">
        <h3>受影响订单</h3>
        <ul>
          <li v-for="order in diff.affectedOrders.slice(0, 8)" :key="order.id">
            <span><strong>{{ order.orderNo }}</strong><small>{{ order.summary }}</small></span>
            <em v-if="order.deliveryDeltaHours != null">
              {{ order.deliveryDeltaHours > 0 ? '+' : '' }}{{ Math.round(order.deliveryDeltaHours) }}h
            </em>
          </li>
        </ul>
      </div>

      <div class="phase2-versions__conflicts">
        <h3>发布校验</h3>
        <ul v-if="conflicts.length">
          <li
            v-for="conflict in conflicts.slice(0, 8)"
            :key="conflict.id"
            :class="{ blocking: conflict.blocking }"
          >
            <AlertTriangle v-if="conflict.blocking" aria-hidden="true" />
            <CheckCircle2 v-else aria-hidden="true" />
            <span><strong>{{ conflict.code }}</strong>{{ conflict.message }}</span>
          </li>
        </ul>
        <p v-else class="phase2-versions__clean">
          <CheckCircle2 aria-hidden="true" />
          当前没有已知冲突；发布时仍会由服务端重新校验。
        </p>
      </div>

      <button
        v-if="currentVersion?.status === 'draft' && !showPublish"
        type="button"
        class="phase2-versions__publish"
        :disabled="busy"
        @click="publishReady ? showPublish = true : emit('validate', currentVersion.id)"
      >
        <LockKeyhole v-if="publishReady" aria-hidden="true" />
        <ShieldCheck v-else aria-hidden="true" />
        {{ publishReady ? '进入发布确认' : '先校验并查看差异' }}
      </button>

      <section v-if="showPublish && currentVersion?.status === 'draft'" class="phase2-versions__publish-form">
        <label>
          <span>发布原因</span>
          <textarea
            v-model="publishReason"
            rows="3"
            maxlength="300"
            placeholder="说明本次排程调整依据与业务影响"
          />
        </label>
        <p v-if="publishDisabledReason" role="status">{{ publishDisabledReason }}</p>
        <div>
          <button type="button" class="phase2-versions__secondary" @click="showPublish = false">
            取消
          </button>
          <button
            type="button"
            class="phase2-versions__publish"
            :disabled="Boolean(publishDisabledReason) || busy"
            @click="publishCurrent"
          >
            <LoaderCircle v-if="busy" class="spin" aria-hidden="true" />
            <ShieldCheck v-else aria-hidden="true" />
            确认发布 V{{ currentVersion.versionNo }}
          </button>
        </div>
      </section>

      <p v-if="error" class="phase2-versions__error" role="alert">{{ error }}</p>
    </aside>
  </section>
</template>

<style scoped>
.phase2-versions {
  display: grid;
  min-height: 0;
  grid-template-columns: minmax(440px, 1.15fr) minmax(380px, 0.85fr);
  gap: 14px;
  padding: 14px;
  background: #eef2f3;
}

.phase2-versions__list,
.phase2-versions__diff {
  min-height: 0;
  border: 1px solid #d7e1e4;
  border-radius: 6px;
  background: #fff;
}

.phase2-versions__list { display: flex; flex-direction: column; }

.phase2-versions__list > header,
.phase2-versions__diff > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid #e2e8f0;
  padding: 14px 16px;
}

.phase2-versions header span {
  color: #0f766e;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.phase2-versions h2,
.phase2-versions h3,
.phase2-versions p { margin: 0; }
.phase2-versions h2 { margin-top: 3px; font-size: 17px; font-weight: 800; }
.phase2-versions h3 { font-size: 12px; font-weight: 800; }
.phase2-versions header p { margin-top: 4px; color: #64748b; font-size: 11px; }
.phase2-versions svg { width: 16px; height: 16px; }
.phase2-versions__diff > header > svg { width: 26px; height: 26px; color: #0f766e; }

.phase2-versions button {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid #0f766e;
  border-radius: 6px;
  background: #0f766e;
  padding: 0 12px;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

.phase2-versions button:disabled { cursor: not-allowed; opacity: 0.48; }
.phase2-versions button:focus-visible,
.phase2-versions textarea:focus-visible { outline: 3px solid rgb(20 184 166 / 28%); outline-offset: 2px; }

.phase2-versions__cards {
  display: grid;
  align-content: start;
  gap: 8px;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}

.phase2-version-card {
  display: grid !important;
  min-height: 74px !important;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 11px !important;
  border-color: #dce5e8 !important;
  background: #fff !important;
  padding: 10px 12px !important;
  color: #0f172a !important;
  text-align: left;
}

.phase2-version-card:hover { border-color: #83aaa6 !important; background: #f7fbfb !important; }
.phase2-version-card--selected { border-color: #0f766e !important; box-shadow: inset 3px 0 0 #0f766e; }
.phase2-version-card--published { background: #f0fdfa !important; }

.phase2-version-card__icon {
  display: inline-flex;
  width: 36px;
  height: 36px;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: #e6f7f4;
  color: #0f766e;
}

.phase2-version-card__copy { display: grid; min-width: 0; gap: 3px; }
.phase2-version-card__copy strong,
.phase2-version-card__copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.phase2-version-card__copy strong { font-size: 12px; }
.phase2-version-card__copy small { color: #64748b; font-size: 10px; }

.phase2-version-card__state {
  border-radius: 999px;
  background: #eef2ff;
  padding: 4px 8px;
  color: #4338ca;
  font-size: 10px;
  font-weight: 800;
}
.phase2-version-card__state--published { background: #dcfce7; color: #15803d; }
.phase2-version-card__state--superseded { background: #f1f5f9; color: #64748b; }

.phase2-versions__list > footer {
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid #e2e8f0;
  padding: 10px 12px;
}

.phase2-versions__secondary {
  border-color: #b7c9cc !important;
  background: #fff !important;
  color: #334155 !important;
}

.phase2-versions__empty {
  display: grid;
  flex: 1;
  place-items: center;
  align-content: center;
  gap: 8px;
  padding: 40px;
  color: #64748b;
  text-align: center;
}
.phase2-versions__empty > svg { width: 34px; height: 34px; color: #0f766e; }
.phase2-versions__empty h3 { color: #0f172a; font-size: 15px; }
.phase2-versions__empty p { max-width: 360px; font-size: 11px; line-height: 1.6; }

.phase2-versions__diff {
  display: grid;
  align-content: start;
  overflow: auto;
}

.phase2-versions__metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-bottom: 1px solid #e2e8f0;
}
.phase2-versions__metrics span {
  display: grid;
  gap: 2px;
  border-right: 1px solid #e2e8f0;
  border-bottom: 1px solid #e2e8f0;
  padding: 10px 12px;
}
.phase2-versions__metrics span:nth-child(3n) { border-right: 0; }
.phase2-versions__metrics strong { font-size: 18px; }
.phase2-versions__metrics small { color: #64748b; font-size: 10px; }
.phase2-versions__metrics .danger strong { color: #dc2626; }

.phase2-versions__affected,
.phase2-versions__conflicts,
.phase2-versions__publish-form { padding: 13px 15px; border-bottom: 1px solid #e2e8f0; }
.phase2-versions__affected ul,
.phase2-versions__conflicts ul { display: grid; gap: 7px; margin: 10px 0 0; padding: 0; list-style: none; }
.phase2-versions__affected li,
.phase2-versions__conflicts li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-radius: 5px;
  background: #f8fafc;
  padding: 8px 9px;
  font-size: 10px;
}
.phase2-versions__affected li span { display: grid; gap: 2px; }
.phase2-versions__affected li small { color: #64748b; }
.phase2-versions__affected em { color: #b45309; font-style: normal; font-weight: 800; }

.phase2-versions__conflicts li { justify-content: flex-start; color: #475569; }
.phase2-versions__conflicts li svg { flex: none; color: #0f766e; }
.phase2-versions__conflicts li.blocking { background: #fff1f2; color: #b91c1c; }
.phase2-versions__conflicts li.blocking svg { color: #dc2626; }
.phase2-versions__conflicts li span { display: grid; gap: 2px; }
.phase2-versions__conflicts li strong { font-size: 9px; text-transform: uppercase; }
.phase2-versions__clean { display: flex; align-items: center; gap: 7px; margin-top: 10px !important; color: #047857; font-size: 11px; }

.phase2-versions__publish {
  margin: 13px 15px;
}
.phase2-versions__publish-form { display: grid; gap: 8px; background: #f7fbfb; }
.phase2-versions__publish-form label { display: grid; gap: 5px; color: #334155; font-size: 11px; font-weight: 700; }
.phase2-versions__publish-form textarea {
  resize: vertical;
  border: 1px solid #b7c9cc;
  border-radius: 6px;
  padding: 8px 9px;
  color: #0f172a;
  font: inherit;
}
.phase2-versions__publish-form p { color: #b45309; font-size: 10px; }
.phase2-versions__publish-form > div { display: flex; justify-content: flex-end; gap: 8px; }
.phase2-versions__publish-form .phase2-versions__publish { margin: 0; }

.phase2-versions__error {
  margin: 0 15px 15px !important;
  border: 1px solid #fecaca;
  border-radius: 6px;
  background: #fff1f2;
  padding: 8px 10px;
  color: #b91c1c;
  font-size: 11px;
}

.spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 1000px) {
  .phase2-versions { grid-template-columns: 1fr; }
}
</style>
