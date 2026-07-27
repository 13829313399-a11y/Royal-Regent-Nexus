<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  AlertTriangle,
  CheckCircle2,
  GitBranch,
  LoaderCircle,
  LockKeyhole,
  LockKeyholeOpen,
  MoveRight,
  Scissors,
  X,
} from '@lucide/vue'
import type {
  InjectionMachine,
  InjectionOrder,
  InjectionScheduleTask,
} from '@/types/injectionSchedule'

const props = withDefaults(defineProps<{
  open: boolean
  task?: InjectionScheduleTask | null
  order?: InjectionOrder | null
  machine?: InjectionMachine | null
  machines?: InjectionMachine[]
  conflictMessages?: string[]
  busy?: boolean
  error?: string
}>(), {
  task: null,
  order: null,
  machine: null,
  machines: () => [],
  conflictMessages: () => [],
  busy: false,
  error: '',
})

const emit = defineEmits<{
  close: []
  toggleLock: [payload: { taskId: string; locked: boolean; reason: string }]
  split: [payload: {
    taskId: string
    splitShots: number
    targetMachineId: string
    reason: string
  }]
}>()

const dialog = ref<HTMLElement | null>(null)
const actionMode = ref<'summary' | 'lock' | 'split'>('summary')
const reason = ref('')
const splitShots = ref(0)
const splitTargetMachineId = ref('')

const maxSplitShots = computed(() => Math.max(0, (props.task?.plannedShots ?? 0) - 1))
const splitIsValid = computed(() => (
  Boolean(props.task)
  && splitShots.value > 0
  && splitShots.value <= maxSplitShots.value
  && Boolean(splitTargetMachineId.value)
  && reason.value.trim().length >= 4
))
const lockIsValid = computed(() => (
  props.task?.status === 'draft'
  && reason.value.trim().length >= 4
))

watch(() => [props.open, props.task?.id] as const, async ([open]) => {
  actionMode.value = 'summary'
  reason.value = ''
  splitShots.value = Math.max(1, Math.floor((props.task?.plannedShots ?? 0) / 2))
  splitTargetMachineId.value = props.machine?.id ?? props.machines[0]?.id ?? ''
  if (open) {
    await nextTick()
    dialog.value?.querySelector<HTMLElement>('button')?.focus()
  }
}, { immediate: true })

