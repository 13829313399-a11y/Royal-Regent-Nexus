<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ChevronDown, Download } from '@lucide/vue'
import { moldingSampleApi } from '@/api/moldingSample'
import { Button } from '@/components/ui/button'
import { saveSpreadsheetBlob } from '@/features/spreadsheet-merge/mergeHelpers'
import { formatBusinessDate } from '@/lib/dateTime'
import { getApiErrorMessageAsync } from '@/lib/http'
import type { MoldingSampleWorkflowRecord } from '@/types/moldingSample'

const props = defineProps<{
  factoryId: string
  factoryName: string
  records: MoldingSampleWorkflowRecord[]
  queueState: 'checking' | 'connected' | 'empty' | 'error'
}>()

const currentMonth = formatBusinessDate(new Date().toISOString()).slice(0, 7)
const monthPattern = /^[0-9]{4}-(0[1-9]|1[0-2])$/
const customMonth = ref<string | null>(null)
const busy = ref(false)
const feedback = ref('')
const failed = ref(false)
let request: AbortController | undefined

const months = computed(() => {
  const counts = new Map<string, { orders: number, items: number }>()
  for (const { order, items } of props.records) {
    const key = order.date.slice(0, 7)
    if (!monthPattern.test(key)) continue
    const total = counts.get(key) ?? { orders: 0, items: 0 }
    total.orders += 1
    total.items += items.length
    counts.set(key, total)
  }
  return counts
})
const defaultMonth = computed(() => months.value.has(currentMonth)
  ? currentMonth
  : [...months.value.keys()].sort().at(-1) ?? currentMonth)
const month = computed({
  get: () => customMonth.value ?? defaultMonth.value,
  set: (value: string) => { customMonth.value = value },
})
const validMonth = computed(() => monthPattern.test(month.value))
const count = computed(() => months.value.get(month.value))
const queueReady = computed(() => props.queueState === 'connected' || props.queueState === 'empty')
const canDownload = computed(() => validMonth.value && !busy.value && props.queueState !== 'checking'
  && (!queueReady.value || Boolean(count.value)))

watch(month, () => { feedback.value = '' })
onBeforeUnmount(() => request?.abort())

async function download() {
  if (!canDownload.value) return
  const controller = new AbortController()
  request = controller
  busy.value = true
  feedback.value = ''
  failed.value = false
  const selectedMonth = month.value
  customMonth.value = selectedMonth
  try {
    const workbook = await moldingSampleApi.exportProductionMonth(props.factoryId, selectedMonth, controller.signal)
    if (controller.signal.aborted) return
    if (!workbook?.size) {
      feedback.value = '该月暂无可导出的啤办单。'
      return
    }
    saveSpreadsheetBlob(workbook, `${props.factoryName}-${selectedMonth}-啤办单对账明细.xlsx`)
    feedback.value = `${props.factoryName} ${selectedMonth} 的啤办单已开始下载。`
  } catch (error) {
    const reason = await getApiErrorMessageAsync(error)
    if (!controller.signal.aborted) {
      failed.value = true
      feedback.value = `导出失败：${reason}`
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <details class="group mt-2 rounded-lg border border-slate-200 bg-white">
    <summary class="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-lg px-2.5 text-xs font-semibold text-[#17385e] hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-ring sm:min-h-9 [&::-webkit-details-marker]:hidden">
      <Download class="size-3.5 text-teal-700" aria-hidden="true" />
      按月导出啤办单
      <ChevronDown class="ml-auto size-3.5 text-slate-500 group-open:rotate-180" aria-hidden="true" />
    </summary>
    <form class="space-y-2 border-t border-slate-100 px-2.5 py-2.5" @submit.prevent="download">
      <label for="production-export-month" class="block text-xs font-semibold text-slate-700">开单月份</label>
      <div class="flex flex-wrap items-center gap-2">
        <input
          id="production-export-month" v-model="month" type="month" required :disabled="busy" aria-describedby="production-export-scope"
          class="h-11 min-w-0 max-w-full flex-1 basis-32 rounded-lg border border-input bg-card px-2 text-sm text-slate-800 outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 sm:h-9"
        >
        <Button type="submit" size="sm" class="min-h-11 motion-reduce:transition-none sm:min-h-9" :disabled="!canDownload" :aria-busy="busy">
          {{ busy ? '正在导出…' : '导出 Excel' }}
        </Button>
      </div>
      <p id="production-export-scope" class="text-[11px] leading-relaxed text-slate-600" role="status">
        <template v-if="queueState === 'checking'">正在读取生产队列…</template>
        <template v-else-if="!validMonth">请选择开单月份。</template>
        <template v-else-if="!queueReady">将从服务器读取该月单据。</template>
        <template v-else-if="count">{{ factoryName }}整月共 {{ count.orders }} 张啤办单，{{ count.items }} 项模具明细。可逐模对账，费用和仓库明细按权限显示。</template>
        <template v-else>{{ factoryName }}在该月没有进入生产队列的啤办单。</template>
      </p>
      <p v-if="feedback" :role="failed ? 'alert' : 'status'" class="break-words text-xs" :class="failed ? 'text-red-700' : 'text-teal-800'">{{ feedback }}</p>
    </form>
  </details>
</template>
