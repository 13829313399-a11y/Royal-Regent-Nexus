<script setup lang="ts">
import axios from 'axios'
import { AlertTriangle, ArrowLeft, CheckCircle2, LoaderCircle, Save } from '@lucide/vue'
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { qcInspectionApi, type QcInspectionOrder } from '@/api/qcInspection'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { useQcInspectionWorkspace } from './context'

const context = useQcInspectionWorkspace()
const route = useRoute()
const order = ref<QcInspectionOrder | null>(null)
const loading = ref(true)
const saving = ref(false)
const forbidden = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const form = reactive({
  actual_inspection_date: '',
  inspection_result: 'PENDING',
  inspection_agency: '',
  packing: '',
  carton_count: '',
  report_status: '',
  production_department: '',
  manual_has_problem: false,
})

const resultOptions = [
  { value: 'PENDING', label: '待验货' },
  { value: 'PASS', label: 'PASS' },
  { value: 'CONDITIONAL_PASS', label: '有条件通过' },
  { value: 'FAIL', label: '不通过' },
  { value: 'REJECTED', label: '退货' },
  { value: 'CANCELLED', label: '取消' },
]

const orderId = computed(() => String(route.params.orderId ?? ''))
const createsPendingProblem = computed(() => form.manual_has_problem
  || (form.inspection_result !== 'PENDING' && form.inspection_result !== 'PASS'))

function applyOrder(value: QcInspectionOrder) {
  order.value = value
  form.actual_inspection_date = value.actual_inspection_date ?? ''
  form.inspection_result = value.inspection_result ?? 'PENDING'
  form.inspection_agency = value.inspection_agency ?? ''
  form.packing = value.packing ?? ''
  form.carton_count = value.carton_count ?? ''
  form.report_status = value.report_status ?? ''
  form.production_department = value.production_department ?? ''
  form.manual_has_problem = value.manual_has_problem ?? false
}

