<script setup lang="ts">
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  ClipboardCheck,
  Info,
  LockKeyhole,
  ShieldCheck,
  Sparkles,
  X,
} from '@lucide/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import BacklogPool from './BacklogPool.vue'
import {
  colorChangeHoursByMachineClass,
  evaluateMachineEligibility,
  moldChangeHoursByMachineClass,
} from '@/domain/injection-scheduling'
import {
  armLabels,
  formatScheduleTime,
  formatSlack,
} from '@/lib/injectionSchedulingPresentation'
import type {
  BacklogOrder,
  InjectionMachine,
  MoveValidation,
  ScheduleMoveRequest,
  SchedulePlanVersion,
  ScheduleTask,
  SchedulingSimulationResult,
} from '@/types/injectionScheduling'

const props = defineProps<{
  selectedTask: ScheduleTask | null
  selectedMachine: InjectionMachine | null
  selectedBacklog: BacklogOrder | null
  machines: InjectionMachine[]
  tasks: ScheduleTask[]
  pendingMove: ScheduleMoveRequest | null
  pendingMoveValidation: MoveValidation | null
  backlog: BacklogOrder[]
  alertsOpen: boolean
  rulesOpen: boolean
  publishOpen: boolean
  backlogOpen: boolean
  optimizerOpen: boolean
  optimizationResult: SchedulingSimulationResult | null
  plan: SchedulePlanVersion
  factoryName: string
  backendConnected: boolean
}>()

const emit = defineEmits<{
  closeTask: []
  closeMachine: []
  selectBacklog: [backlogId: string]
  clearBacklogSelection: []
  assignBacklog: [backlogId: string, machineId: string]
  closeBacklog: []
  cancelMove: []
  confirmMove: []
  closeAlerts: []
  closeRules: []
  closePublish: []
  closeOptimizer: []
  applyOptimizer: []
  publish: []
}>()

const optimizerStepIndex = ref(0)
let optimizerTimers: number[] = []

const machineMap = computed(() => new Map(props.machines.map((machine) => [machine.id, machine])))
const taskMap = computed(() => new Map(props.tasks.map((task) => [task.id, task])))
const taskLabel = computed(() => {
  if (props.pendingMove?.taskId) {
    const task = taskMap.value.get(props.pendingMove.taskId)
    return task ? `${task.requirement.mold.moldNo} · ${task.requirement.productName}` : props.pendingMove.taskId
  }
  const order = props.backlog.find((item) => item.id === props.pendingMove?.backlogId)
  return order ? `${order.requirement.mold.moldNo} · ${order.requirement.productName}` : ''
})
const selectedTaskEligibility = computed(() => {
  if (!props.selectedTask) return null
  const machine = machineMap.value.get(props.selectedTask.machineId)
  return machine ? evaluateMachineEligibility({ machine, requirement: props.selectedTask.requirement }) : null
})
const alertTasks = computed(() => props.tasks.filter((task) => ['overdue', 'urgent', 'incomplete'].includes(task.risk)).slice(0, 12))
const drawerOpen = computed(() => Boolean(props.selectedTask || props.selectedMachine || props.backlogOpen))
const optimizerComplete = computed(() => optimizerStepIndex.value >= (props.optimizationResult?.steps.length ?? 0))

function clearOptimizerTimers() {
  optimizerTimers.forEach((timer) => window.clearTimeout(timer))
  optimizerTimers = []
}

watch(() => props.optimizerOpen, (open) => {
  clearOptimizerTimers()
  optimizerStepIndex.value = 0
  if (!open || !props.optimizationResult) return
  props.optimizationResult.steps.forEach((_, index) => {
    optimizerTimers.push(window.setTimeout(() => {
      optimizerStepIndex.value = index + 1
    }, 220 + index * 260))
  })
})

onBeforeUnmount(clearOptimizerTimers)
</script>

