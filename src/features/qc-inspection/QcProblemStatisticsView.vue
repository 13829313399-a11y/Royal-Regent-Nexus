<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Search, ShieldCheck } from '@lucide/vue'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { qcInspectionApi, type QcInspectionProblem } from '@/api/qcInspection'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { useQcInspectionWorkspace } from './context'

const context = useQcInspectionWorkspace()
const route = useRoute()
const searchQuery = ref('')
const selectedProblemId = ref('')
const saving = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const form = reactive({
  status: 'DRAFT',
  category: '',
  description: '',
  return_reason: '',
  corrective_action: '',
  resolution: '',
  primary_responsible_person: '',
  secondary_responsible_person: '',
})

const problems = computed(() => context.workspace.value?.problems ?? [])
const orderById = computed(() => new Map(
  (context.workspace.value?.orders ?? []).map((order) => [order.id, order]),
))
const orderForProblem = (problem: QcInspectionProblem) => orderById.value.get(problem.inspection_order_id)
const filteredProblems = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase()
  const orderFilter = typeof route.query.order === 'string' ? route.query.order : ''
  return problems.value.filter((problem) => {
    const order = orderForProblem(problem)
    if (orderFilter && problem.inspection_order_id !== orderFilter) return false
    if (!query) return true
    return [
      problem.problem_no,
      order?.inspection_no,
      order?.customer_name,
      order?.sales_contract_no,
      order?.customer_po_no,
      order?.customer_item_no,
      problem.description,
    ].some((value) => String(value ?? '').toLocaleLowerCase().includes(query))
  })
})
const selectedProblem = computed(() => problems.value.find((problem) => problem.id === selectedProblemId.value) ?? null)
const openCount = computed(() => problems.value.filter((problem) => ['DRAFT', 'OPEN', 'IN_PROGRESS'].includes(problem.status)).length)
const resolvedCount = computed(() => problems.value.filter((problem) => ['RESOLVED', 'CLOSED'].includes(problem.status)).length)
const returnCount = computed(() => problems.value.filter((problem) => Boolean(problem.return_reason)).length)

const statusLabels: Record<string, string> = {
  DRAFT: '待补充',
  OPEN: '已登记',
  IN_PROGRESS: '处理中',
  RESOLVED: '已解决',
  CLOSED: '已关闭',
  CANCELLED: '已取消',
}

function selectProblem(problem: QcInspectionProblem) {
  selectedProblemId.value = problem.id
}

watch(selectedProblem, (problem) => {
  if (!problem) return
  form.status = problem.status
  form.category = problem.category ?? ''
  form.description = problem.description ?? ''
  form.return_reason = problem.return_reason ?? ''
  form.corrective_action = problem.corrective_action ?? ''
  form.resolution = problem.resolution ?? ''
  form.primary_responsible_person = problem.primary_responsible_person ?? ''
  form.secondary_responsible_person = problem.secondary_responsible_person ?? ''
  errorMessage.value = ''
  successMessage.value = ''
}, { immediate: true })

watch(filteredProblems, (current) => {
  if (!selectedProblemId.value || !current.some((problem) => problem.id === selectedProblemId.value)) {
    selectedProblemId.value = current[0]?.id ?? ''
  }
}, { immediate: true })

