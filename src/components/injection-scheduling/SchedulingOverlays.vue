<script setup lang="ts">
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Info,
  LockKeyhole,
  ShieldCheck,
  X,
} from '@lucide/vue'
import { computed } from 'vue'
import type { BacklogOrder, InjectionMachine, ScheduleMoveRequest, ScheduleTask } from '@/types/injectionScheduling'

const props = defineProps<{
  selectedTask: ScheduleTask | null
  machines: InjectionMachine[]
  pendingMove: ScheduleMoveRequest | null
  backlog: BacklogOrder[]
  alertsOpen: boolean
  rulesOpen: boolean
  publishOpen: boolean
}>()

const emit = defineEmits<{
  closeTask: []
  cancelMove: []
  confirmMove: []
  closeAlerts: []
  closeRules: []
  closePublish: []
  publish: []
}>()

const machineMap = computed(() => new Map(props.machines.map((machine) => [machine.id, machine])))
const taskLabel = computed(() => {
  if (props.pendingMove?.taskId) return props.pendingMove.taskId
  const order = props.backlog.find((item) => item.id === props.pendingMove?.backlogId)
  return order ? `${order.moldNo} · ${order.productName}` : ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="injection-fade">
      <div
        v-if="selectedTask"
        class="fixed inset-0 z-[70] bg-slate-950/25 backdrop-blur-[1px]"
        @click.self="emit('closeTask')"
      >
        <aside class="absolute inset-y-0 right-0 w-full max-w-[440px] overflow-y-auto border-l border-slate-200 bg-white p-6 shadow-2xl" aria-label="任务详情">
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="text-[10px] font-black uppercase tracking-[.16em] text-teal-700">Task detail</p>
              <h2 class="mt-2 text-xl font-black text-slate-950">任务详情</h2>
            </div>
            <button type="button" class="grid size-9 place-items-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50" aria-label="关闭任务详情" @click="emit('closeTask')">
              <X class="size-4" aria-hidden="true" />
            </button>
          </div>

          <div class="mt-6 rounded-xl bg-teal-950 p-5 text-white">
            <div class="flex items-center justify-between gap-3">
              <strong class="text-lg">{{ selectedTask.moldNo }}</strong>
              <span v-if="selectedTask.locked" class="inline-flex items-center gap-1 rounded-full bg-white/10 px-2 py-1 text-[10px] text-teal-100">
                <LockKeyhole class="size-3" aria-hidden="true" />当前任务锁定
              </span>
            </div>
            <p class="mt-2 text-sm text-teal-100">{{ selectedTask.productName }}</p>
            <p class="mt-5 text-[11px] text-teal-200">{{ selectedTask.startAt }} → {{ selectedTask.endAt }}</p>
          </div>

          <dl class="mt-5 grid grid-cols-2 gap-3">
            <div v-for="item in [
              ['订单号', selectedTask.orderNo],
              ['机台', machineMap.get(selectedTask.machineId)?.name ?? selectedTask.machineId],
              ['颜色', selectedTask.color],
              ['排产数量', selectedTask.quantity.toLocaleString()],
              ['已完成', selectedTask.completedQuantity.toLocaleString()],
              ['目标/日', selectedTask.dailyTarget.toLocaleString()],
            ]" :key="item[0]" class="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <dt class="text-[10px] text-slate-400">{{ item[0] }}</dt>
              <dd class="mt-1 text-xs font-black text-slate-800">{{ item[1] }}</dd>
            </div>
          </dl>

          <div class="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-6 text-amber-900">
            <strong class="flex items-center gap-2"><Info class="size-4" aria-hidden="true" />排程说明</strong>
            <p class="mt-2">{{ selectedTask.remark ?? '该数据来自前端 Mock 快照，尚未经过后端资格校验。' }}</p>
          </div>
        </aside>
      </div>
    </Transition>

    <Transition name="injection-fade">
      <div v-if="pendingMove" class="fixed inset-0 z-[80] grid place-items-center bg-slate-950/35 p-4 backdrop-blur-[1px]">
        <section class="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="move-title">
          <span class="grid size-11 place-items-center rounded-xl bg-amber-50 text-amber-700">
            <AlertTriangle class="size-5" aria-hidden="true" />
          </span>
          <h2 id="move-title" class="mt-4 text-xl font-black text-slate-950">确认调整排程草案？</h2>
          <p class="mt-2 text-sm leading-6 text-slate-600">调整前会保留当前任务锁定规则；本次操作只修改浏览器内的演示草案。</p>
          <div class="mt-5 flex items-center gap-3 rounded-xl bg-slate-50 p-4 text-sm font-bold text-slate-700">
            <span class="min-w-0 flex-1 truncate">{{ taskLabel }}</span>
            <ArrowRight class="size-4 shrink-0 text-slate-400" aria-hidden="true" />
            <span class="text-teal-700">{{ machineMap.get(pendingMove.targetMachineId)?.name ?? pendingMove.targetMachineId }}</span>
          </div>
          <div class="mt-6 flex justify-end gap-3">
            <button type="button" class="h-10 rounded-lg border border-slate-200 px-4 text-sm font-bold text-slate-700 hover:bg-slate-50" @click="emit('cancelMove')">取消</button>
            <button type="button" class="h-10 rounded-lg bg-teal-700 px-4 text-sm font-black text-white hover:bg-teal-800" @click="emit('confirmMove')">确认调整</button>
          </div>
        </section>
      </div>
    </Transition>

    <Transition name="injection-fade">
      <div v-if="alertsOpen || rulesOpen || publishOpen" class="fixed inset-0 z-[75] grid place-items-center bg-slate-950/35 p-4" @click.self="alertsOpen ? emit('closeAlerts') : rulesOpen ? emit('closeRules') : emit('closePublish')">
        <section v-if="alertsOpen" class="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-2xl">
          <div class="flex items-start justify-between">
            <div><p class="text-[10px] font-black uppercase tracking-[.16em] text-red-600">Exception center</p><h2 class="mt-2 text-xl font-black">交期异常与预警</h2></div>
            <button type="button" class="grid size-9 place-items-center rounded-lg border" aria-label="关闭异常列表" @click="emit('closeAlerts')"><X class="size-4" /></button>
          </div>
          <div class="mt-5 grid gap-3 sm:grid-cols-2">
            <article v-for="item in [
              ['旧3 · PAMT-01M-01', '累计逾期 53.9 天，建议与 PMC 复核交期。'],
              ['新37 · T01-BL201-00200000', '快照交期异常 373.6 天，疑似来源日期需重算。'],
              ['旧2 · GT1214', '当前任务已逾期，后续 1 张订单存在连带风险。'],
              ['待排订单 JP45801-21', '特急订单尚未确认插入新37队列。'],
            ]" :key="item[0]" class="rounded-xl border border-red-100 bg-red-50/50 p-4">
              <strong class="text-sm text-red-900">{{ item[0] }}</strong><p class="mt-2 text-xs leading-5 text-red-700">{{ item[1] }}</p>
            </article>
          </div>
        </section>

        <section v-else-if="rulesOpen" class="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-2xl">
          <div class="flex items-start justify-between">
            <div><p class="text-[10px] font-black uppercase tracking-[.16em] text-teal-700">Rule preview</p><h2 class="mt-2 text-xl font-black">排程规则说明</h2></div>
            <button type="button" class="grid size-9 place-items-center rounded-lg border" aria-label="关闭规则说明" @click="emit('closeRules')"><X class="size-4" /></button>
          </div>
          <div class="mt-5 space-y-3">
            <article v-for="(item, index) in [
              ['机台资格先行', '吨位、机械手、螺杆及抽芯限制必须满足后才可进入候选集。'],
              ['当前任务不可移动', '正在生产的任务保持锁定，仅允许调整后续队列。'],
              ['交期与换模成本平衡', '同色同模优先仅作建议，最终评分需要正式算法和数据。'],
              ['发布必须版本化', '发布前由后端执行并发锁、资格复核与审计。'],
            ]" :key="item[0]" class="flex gap-3 rounded-xl border border-slate-200 p-4">
              <span class="grid size-7 shrink-0 place-items-center rounded-lg bg-teal-50 text-xs font-black text-teal-700">{{ index + 1 }}</span>
              <div><strong class="text-sm text-slate-900">{{ item[0] }}</strong><p class="mt-1 text-xs leading-5 text-slate-500">{{ item[1] }}</p></div>
            </article>
          </div>
        </section>

        <section v-else class="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
          <span class="grid size-11 place-items-center rounded-xl bg-teal-50 text-teal-700"><ClipboardCheck class="size-5" /></span>
          <h2 class="mt-4 text-xl font-black">发布计划</h2>
          <p class="mt-2 text-sm leading-6 text-slate-600">当前页面尚未连接排程后端，发布不会写入数据库。你可以继续体验发布确认流程。</p>
          <div class="mt-5 flex items-start gap-3 rounded-xl bg-amber-50 p-4 text-xs leading-5 text-amber-800">
            <ShieldCheck class="mt-0.5 size-4 shrink-0" />正式接入后，这里会校验版本号、权限、机台资格和任务冲突。
          </div>
          <div class="mt-6 flex justify-end gap-3">
            <button type="button" class="h-10 rounded-lg border border-slate-200 px-4 text-sm font-bold" @click="emit('closePublish')">取消</button>
            <button type="button" class="inline-flex h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 text-sm font-black text-white" @click="emit('publish')"><CheckCircle2 class="size-4" />确认演示</button>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style>
.injection-fade-enter-active,
.injection-fade-leave-active { transition: opacity 160ms ease; }
.injection-fade-enter-from,
.injection-fade-leave-to { opacity: 0; }
</style>