<template>
  <Teleport to="body">
    <Transition name="injection-fade">
      <div
        v-if="drawerOpen"
        class="fixed inset-0 z-[70] bg-slate-950/25 backdrop-blur-[1px]"
        @click.self="selectedTask ? emit('closeTask') : selectedMachine ? emit('closeMachine') : emit('closeBacklog')"
      >
        <aside class="absolute inset-y-0 right-0 grid w-full max-w-[430px] grid-rows-[auto_minmax(0,1fr)] border-l border-slate-200 bg-white shadow-2xl" aria-label="注塑排产详情抽屉">
          <header class="flex items-start gap-3 border-b border-slate-200 bg-gradient-to-b from-slate-50 to-white px-5 py-4">
            <span class="grid size-9 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-700">
              <Sparkles v-if="backlogOpen" class="size-4" />
              <Info v-else class="size-4" />
            </span>
            <div class="min-w-0 flex-1">
              <h2 class="text-base font-black text-slate-950">
                {{ backlogOpen ? '待排订单池' : selectedMachine ? '机台能力与队列' : '任务详情' }}
              </h2>
              <p class="mt-1 text-[9px] text-slate-500">
                {{ backlogOpen ? `${factoryName}独立数据 · ${backlog.length} 项待排` : selectedMachine ? `${selectedMachine.name} · 硬约束能力与状态` : '订单、匹配解释与交期影响' }}
              </p>
            </div>
            <button
              autofocus
              type="button"
              class="grid size-8 place-items-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50"
              aria-label="关闭抽屉"
              @click="selectedTask ? emit('closeTask') : selectedMachine ? emit('closeMachine') : emit('closeBacklog')"
            >
              <X class="size-4" />
            </button>
          </header>

          <div class="min-h-0 overflow-y-auto p-5">
            <BacklogPool
              v-if="backlogOpen"
              :orders="backlog"
              :machines="machines"
              :selected-order="selectedBacklog"
              @select="emit('selectBacklog', $event)"
              @clear-selection="emit('clearBacklogSelection')"
              @assign="(backlogId, machineId) => emit('assignBacklog', backlogId, machineId)"
            />

            <div v-else-if="selectedMachine" class="space-y-4">
              <div class="rounded-xl bg-teal-950 p-4 text-white">
                <div class="flex items-center justify-between">
                  <strong class="text-lg">{{ selectedMachine.name }}</strong>
                  <span class="rounded-full bg-white/10 px-2 py-1 text-[9px]">{{ selectedMachine.workshop }}</span>
                </div>
                <p class="mt-2 text-[10px] text-teal-100">
                  {{ selectedMachine.capability.machineClass }} · {{ selectedMachine.capability.tonnage }}T · {{ selectedMachine.kind }}
                </p>
              </div>
              <dl class="grid grid-cols-2 gap-2">
                <div
                  v-for="item in [
                    ['有效射胶量', `${Math.round(selectedMachine.capability.shotCapacityGrams * selectedMachine.capability.safetyUtilization)}g`],
                    ['拉杆内距', `${selectedMachine.capability.tieBarWidthMm}×${selectedMachine.capability.tieBarHeightMm}mm`],
                    ['容模厚度', `${selectedMachine.capability.minMoldThicknessMm}–${selectedMachine.capability.maxMoldThicknessMm}mm`],
                    ['机械手', armLabels[selectedMachine.capability.armType]],
                    ['螺杆', selectedMachine.capability.screwType],
                    ['抽芯 / 绞牙', `${selectedMachine.capability.supportsCorePull ? '可' : '不可'} / ${selectedMachine.capability.supportsUnscrewing ? '可' : '不可'}`],
                  ]"
                  :key="item[0]"
                  class="rounded-xl border border-slate-200 bg-slate-50 p-3"
                >
                  <dt class="text-[8px] text-slate-400">{{ item[0] }}</dt>
                  <dd class="mt-1 text-[10px] font-black text-slate-800">{{ item[1] }}</dd>
                </div>
              </dl>
              <div class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[9px] leading-5 text-amber-900">
                <strong>限制与状态</strong>
                <p class="mt-1">{{ selectedMachine.restriction }} · {{ selectedMachine.resourceState }}</p>
                <p>材料兼容：{{ selectedMachine.capability.compatibleMaterials.join(' / ') }}</p>
              </div>
            </div>

            <div v-else-if="selectedTask" class="space-y-4">
              <div class="rounded-xl bg-teal-950 p-4 text-white">
                <div class="flex items-center justify-between gap-3">
                  <strong class="text-lg">{{ selectedTask.requirement.mold.moldNo }}</strong>
                  <span v-if="selectedTask.locked" class="inline-flex items-center gap-1 rounded-full bg-white/10 px-2 py-1 text-[8px] text-teal-100">
                    <LockKeyhole class="size-3" />当前任务锁定
                  </span>
                </div>
                <p class="mt-2 text-[11px] text-teal-100">{{ selectedTask.requirement.productName }}</p>
                <p class="mt-4 text-[9px] text-teal-200">{{ formatScheduleTime(selectedTask.timing.plannedStart) }} → {{ formatScheduleTime(selectedTask.timing.plannedEnd) }}</p>
              </div>
              <dl class="grid grid-cols-2 gap-2">
                <div
                  v-for="item in [
                    ['订单号', selectedTask.requirement.orderNo],
                    ['机台', machineMap.get(selectedTask.machineId)?.name ?? selectedTask.machineId],
                    ['颜色 / 材料', `${selectedTask.requirement.color} / ${selectedTask.requirement.material}`],
                    ['欠数', selectedTask.production.remainingQuantity.toLocaleString()],
                    ['整啤毛重', selectedTask.requirement.mold.shotWeightGrams ? `${selectedTask.requirement.mold.shotWeightGrams}g` : '未录入'],
                    ['交期余量', formatSlack(selectedTask.timing.slackHours)],
                  ]"
                  :key="item[0]"
                  class="rounded-xl border border-slate-200 bg-slate-50 p-3"
                >
                  <dt class="text-[8px] text-slate-400">{{ item[0] }}</dt>
                  <dd class="mt-1 text-[10px] font-black text-slate-800">{{ item[1] }}</dd>
                </div>
              </dl>
              <div class="rounded-xl border border-slate-200 p-3">
                <strong class="text-[10px] text-slate-800">当前机台资格解释</strong>
                <div class="mt-2 space-y-1.5">
                  <p
                    v-for="check in selectedTaskEligibility?.checks"
                    :key="check.code"
                    class="flex items-start gap-2 text-[8px]"
                    :class="check.passed ? 'text-slate-600' : 'text-red-700'"
                  >
                    <CheckCircle2 v-if="check.passed" class="mt-0.5 size-2.5 shrink-0 text-teal-600" />
                    <AlertTriangle v-else class="mt-0.5 size-2.5 shrink-0" />
                    <span><b>{{ check.label }}</b> · {{ check.reason }}</span>
                  </p>
                </div>
              </div>
              <div class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[9px] leading-5 text-amber-900">
                <strong>切换与排程说明</strong>
                <p class="mt-1">{{ selectedTask.changeover.reason }}</p>
                <p>{{ selectedTask.remark ?? '计算使用固定 anchorAt 和 Mock 生产日历。' }}</p>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </Transition>

    <Transition name="injection-fade">
      <div v-if="pendingMove" class="fixed inset-0 z-[85] grid place-items-center bg-slate-950/35 p-4 backdrop-blur-[1px]">
        <section class="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="move-title">
          <span class="grid size-11 place-items-center rounded-xl" :class="pendingMoveValidation?.allowed ? 'bg-teal-50 text-teal-700' : 'bg-red-50 text-red-700'">
            <ShieldCheck v-if="pendingMoveValidation?.allowed" class="size-5" />
            <AlertTriangle v-else class="size-5" />
          </span>
          <h2 id="move-title" class="mt-4 text-xl font-black text-slate-950">
            {{ pendingMoveValidation?.allowed ? '确认调整后续任务？' : '目标机台未通过校验' }}
          </h2>
          <p class="mt-2 text-sm leading-6 text-slate-600">当前任务保持锁定；确认后只修改 {{ factoryName }} 的{{ backendConnected ? '后端草案并进行 revision 校验' : '浏览器 Mock 草案' }}。</p>
          <div class="mt-5 flex items-center gap-3 rounded-xl bg-slate-50 p-4 text-sm font-bold text-slate-700">
            <span class="min-w-0 flex-1 truncate">{{ taskLabel }}</span>
            <ArrowRight class="size-4 shrink-0 text-slate-400" />
            <span class="text-teal-700">{{ machineMap.get(pendingMove.targetMachineId)?.name ?? pendingMove.targetMachineId }}</span>
          </div>
          <ul class="mt-4 space-y-2">
            <li
              v-for="reason in pendingMoveValidation?.reasons"
              :key="reason"
              class="flex items-start gap-2 text-[10px]"
              :class="pendingMoveValidation?.allowed ? 'text-teal-700' : 'text-red-700'"
            >
              <Check v-if="pendingMoveValidation?.allowed" class="mt-0.5 size-3 shrink-0" />
              <AlertTriangle v-else class="mt-0.5 size-3 shrink-0" />
              {{ reason }}
            </li>
          </ul>
          <div class="mt-6 flex justify-end gap-3">
            <button type="button" class="h-10 rounded-lg border border-slate-200 px-4 text-sm font-bold text-slate-700" @click="emit('cancelMove')">取消</button>
            <button
              type="button"
              class="h-10 rounded-lg bg-teal-700 px-4 text-sm font-black text-white disabled:cursor-not-allowed disabled:bg-slate-300"
              :disabled="!pendingMoveValidation?.allowed"
              @click="emit('confirmMove')"
            >通过校验并加入草案</button>
          </div>
        </section>
      </div>
    </Transition>

    <Transition name="injection-fade">
      <div v-if="optimizerOpen && optimizationResult" class="fixed inset-0 z-[82] grid place-items-center bg-slate-950/45 p-4 backdrop-blur-[2px]">
        <section class="grid max-h-[88dvh] w-full max-w-[900px] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-2xl bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="optimizer-title">
          <header class="flex items-start gap-3 border-b border-slate-200 px-5 py-4">
            <span class="grid size-10 place-items-center rounded-xl bg-teal-50 text-teal-700"><Sparkles class="size-5" /></span>
            <div class="min-w-0 flex-1">
              <h2 id="optimizer-title" class="text-lg font-black text-slate-950">智能排程模拟</h2>
              <p class="mt-1 text-[10px] text-slate-500">硬约束过滤 → 交期排序 → 同模同色成组 → 插入仿真 → 局部优化</p>
            </div>
            <button type="button" class="grid size-8 place-items-center rounded-lg border border-slate-200" aria-label="关闭智能排程" @click="emit('closeOptimizer')"><X class="size-4" /></button>
          </header>
          <div class="grid min-h-0 gap-4 overflow-y-auto p-5 md:grid-cols-[260px_minmax(0,1fr)]">
            <div class="space-y-2">
              <article
                v-for="(step, index) in optimizationResult.steps"
                :key="step.code"
                class="grid min-h-12 grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-2 rounded-xl border p-2.5"
                :class="index < optimizerStepIndex ? 'border-teal-200 bg-teal-50/50' : index === optimizerStepIndex ? 'border-teal-400' : 'border-slate-200'"
              >
                <span class="grid size-7 place-items-center rounded-lg text-[9px] font-black" :class="index < optimizerStepIndex ? 'bg-teal-100 text-teal-800' : 'bg-slate-100 text-slate-500'">
                  <Check v-if="index < optimizerStepIndex" class="size-3" />
                  <template v-else>{{ index + 1 }}</template>
                </span>
                <div class="min-w-0"><strong class="block text-[10px] text-slate-800">{{ step.label }}</strong><span class="block truncate text-[8px] text-slate-400">{{ step.detail }}</span></div>
                <span class="text-[8px] font-bold text-slate-400">{{ index < optimizerStepIndex ? '完成' : index === optimizerStepIndex ? '执行中' : '等待' }}</span>
              </article>
            </div>
            <div class="rounded-2xl bg-gradient-to-br from-[#102e2c] to-[#081d1b] p-4 text-teal-50">
              <div class="flex items-center justify-between text-[10px]"><strong>排程引擎执行记录</strong><span class="text-teal-300">{{ optimizerComplete ? '建议已生成' : '运行中' }}</span></div>
              <div class="mt-4 space-y-2 text-[9px] text-teal-200">
                <p v-for="(step, index) in optimizationResult.steps.slice(0, optimizerStepIndex)" :key="step.code">› {{ step.label }}：{{ step.detail }}</p>
              </div>
              <div v-if="optimizerComplete" class="mt-5 grid grid-cols-2 gap-2">
                <div
                  v-for="metric in [
                    ['逾期任务', optimizationResult.after.overdueTaskCount, optimizationResult.before.overdueTaskCount],
                    ['总逾期小时', optimizationResult.after.totalOverdueHours, optimizationResult.before.totalOverdueHours],
                    ['换模次数', optimizationResult.after.moldChangeCount, optimizationResult.before.moldChangeCount],
                    ['转色次数', optimizationResult.after.colorChangeCount, optimizationResult.before.colorChangeCount],
                    ['移动任务', optimizationResult.after.movedTaskCount, optimizationResult.before.movedTaskCount],
                    ['人工确认', optimizationResult.after.manualReviewCount, optimizationResult.before.manualReviewCount],
                  ]"
                  :key="metric[0]"
                  class="rounded-xl bg-white/5 p-3"
                >
                  <span class="block text-[8px] text-teal-300">{{ metric[0] }}</span>
                  <strong class="mt-1 block text-lg">{{ metric[1] }} <small class="text-[8px] font-normal text-teal-300">原 {{ metric[2] }}</small></strong>
                </div>
              </div>
              <p class="mt-4 rounded-lg bg-white/5 p-3 text-[8px] leading-4 text-teal-200">{{ backendConnected ? '应用后将按相同 factoryId 与 revision 保存为后端新草案，当前锁定任务保持不动。' : '演示结果只修改浏览器 Mock 草案，不写生产数据库。' }}</p>
            </div>
          </div>
          <footer class="flex justify-end gap-3 border-t border-slate-200 px-5 py-3">
            <button type="button" class="h-9 rounded-lg border border-slate-200 px-4 text-[10px] font-bold" @click="emit('closeOptimizer')">取消</button>
            <button type="button" class="h-9 rounded-lg bg-teal-700 px-4 text-[10px] font-black text-white disabled:bg-slate-300" :disabled="!optimizerComplete" @click="emit('applyOptimizer')">应用建议草案</button>
          </footer>
        </section>
      </div>
    </Transition>

    <Transition name="injection-fade">
      <div v-if="alertsOpen || rulesOpen || publishOpen" class="fixed inset-0 z-[78] grid place-items-center bg-slate-950/35 p-4" @click.self="alertsOpen ? emit('closeAlerts') : rulesOpen ? emit('closeRules') : emit('closePublish')">
        <section v-if="alertsOpen" class="max-h-[84dvh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl">
          <div class="flex items-start justify-between">
            <div><p class="text-[9px] font-black uppercase tracking-[.16em] text-red-600">Exception center</p><h2 class="mt-2 text-xl font-black">交期异常与预警</h2></div>
            <button type="button" class="grid size-9 place-items-center rounded-lg border" aria-label="关闭异常列表" @click="emit('closeAlerts')"><X class="size-4" /></button>
          </div>
          <div class="mt-5 grid gap-3 sm:grid-cols-2">
            <article v-for="task in alertTasks" :key="task.id" class="rounded-xl border border-red-100 bg-red-50/50 p-4">
              <strong class="text-[11px] text-red-900">{{ machineMap.get(task.machineId)?.name }} · {{ task.requirement.mold.moldNo }}</strong>
              <p class="mt-2 text-[9px] leading-5 text-red-700">{{ task.risk === 'incomplete' ? task.changeover.reason : `${formatSlack(task.timing.slackHours)}，优先级 ${task.requirement.priorityCode}。` }}</p>
            </article>
          </div>
        </section>

        <section v-else-if="rulesOpen" class="max-h-[84dvh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl">
          <div class="flex items-start justify-between">
            <div><p class="text-[9px] font-black uppercase tracking-[.16em] text-teal-700">Rule preview</p><h2 class="mt-2 text-xl font-black">排程规则与约束</h2></div>
            <button type="button" class="grid size-9 place-items-center rounded-lg border" aria-label="关闭规则说明" @click="emit('closeRules')"><X class="size-4" /></button>
          </div>
          <div class="mt-5 grid gap-3 sm:grid-cols-2">
            <article
              v-for="(item, index) in [
                ['硬约束优先', '模具尺寸、模厚、开模/顶出、整啤毛重、机械手、抽芯、绞牙、材料螺杆和资源状态全部校验。'],
                ['缺资料不放行', '关键主数据缺失返回 incomplete，未覆盖机型返回 missing-rule，均不得按 0 小时通过。'],
                ['当前任务锁定', '正在生产和人工锁定任务不参与优化；后续移动必须校验并二次确认。'],
                ['厂区与版本', '所有未来写操作都必须携带 factoryId、revision、原因和规则版本。'],
              ]"
              :key="item[0]"
              class="flex gap-3 rounded-xl border border-slate-200 p-4"
            >
              <span class="grid size-7 shrink-0 place-items-center rounded-lg bg-teal-50 text-xs font-black text-teal-700">{{ index + 1 }}</span>
              <div><strong class="text-[11px] text-slate-900">{{ item[0] }}</strong><p class="mt-1 text-[9px] leading-5 text-slate-500">{{ item[1] }}</p></div>
            </article>
          </div>
          <div class="mt-4 overflow-x-auto rounded-xl border border-slate-200">
            <table class="w-full text-left text-[9px]">
              <thead class="bg-slate-50 text-slate-500"><tr><th class="px-3 py-2">机型</th><th class="px-3 py-2">换模</th><th class="px-3 py-2">转色</th><th class="px-3 py-2">状态</th></tr></thead>
              <tbody>
                <tr v-for="machineClass in ['4A', '5A', '7A', '10A', '12A', '14A', '18A', '24A', '32A', '60A', '80A'] as const" :key="machineClass" class="border-t border-slate-100">
                  <td class="px-3 py-2 font-black">{{ machineClass }}</td>
                  <td class="px-3 py-2">{{ moldChangeHoursByMachineClass[machineClass] ?? '缺规则' }}</td>
                  <td class="px-3 py-2">{{ colorChangeHoursByMachineClass[machineClass] ?? '缺规则' }}</td>
                  <td class="px-3 py-2" :class="moldChangeHoursByMachineClass[machineClass] ? 'text-teal-700' : 'text-violet-700'">{{ moldChangeHoursByMachineClass[machineClass] ? '已配置' : '需人工确认' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-else class="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
          <span class="grid size-11 place-items-center rounded-xl bg-teal-50 text-teal-700"><ClipboardCheck class="size-5" /></span>
          <h2 class="mt-4 text-xl font-black">发布大屏快照</h2>
          <p class="mt-2 text-sm leading-6 text-slate-600">{{ backendConnected ? '确认后由后端校验权限与 revision，并创建当前厂区的不可变发布版本。' : '当前显示 Mock 数据，本次确认不会写入数据库或创建发布版本。' }}</p>
          <div class="mt-5 grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-4 text-[10px]">
            <span>发布厂区 <b class="block text-slate-800">{{ factoryName }}</b></span>
            <span>计划版本 <b class="block text-slate-800">{{ plan.label }} · r{{ plan.revision }}</b></span>
          </div>
          <div class="mt-4 flex items-start gap-3 rounded-xl bg-amber-50 p-4 text-xs leading-5 text-amber-800">
            <ShieldCheck class="mt-0.5 size-4 shrink-0" />{{ backendConnected ? '发布会保存操作者、原因、版本哈希与审计记录。' : '请先导入并确认正式工作簿，再执行发布。' }}
          </div>
          <div class="mt-6 flex justify-end gap-3">
            <button type="button" class="h-10 rounded-lg border border-slate-200 px-4 text-sm font-bold" @click="emit('closePublish')">返回检查</button>
            <button type="button" class="inline-flex h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 text-sm font-black text-white" @click="emit('publish')"><CheckCircle2 class="size-4" />{{ backendConnected ? '确认发布正式版本' : '确认 Mock 提示' }}</button>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style>
.injection-fade-enter-active,
.injection-fade-leave-active { transition: opacity 180ms ease; }
.injection-fade-enter-from,
.injection-fade-leave-to { opacity: 0; }
@media (prefers-reduced-motion: reduce) {
  .injection-fade-enter-active,
  .injection-fade-leave-active { transition: none; }
}
</style>