async function loadOrder() {
  loading.value = true
  forbidden.value = false
  errorMessage.value = ''
  successMessage.value = ''
  try {
    applyOrder(await qcInspectionApi.getOrder(orderId.value, context.factoryId.value))
  } catch (error) {
    order.value = null
    forbidden.value = axios.isAxiosError(error) && error.response?.status === 403
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

async function saveResult() {
  if (!order.value || !context.canResultWrite.value) return
  errorMessage.value = ''
  successMessage.value = ''
  if (form.inspection_result !== 'PENDING' && !form.actual_inspection_date) {
    errorMessage.value = '填写验货结论时必须填写实际验货日期。'
    return
  }
  saving.value = true
  try {
    const updated = await qcInspectionApi.updateOrder(order.value.id, {
      factory_id: context.factoryId.value,
      expected_revision: order.value.revision,
      reason: 'QC 在验货主单详情更新实际验货结果',
      actual_inspection_date: form.actual_inspection_date || null,
      inspection_result: form.inspection_result,
      inspection_agency: form.inspection_agency.trim() || null,
      packing: form.packing.trim() || null,
      carton_count: form.carton_count.trim() || null,
      report_status: form.report_status.trim() || null,
      production_department: form.production_department.trim() || null,
      manual_has_problem: form.manual_has_problem,
    })
    applyOrder(updated)
    successMessage.value = createsPendingProblem.value
      ? '验货结果已保存；系统已创建或保留一条待补充问题记录。'
      : '验货结果已保存。PASS 且未勾选有问题，不会创建问题记录。'
    await context.refresh()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    saving.value = false
  }
}

watch(orderId, () => {
  void loadOrder()
}, { immediate: true })
</script>

<template>
  <div class="space-y-6">
    <RouterLink :to="{ name: 'qc-inspection-schedule', query: { factory: context.factoryId.value, week: context.weekKey.value } }" class="inline-flex items-center gap-2 text-sm font-semibold text-teal-700 hover:text-teal-900">
      <ArrowLeft class="size-4" aria-hidden="true" />返回验货排期
    </RouterLink>

    <SectionPanel v-if="loading" title="正在读取验货主单">
      <div class="grid min-h-52 place-items-center"><LoaderCircle class="size-7 animate-spin text-teal-700" aria-label="正在加载" /></div>
    </SectionPanel>

    <SectionPanel v-else-if="forbidden" title="无权查看此验货主单" subtitle="验货主单按厂区和 QC 权限隔离。">
      <p role="alert" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">{{ errorMessage }}</p>
    </SectionPanel>

    <SectionPanel v-else-if="!order" title="验货主单不可用">
      <div role="alert" class="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        <p>{{ errorMessage || '没有找到对应验货主单。' }}</p>
        <Button type="button" variant="outline" class="mt-3" @click="loadOrder">重新加载</Button>
      </div>
    </SectionPanel>

    <template v-else>
      <SectionPanel :title="order.inspection_no || '验货主单'" subtitle="每次验货拥有独立系统 ID；问题字段在问题统计页维护，此处仅显示只读镜像。">
        <template #action><StatusPill :label="order.status || 'SCHEDULED'" :tone="order.status === 'COMPLETED' ? 'green' : 'blue'" /></template>
        <dl class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="item in [
            ['客户', order.customer_name],
            ['合同号', order.sales_contract_no],
            ['PO', order.customer_po_no],
            ['客户货号', order.customer_item_no],
            ['产品名称', order.product_name],
            ['数量', String(order.quantity)],
            ['装箱', order.packing || '—'],
            ['箱数', order.carton_count || '—'],
            ['出口国', order.export_country_code],
            ['走货期', order.shipment_date],
            ['计划验货期', order.planned_inspection_date],
            ['来源', order.source_type || '—'],
            ['验货机构', order.inspection_agency || '—'],
            ['报告', order.report_status || '—'],
            ['生产部门', order.production_department || '—'],
            ['跟客人员', order.account_manager || '—'],
          ]" :key="item[0]" class="rounded-xl border border-slate-200 bg-slate-50/60 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-500">{{ item[0] }}</dt>
            <dd class="mt-1 break-words text-sm font-semibold text-slate-900">{{ item[1] }}</dd>
          </div>
        </dl>
      </SectionPanel>

      <div class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <SectionPanel title="验货执行与结果" subtitle="实际验货结果只在验货主单详情录入。">
          <div v-if="!context.canResultWrite.value" class="mb-5 rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">当前为只读访问，不能填写验货结果。</div>
          <form class="grid gap-4 sm:grid-cols-2" @submit.prevent="saveResult">
            <label class="space-y-1.5">
              <span class="text-sm font-semibold text-slate-700">实际验货日期</span>
              <input v-model="form.actual_inspection_date" type="date" :disabled="!context.canResultWrite.value || saving" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50">
            </label>
            <label class="space-y-1.5">
              <span class="text-sm font-semibold text-slate-700">验货结果</span>
              <select v-model="form.inspection_result" :disabled="!context.canResultWrite.value || saving" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50">
                <option v-for="option in resultOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </label>
            <label class="space-y-1.5 sm:col-span-2">
              <span class="text-sm font-semibold text-slate-700">验货机构</span>
              <input v-model="form.inspection_agency" type="text" :disabled="!context.canResultWrite.value || saving" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50">
            </label>
            <label class="space-y-1.5">
              <span class="text-sm font-semibold text-slate-700">装箱</span>
              <input v-model="form.packing" type="text" :disabled="!context.canResultWrite.value || saving" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50" placeholder="按现有验货表原值填写">
            </label>
            <label class="space-y-1.5">
              <span class="text-sm font-semibold text-slate-700">箱数</span>
              <input v-model="form.carton_count" type="text" :disabled="!context.canResultWrite.value || saving" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50" placeholder="按现有验货表原值填写">
            </label>
            <label class="space-y-1.5">
              <span class="text-sm font-semibold text-slate-700">报告</span>
              <input v-model="form.report_status" type="text" :disabled="!context.canResultWrite.value || saving" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50" placeholder="例如：有、待补">
            </label>
            <label class="space-y-1.5">
              <span class="text-sm font-semibold text-slate-700">生产部门</span>
              <input v-model="form.production_department" type="text" :disabled="!context.canResultWrite.value || saving" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-500 disabled:bg-slate-50">
            </label>
            <label class="sm:col-span-2 flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <input v-model="form.manual_has_problem" type="checkbox" :disabled="!context.canResultWrite.value || saving" class="mt-1 size-4 accent-teal-700">
              <span><b class="text-sm text-slate-900">本次验货有问题</b><span class="mt-1 block text-xs leading-5 text-slate-500">即使结果为 PASS，也可人工标记并生成待补问题记录。</span></span>
            </label>
            <div v-if="createsPendingProblem" class="sm:col-span-2 flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              <AlertTriangle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />保存后会生成或复用待补问题记录，问题描述、退货原因和处理结果必须到“问题统计”页填写。
            </div>
            <p v-if="errorMessage" role="alert" class="sm:col-span-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{{ errorMessage }}</p>
            <p v-if="successMessage" class="sm:col-span-2 flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"><CheckCircle2 class="mt-0.5 size-4 shrink-0" aria-hidden="true" />{{ successMessage }}</p>
            <div class="sm:col-span-2 flex justify-end"><Button type="submit" :disabled="!context.canResultWrite.value || saving"><Save class="size-4" aria-hidden="true" />{{ saving ? '保存中…' : '保存验货结果' }}</Button></div>
          </form>
        </SectionPanel>

        <SectionPanel title="问题只读镜像" subtitle="权威内容来自问题统计模块。">
          <div v-if="order.has_problem || order.problem_count" class="space-y-4">
            <StatusPill :label="`${order.problem_count || 1} 条问题记录`" tone="red" />
            <p class="rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-700">{{ order.problem_summary || '问题记录待 QC 在问题统计页补充。' }}</p>
            <RouterLink :to="{ name: 'qc-inspection-problems', query: { factory: context.factoryId.value, week: context.weekKey.value, order: order.id } }" class="inline-flex font-semibold text-teal-700 hover:text-teal-900">前往问题统计补充</RouterLink>
          </div>
          <div v-else class="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center text-sm text-slate-500">当前主单没有问题记录。</div>
        </SectionPanel>
      </div>
    </template>
  </div>
</template>
