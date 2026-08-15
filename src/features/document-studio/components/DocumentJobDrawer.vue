<script setup lang="ts">
import { Clock3, Download, History, LoaderCircle, X } from '@lucide/vue'
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import {
  getDocumentJobCapabilities,
  getDocumentJobMetrics,
  listDocumentJobs,
  type DocumentJob,
  type DocumentJobOperationalMetrics,
} from '../api/documentJobs'

const props = defineProps<{ open: boolean; factoryId: string }>()
const emit = defineEmits<{ close: [] }>()

const drawerRef = ref<HTMLElement | null>(null)
const closeButtonRef = ref<InstanceType<typeof Button> | null>(null)
let previousFocus: HTMLElement | null = null
const jobs = ref<DocumentJob[]>([])
const loading = ref(false)
const loadError = ref('')
const metrics = ref<DocumentJobOperationalMetrics | null>(null)

const stateLabels: Record<DocumentJob['state'], string> = {
  CREATED: '已创建',
  PREFLIGHTING: '预检中',
  READY: '等待处理',
  RUNNING: '处理中',
  REVIEW_REQUIRED: '需要复核',
  VERIFYING: '验证中',
  COMPLETED: '已完成',
  FAILED: '失败',
  CANCELLED: '已取消',
  EXPIRED: '已过期',
}

async function loadJobs() {
  loading.value = true
  loadError.value = ''
  try {
    const capabilities = await getDocumentJobCapabilities(props.factoryId)
    if (capabilities.available) {
      [jobs.value, metrics.value] = await Promise.all([
        listDocumentJobs(props.factoryId),
        getDocumentJobMetrics(props.factoryId),
      ])
    }
    else {
      jobs.value = []
      metrics.value = null
    }
  }
  catch (error) {
    jobs.value = []
    metrics.value = null
    loadError.value = error instanceof Error ? error.message : '任务记录暂时不可用。'
  }
  finally {
    loading.value = false
  }
}

function restoreFocus() {
  previousFocus?.focus()
  previousFocus = null
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
    return
  }
  if (event.key !== 'Tab' || !drawerRef.value) return

  const focusable = Array.from(drawerRef.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
  ))
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  }
  else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(() => props.open, async (open) => {
  if (open) {
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    closeButtonRef.value?.$el?.focus()
    void loadJobs()
  }
  else {
    restoreFocus()
  }
})

onBeforeUnmount(restoreFocus)
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50" role="presentation">
      <button
        type="button"
        class="absolute inset-0 bg-slate-950/30 backdrop-blur-[1px]"
        aria-label="关闭任务记录"
        @click="emit('close')"
      />
      <aside
        ref="drawerRef"
        class="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="document-job-drawer-title"
        @keydown="handleKeydown"
      >
        <header class="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <p class="text-xs font-bold uppercase tracking-[0.14em] text-teal-700">Document Jobs</p>
            <h2 id="document-job-drawer-title" class="mt-1 text-lg font-semibold text-slate-950">任务记录</h2>
          </div>
          <Button ref="closeButtonRef" variant="ghost" size="icon" aria-label="关闭任务记录" @click="emit('close')">
            <X class="size-4" aria-hidden="true" />
          </Button>
        </header>

        <div v-if="loading" class="flex flex-1 items-center justify-center gap-2 p-8 text-sm text-slate-500" aria-live="polite">
          <LoaderCircle class="size-4 animate-spin" aria-hidden="true" />
          正在读取任务记录
        </div>

        <div v-else-if="!jobs.length" class="flex flex-1 items-center justify-center p-8 text-center">
          <div class="max-w-xs">
            <span class="mx-auto flex size-12 items-center justify-center rounded-xl bg-slate-100 text-slate-500">
              <History class="size-5" aria-hidden="true" />
            </span>
            <h3 class="mt-4 text-sm font-semibold text-slate-900">尚无持久化文档任务</h3>
            <p class="mt-2 text-xs leading-5 text-slate-500">
              {{ loadError || '当前同步转换不会虚构任务历史；Document Job 开放后，这里只显示真实 AI Task / Artifact 记录。' }}
            </p>
          </div>
        </div>

        <div v-else class="flex-1 space-y-3 overflow-y-auto p-4">
          <section v-if="metrics" class="grid grid-cols-2 gap-2 rounded-xl border border-teal-100 bg-teal-50/60 p-3 text-xs sm:grid-cols-3" aria-label="文档任务质量概览">
            <div><p class="text-slate-500">成功率</p><p class="mt-1 font-semibold text-slate-900">{{ Math.round(metrics.success_rate * 100) }}%</p></div>
            <div><p class="text-slate-500">平均质量</p><p class="mt-1 font-semibold text-slate-900">{{ metrics.average_quality_confidence === null ? '—' : `${Math.round(metrics.average_quality_confidence * 100)}%` }}</p></div>
            <div><p class="text-slate-500">P95 耗时</p><p class="mt-1 font-semibold text-slate-900">{{ Math.round(metrics.p95_duration_ms / 1000) }} 秒</p></div>
            <div><p class="text-slate-500">任务数</p><p class="mt-1 font-semibold text-slate-900">{{ metrics.total_jobs }}</p></div>
            <div><p class="text-slate-500">复核中</p><p class="mt-1 font-semibold text-slate-900">{{ metrics.review_jobs }}</p></div>
            <div><p class="text-slate-500">云处理页</p><p class="mt-1 font-semibold text-slate-900">{{ metrics.cloud_page_count }}</p></div>
          </section>
          <article v-for="job in jobs" :key="job.id" class="rounded-xl border border-slate-200 p-4">
            <div class="flex items-start gap-3">
              <span class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
                <History class="size-4" aria-hidden="true" />
              </span>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-semibold text-slate-900">{{ job.source_filename }}</p>
                <p class="mt-1 text-xs text-slate-500">{{ job.job_type }} · {{ new Date(job.created_at).toLocaleString() }}</p>
              </div>
              <span class="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700">
                {{ stateLabels[job.state] }}
              </span>
            </div>
            <a
              v-if="job.state === 'COMPLETED' && job.result_artifact_id"
              :href="`/api/ai/artifacts/${encodeURIComponent(job.result_artifact_id)}/download`"
              class="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-teal-700 hover:text-teal-900"
            >
              <Download class="size-3.5" aria-hidden="true" />
              下载结果（重新鉴权）
            </a>
          </article>
        </div>

        <footer class="flex items-start gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4 text-xs leading-5 text-slate-500">
          <Clock3 class="mt-0.5 size-3.5 shrink-0 text-teal-700" aria-hidden="true" />
          任务保留、取消与过期策略将沿用现有 AI Task / Artifact 合同。
        </footer>
      </aside>
    </div>
  </Teleport>
</template>