function formatDateTime(value: string | null | undefined) {
  if (!value) return '未排程'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '未排程'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function snapshotLabel(
  snapshot: string | undefined,
  current: string | null | undefined,
  fallback: string,
) {
  if (snapshot !== undefined) return snapshot.trim() || '未记录'
  return current?.trim() || fallback
}

function submitLock() {
  const task = props.task
  if (!task || !lockIsValid.value) return
  emit('toggleLock', {
    taskId: task.id,
    locked: !task.locked,
    reason: reason.value.trim(),
  })
}

function submitSplit() {
  const task = props.task
  if (!task || !splitIsValid.value) return
  emit('split', {
    taskId: task.id,
    splitShots: splitShots.value,
    targetMachineId: splitTargetMachineId.value,
    reason: reason.value.trim(),
  })
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open && task" class="task-inspector-backdrop" @click.self="emit('close')">
      <section
        ref="dialog"
        class="task-inspector"
        role="dialog"
        aria-modal="true"
        aria-labelledby="task-inspector-title"
        @keydown.esc="emit('close')"
      >
        <header>
          <span class="task-inspector__icon"><GitBranch aria-hidden="true" /></span>
          <div>
            <span>
              {{ task.status === 'published' ? '已发布任务' : '草稿任务' }} ·
              {{ snapshotLabel(task.machineCodeSnapshot, machine?.machineNo, task.machineId) }}
            </span>
            <h2 id="task-inspector-title">
              {{ snapshotLabel(task.productNameSnapshot, order?.productName, '排程任务') }}
            </h2>
            <p>
              {{ snapshotLabel(task.orderNoSnapshot, order?.orderNo, task.orderId) }} ·
              模号 {{ snapshotLabel(task.moldCodeSnapshot, order?.moldId, '待确认') }} ·
              计划 {{ task.plannedShots.toLocaleString('zh-CN') }} 啤
            </p>
          </div>
          <button type="button" aria-label="关闭任务详情" @click="emit('close')">
            <X aria-hidden="true" />
          </button>
        </header>

        <div class="task-inspector__timeline">
          <span><small>开始</small><strong>{{ formatDateTime(task.startAt) }}</strong></span>
          <MoveRight aria-hidden="true" />
          <span><small>完成</small><strong>{{ formatDateTime(task.endAt) }}</strong></span>
        </div>

        <dl class="task-inspector__facts">
          <div><dt>换型时间</dt><dd>{{ task.setupMinutesBefore }} 分钟</dd></div>
          <div><dt>来源</dt><dd>{{ task.source === 'manual' ? '人工排程' : task.source }}</dd></div>
          <div><dt>状态</dt><dd>{{ task.locked ? '已锁定' : '可调整' }}</dd></div>
          <div><dt>版本</dt><dd>{{ task.planVersionId }}</dd></div>
        </dl>

        <section v-if="conflictMessages.length" class="task-inspector__conflicts">
          <h3>当前风险</h3>
          <ul>
            <li v-for="message in conflictMessages" :key="message">
              <AlertTriangle aria-hidden="true" />
              {{ message }}
            </li>
          </ul>
        </section>
        <p v-else class="task-inspector__clean">
          <CheckCircle2 aria-hidden="true" />
          当前任务没有已知阻断项；发布时仍会重新校验。
        </p>

        <nav aria-label="任务操作">
          <button
            type="button"
            :class="{ active: actionMode === 'lock' }"
            :disabled="task.status !== 'draft'"
            @click="actionMode = 'lock'; reason = ''"
          >
            <LockKeyholeOpen v-if="task.locked" aria-hidden="true" />
            <LockKeyhole v-else aria-hidden="true" />
            {{ task.locked ? '解锁任务' : '锁定任务' }}
          </button>
          <button
            type="button"
            :class="{ active: actionMode === 'split' }"
            :disabled="task.locked || task.status !== 'draft' || task.plannedShots <= 1"
            @click="actionMode = 'split'; reason = ''"
          >
            <Scissors aria-hidden="true" />
            拆分订单
          </button>
        </nav>

        <section v-if="actionMode === 'lock'" class="task-inspector__action">
          <h3>{{ task.locked ? '解除任务保护' : '锁定任务，防止后续移动' }}</h3>
          <label>
            <span>操作原因</span>
            <input
              v-model="reason"
              type="text"
              maxlength="200"
              placeholder="至少填写 4 个字，记录到版本审计"
            >
          </label>
          <button type="button" :disabled="!lockIsValid || busy" @click="submitLock">
            <LoaderCircle v-if="busy" class="spin" aria-hidden="true" />
            <LockKeyhole v-else aria-hidden="true" />
            {{ task.locked ? '确认解锁' : '确认锁定' }}
          </button>
        </section>

        <section v-if="actionMode === 'split'" class="task-inspector__action task-inspector__action--split">
          <h3>拆出一段计划数量</h3>
          <div>
            <label>
              <span>拆出数量</span>
              <input
                v-model.number="splitShots"
                type="number"
                min="1"
                :max="maxSplitShots"
              >
            </label>
            <label>
              <span>目标机台</span>
              <select v-model="splitTargetMachineId">
                <option v-for="entry in machines" :key="entry.id" :value="entry.id">
                  {{ entry.machineNo }} · {{ entry.machineClass }}
                </option>
              </select>
            </label>
          </div>
          <p>
            原任务保留 {{ Math.max(0, task.plannedShots - splitShots).toLocaleString('zh-CN') }} 啤，
            拆出 {{ Math.max(0, splitShots).toLocaleString('zh-CN') }} 啤；总数不会超过订单欠数。
          </p>
          <label>
            <span>拆单原因</span>
            <input
              v-model="reason"
              type="text"
              maxlength="200"
              placeholder="例如：目标机台可先完成急单数量"
            >
          </label>
          <button type="button" :disabled="!splitIsValid || busy" @click="submitSplit">
            <LoaderCircle v-if="busy" class="spin" aria-hidden="true" />
            <Scissors v-else aria-hidden="true" />
            确认拆单
          </button>
        </section>

        <p v-if="error" class="task-inspector__error" role="alert">{{ error }}</p>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.task-inspector-backdrop {
  position: fixed;
  z-index: 120;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  background: rgb(15 23 42 / 42%);
}

.task-inspector {
  display: flex;
  width: min(460px, 94vw);
  height: 100%;
  flex-direction: column;
  overflow: auto;
  background: #fff;
  box-shadow: -12px 0 30px rgb(15 23 42 / 18%);
  color: #0f172a;
}

.task-inspector > header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 11px;
  border-bottom: 1px solid #dce5e8;
  padding: 18px;
}

.task-inspector__icon {
  display: inline-flex;
  width: 38px;
  height: 38px;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  background: #e6f7f4;
  color: #0f766e;
}

.task-inspector svg { width: 17px; height: 17px; }
.task-inspector header span { color: #0f766e; font-size: 10px; font-weight: 800; }
.task-inspector h2,
.task-inspector h3,
.task-inspector p { margin: 0; }
.task-inspector h2 { margin-top: 3px; font-size: 18px; font-weight: 800; }
.task-inspector h3 { font-size: 13px; font-weight: 800; }
.task-inspector header p { margin-top: 3px; color: #64748b; font-size: 11px; }

.task-inspector button {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid #b7c9cc;
  border-radius: 6px;
  background: #fff;
  padding: 0 11px;
  color: #334155;
  font-size: 11px;
  font-weight: 700;
}
.task-inspector button:disabled { cursor: not-allowed; opacity: 0.45; }
.task-inspector button:focus-visible,
.task-inspector input:focus-visible,
.task-inspector select:focus-visible { outline: 3px solid rgb(20 184 166 / 28%); outline-offset: 2px; }
.task-inspector > header > button { width: 34px; padding: 0; border-color: transparent; }

.task-inspector__timeline {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #f7fafa;
  padding: 13px 18px;
}
.task-inspector__timeline > span { display: grid; gap: 2px; }
.task-inspector__timeline small { color: #64748b; font-size: 10px; }
.task-inspector__timeline strong { font-size: 12px; }
.task-inspector__timeline > svg { color: #0f766e; }

.task-inspector__facts {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1px;
  margin: 0;
  background: #e2e8f0;
  border-bottom: 1px solid #e2e8f0;
}
.task-inspector__facts div { display: grid; gap: 4px; background: #fff; padding: 11px 18px; }
.task-inspector__facts dt { color: #64748b; font-size: 10px; }
.task-inspector__facts dd { margin: 0; font-size: 12px; font-weight: 800; }

.task-inspector__conflicts,
.task-inspector__action { padding: 15px 18px; border-bottom: 1px solid #e2e8f0; }
.task-inspector__conflicts ul { display: grid; gap: 7px; margin: 9px 0 0; padding: 0; list-style: none; }
.task-inspector__conflicts li {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  border-radius: 5px;
  background: #fff1f2;
  padding: 8px 9px;
  color: #b91c1c;
  font-size: 11px;
}
.task-inspector__conflicts li svg { flex: none; margin-top: 1px; }
.task-inspector__clean {
  display: flex;
  align-items: center;
  gap: 7px;
  border-bottom: 1px solid #e2e8f0;
  padding: 13px 18px;
  color: #047857;
  font-size: 11px;
}

.task-inspector nav {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid #e2e8f0;
  padding: 12px 18px;
}
.task-inspector nav button.active { border-color: #0f766e; background: #e6f7f4; color: #0f766e; }

.task-inspector__action { display: grid; gap: 10px; background: #f7fbfb; }
.task-inspector__action label { display: grid; gap: 4px; color: #475569; font-size: 10px; font-weight: 700; }
.task-inspector__action input,
.task-inspector__action select {
  min-height: 36px;
  border: 1px solid #b7c9cc;
  border-radius: 6px;
  background: #fff;
  padding: 0 9px;
  color: #0f172a;
  font: inherit;
}
.task-inspector__action > button { justify-self: end; border-color: #0f766e; background: #0f766e; color: #fff; }
.task-inspector__action--split > div { display: grid; grid-template-columns: 0.7fr 1.3fr; gap: 9px; }
.task-inspector__action--split p { color: #64748b; font-size: 10px; line-height: 1.5; }

.task-inspector__error {
  margin: 14px 18px !important;
  border: 1px solid #fecaca;
  border-radius: 6px;
  background: #fff1f2;
  padding: 8px 10px;
  color: #b91c1c;
  font-size: 11px;
}

.spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
