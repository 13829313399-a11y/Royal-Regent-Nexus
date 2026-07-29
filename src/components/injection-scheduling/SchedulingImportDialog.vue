<script setup lang="ts">
import { AlertTriangle, CheckCircle2, FileSpreadsheet, LoaderCircle, Upload, X } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import type { InjectionSchedulingImportPreview } from '@/api/injectionScheduling'

const props = defineProps<{
  open: boolean
  busy: boolean
  error: string
  preview: InjectionSchedulingImportPreview | null
  factoryName: string
}>()

const emit = defineEmits<{
  close: []
  preview: [file: File, businessDate: string]
  confirm: [reason: string]
}>()

const selectedFile = ref<File | null>(null)
const businessDate = ref('')
const reason = ref('确认导入只读工作簿并建立正式排程草案')

const canPreview = computed(() => Boolean(selectedFile.value && businessDate.value && !props.busy))
const canConfirm = computed(() => Boolean(
  props.preview?.summary.canConfirm
  && reason.value.trim().length >= 2
  && !props.busy,
))

function localDateText() {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

function chooseFile(event: Event) {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

watch(() => props.open, (open) => {
  if (!open) return
  selectedFile.value = null
  businessDate.value = localDateText()
  reason.value = '确认导入只读工作簿并建立正式排程草案'
}, { immediate: true })
</script>

<template>
  <Teleport to="body">
    <Transition name="injection-fade">
      <div
        v-if="open"
        class="fixed inset-0 z-[90] grid place-items-center bg-slate-950/45 p-4 backdrop-blur-[2px]"
        @click.self="emit('close')"
      >
        <section class="grid max-h-[88dvh] w-full max-w-[760px] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-2xl bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="schedule-import-title">
          <header class="flex items-start gap-3 border-b border-slate-200 px-5 py-4">
            <span class="grid size-10 place-items-center rounded-xl bg-teal-50 text-teal-700"><FileSpreadsheet class="size-5" /></span>
            <div class="min-w-0 flex-1">
              <h2 id="schedule-import-title" class="text-lg font-black text-slate-950">导入 {{ factoryName }} 注塑计划表</h2>
              <p class="mt-1 text-[10px] leading-5 text-slate-500">先只读预览并列出问题；只有再次确认后才写入该厂区的主数据与草案版本。</p>
            </div>
            <button type="button" class="grid size-8 place-items-center rounded-lg border border-slate-200 text-slate-500" aria-label="关闭导入" :disabled="busy" @click="emit('close')"><X class="size-4" /></button>
          </header>

          <div class="min-h-0 overflow-y-auto p-5">
            <div class="grid gap-3 md:grid-cols-[minmax(0,1fr)_170px_auto]">
              <label class="grid min-w-0 gap-1.5 text-[10px] font-black text-slate-700">
                工作簿（.xlsx）
                <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" class="h-10 min-w-0 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium" :disabled="busy" @change="chooseFile">
              </label>
              <label class="grid gap-1.5 text-[10px] font-black text-slate-700">
                业务日期
                <input v-model="businessDate" type="date" class="h-10 rounded-lg border border-slate-200 px-3 text-xs" :disabled="busy">
              </label>
              <button type="button" class="mt-[21px] inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 text-xs font-black text-white disabled:bg-slate-300" :disabled="!canPreview" @click="selectedFile && emit('preview', selectedFile, businessDate)">
                <LoaderCircle v-if="busy" class="size-4 animate-spin" />
                <Upload v-else class="size-4" />
                只读预览
              </button>
            </div>

            <p v-if="error" class="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs leading-5 text-red-700">{{ error }}</p>

            <template v-if="preview">
              <div class="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <article v-for="item in [
                  ['机台', preview.summary.machineCount],
                  ['排程任务', preview.summary.taskCount],
                  ['订单', preview.summary.orderCount],
                  ['警告', preview.summary.warningCount],
                ]" :key="item[0]" class="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <span class="text-[9px] text-slate-500">{{ item[0] }}</span>
                  <strong class="mt-1 block text-lg text-slate-950">{{ item[1] }}</strong>
                </article>
              </div>

              <div class="mt-4 flex items-start gap-2 rounded-xl border p-3 text-xs leading-5" :class="preview.summary.canConfirm ? 'border-teal-200 bg-teal-50 text-teal-800' : 'border-red-200 bg-red-50 text-red-700'">
                <CheckCircle2 v-if="preview.summary.canConfirm" class="mt-0.5 size-4 shrink-0" />
                <AlertTriangle v-else class="mt-0.5 size-4 shrink-0" />
                <span>
                  {{ preview.summary.canConfirm ? '预览无阻断项，可以确认导入。警告项会保留为待人工复核。' : `存在 ${preview.summary.blockerCount} 个阻断项，不能确认导入。` }}
                  <b class="ml-1">批次 r{{ preview.preview_revision }}</b>
                </span>
              </div>

              <div v-if="preview.issues.length" class="mt-4 overflow-hidden rounded-xl border border-slate-200">
                <div class="flex items-center justify-between bg-slate-50 px-3 py-2 text-[10px] font-black text-slate-700">
                  <span>问题清单</span>
                  <span>显示前 30 / 共 {{ preview.issues.length }}</span>
                </div>
                <ul class="max-h-52 divide-y divide-slate-100 overflow-y-auto">
                  <li v-for="issue in preview.issues.slice(0, 30)" :key="issue.id" class="flex items-start gap-2 px-3 py-2 text-[10px] leading-5">
                    <span class="mt-0.5 rounded-full px-2 py-0.5 font-black" :class="issue.severity === 'blocker' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'">{{ issue.severity === 'blocker' ? '阻断' : '警告' }}</span>
                    <span class="min-w-0 text-slate-700">{{ issue.message }}<small v-if="issue.sheet_name" class="ml-2 text-slate-400">{{ issue.sheet_name }}!{{ issue.source_row }}</small></span>
                  </li>
                </ul>
              </div>

              <label class="mt-4 grid gap-1.5 text-[10px] font-black text-slate-700">
                确认原因（写入审计）
                <textarea v-model="reason" rows="2" class="resize-none rounded-lg border border-slate-200 p-3 text-xs font-medium" :disabled="busy" />
              </label>
            </template>
          </div>

          <footer class="flex justify-end gap-3 border-t border-slate-200 px-5 py-4">
            <button type="button" class="h-10 rounded-lg border border-slate-200 px-4 text-xs font-black text-slate-700" :disabled="busy" @click="emit('close')">取消</button>
            <button type="button" class="inline-flex h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 text-xs font-black text-white disabled:bg-slate-300" :disabled="!canConfirm" @click="emit('confirm', reason.trim())">
              <LoaderCircle v-if="busy" class="size-4 animate-spin" />
              <CheckCircle2 v-else class="size-4" />
              确认写入正式草案
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