async function saveProblem() {
  const problem = selectedProblem.value
  if (!problem || !context.canProblemWrite.value) return
  errorMessage.value = ''
  successMessage.value = ''
  if (!form.description.trim()) {
    errorMessage.value = '请填写验货问题描述。'
    return
  }
  saving.value = true
  try {
    await qcInspectionApi.updateProblem(problem.id, {
      factory_id: context.factoryId.value,
      expected_revision: problem.revision,
      reason: 'QC 在问题统计页更新验货问题内容',
      status: form.status,
      category: form.category.trim() || null,
      description: form.description.trim(),
      return_reason: form.return_reason.trim() || null,
      corrective_action: form.corrective_action.trim() || null,
      resolution: form.resolution.trim() || null,
      primary_responsible_person: form.primary_responsible_person.trim() || null,
      secondary_responsible_person: form.secondary_responsible_person.trim() || null,
    })
    await context.refresh()
    successMessage.value = '问题记录已保存，并将作为验货主单和下游报表的只读来源。'
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="grid gap-4 sm:grid-cols-3">
      <article v-for="metric in [
        { label: '问题记录', value: problems.length, tone: 'text-slate-950' },
        { label: '待补充 / 处理中', value: openCount, tone: 'text-amber-700' },
        { label: '已解决 / 已关闭', value: resolvedCount, tone: 'text-emerald-700' },
      ]" :key="metric.label" class="enterprise-panel rounded-xl p-5">
        <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">{{ metric.label }}</p>
        <p class="mt-2 text-3xl font-semibold" :class="metric.tone">{{ metric.value }}</p>
      </article>
    </div>

    <div class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_430px]">
      <SectionPanel title="每周验货问题统计" subtitle="只在此处维护问题内容；验货主单及五类报表中的问题字段均为只读镜像。">
        <template #action>
          <label class="relative block">
            <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <input v-model="searchQuery" type="search" placeholder="问题号、客户、合同、PO 或货号" class="h-10 w-72 max-w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-sm outline-none focus:border-teal-500">
          </label>
        </template>

        <div v-if="!filteredProblems.length" class="grid min-h-52 place-items-center rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
          <div><ShieldCheck class="mx-auto size-8 text-slate-400" aria-hidden="true" /><p class="mt-3 font-semibold text-slate-800">{{ problems.length ? '没有匹配的问题记录' : '当前周暂无验货问题' }}</p><p class="mt-1 text-sm text-slate-500">非 PASS 或在主单勾选“有问题”后，系统会生成待补充记录。</p></div>
        </div>
        <div v-else class="space-y-3">
          <button
            v-for="problem in filteredProblems"
            :key="problem.id"
            type="button"
            class="w-full rounded-xl border p-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
            :class="selectedProblemId === problem.id ? 'border-teal-300 bg-teal-50/60' : 'border-slate-200 bg-white hover:border-teal-200'"
            @click="selectProblem(problem)"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div><p class="font-semibold text-slate-950">{{ problem.problem_no || problem.id }}</p><p class="mt-1 text-xs text-slate-500">{{ orderForProblem(problem)?.customer_name || '主单上下文不可用' }} · {{ orderForProblem(problem)?.customer_po_no || '—' }} · {{ orderForProblem(problem)?.customer_item_no || '—' }}</p></div>
              <StatusPill :label="statusLabels[problem.status] || problem.status" :tone="['RESOLVED', 'CLOSED'].includes(problem.status) ? 'green' : problem.status === 'CANCELLED' ? 'slate' : 'amber'" compact />
            </div>
            <p class="mt-3 line-clamp-2 text-sm leading-6 text-slate-700">{{ problem.description || '问题内容待补充' }}</p>
          </button>
        </div>
      </SectionPanel>

      <SectionPanel title="问题单点录入" subtitle="问题描述、退货原因、责任人、纠正措施和处理结果只在这里编辑。">
        <div v-if="!selectedProblem" class="grid min-h-52 place-items-center text-center text-sm text-slate-500">请选择一条问题记录。</div>
        <form v-else class="space-y-4" @submit.prevent="saveProblem">
          <div v-if="!context.canProblemWrite.value" class="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">当前为只读访问，不能修改问题内容。</div>
          <label class="block space-y-1.5"><span class="text-sm font-semibold text-slate-700">状态</span><select v-model="form.status" :disabled="!context.canProblemWrite.value || saving" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50"><option v-for="status in ['DRAFT','OPEN','IN_PROGRESS','RESOLVED','CLOSED','CANCELLED']" :key="status" :value="status">{{ statusLabels[status] }}</option></select></label>
          <label class="block space-y-1.5"><span class="text-sm font-semibold text-slate-700">问题类别</span><input v-model="form.category" :disabled="!context.canProblemWrite.value || saving" class="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50" placeholder="例如外观、功能、包装"></label>
          <label class="block space-y-1.5"><span class="text-sm font-semibold text-slate-700">验货问题 <b class="text-red-600">*</b></span><textarea v-model="form.description" rows="4" :disabled="!context.canProblemWrite.value || saving" class="w-full rounded-lg border border-slate-200 p-3 text-sm leading-6 outline-none focus:border-teal-500 disabled:bg-slate-50" /></label>
          <label class="block space-y-1.5"><span class="text-sm font-semibold text-slate-700">退货原因</span><textarea v-model="form.return_reason" rows="2" :disabled="!context.canProblemWrite.value || saving" class="w-full rounded-lg border border-slate-200 p-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50" /></label>
          <div class="grid gap-4 sm:grid-cols-2">
            <label class="block space-y-1.5"><span class="text-sm font-semibold text-slate-700">第一责任人</span><input v-model="form.primary_responsible_person" :disabled="!context.canProblemWrite.value || saving" class="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50"></label>
            <label class="block space-y-1.5"><span class="text-sm font-semibold text-slate-700">第二责任人</span><input v-model="form.secondary_responsible_person" :disabled="!context.canProblemWrite.value || saving" class="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50"></label>
          </div>
          <label class="block space-y-1.5"><span class="text-sm font-semibold text-slate-700">纠正措施</span><textarea v-model="form.corrective_action" rows="2" :disabled="!context.canProblemWrite.value || saving" class="w-full rounded-lg border border-slate-200 p-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50" /></label>
          <label class="block space-y-1.5"><span class="text-sm font-semibold text-slate-700">处理结果</span><textarea v-model="form.resolution" rows="2" :disabled="!context.canProblemWrite.value || saving" class="w-full rounded-lg border border-slate-200 p-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50" /></label>
          <p v-if="returnCount" class="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800"><AlertTriangle class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />当前周有 {{ returnCount }} 条记录填写了退货原因。</p>
          <p v-if="errorMessage" role="alert" class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{{ errorMessage }}</p>
          <p v-if="successMessage" class="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"><CheckCircle2 class="mt-0.5 size-4 shrink-0" aria-hidden="true" />{{ successMessage }}</p>
          <Button type="submit" class="w-full" :disabled="!context.canProblemWrite.value || saving">{{ saving ? '保存中…' : '保存问题记录' }}</Button>
        </form>
      </SectionPanel>
    </div>
  </div>
</template>
