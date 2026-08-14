<script setup lang="ts">
import { AlertTriangle, CheckCircle2, LoaderCircle } from '@lucide/vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { Button } from '@/components/ui/button'
import {
  getDocumentJobSnapshot,
  reviewDocumentJob,
  type DocumentJob,
  type DocumentReviewAction,
  type DocumentReviewIssue,
  type DocumentSnapshot,
} from '../api/documentJobs'

const props = defineProps<{ job: DocumentJob }>()
const emit = defineEmits<{ completed: [job: DocumentJob]; error: [message: string] }>()

const snapshot = ref<DocumentSnapshot | null>(null)
const loading = ref(true)
const submitting = ref(false)
const actions = reactive<Record<string, { action: DocumentReviewAction; value: string }>>({})
const issues = computed(() => props.job.quality_report?.issues ?? [])

function initializeActions() {
  for (const issue of issues.value) {
    actions[issue.issue_id] ??= {
      action: issue.options.includes('ACCEPT') ? 'ACCEPT' : issue.options[0],
      value: issue.proposed_value || issue.original_value,
    }
  }
}

function targetText(issue: DocumentReviewIssue) {
  const page = snapshot.value?.pages.find(item => item.page_number === issue.page_number)
  const block = page?.blocks.find(item => item.block_id === issue.target_id)
  if (block) return block.normalized_text || block.raw_text
  for (const table of page?.tables ?? []) {
    const cell = table.cells.find(item => item.cell_id === issue.target_id)
    if (cell) return cell.normalized_value || cell.raw_text
  }
  return issue.original_value
}

async function loadSnapshot() {
  loading.value = true
  initializeActions()
  try {
    if (!props.job.task_id) throw new Error('复核任务缺少任务标识。')
    snapshot.value = await getDocumentJobSnapshot(props.job.task_id)
  }
  catch (error) {
    emit('error', error instanceof Error ? error.message : '读取复核证据失败。')
  }
  finally {
    loading.value = false
  }
}

async function submitReview() {
  submitting.value = true
  try {
    const job = await reviewDocumentJob({
      job: props.job,
      actions: issues.value.map(issue => ({
        issue,
        action: actions[issue.issue_id].action,
        replacementValue: actions[issue.issue_id].value,
      })),
    })
    emit('completed', job)
  }
  catch (error) {
    emit('error', error instanceof Error ? error.message : '提交复核结果失败。')
  }
  finally {
    submitting.value = false
  }
}

onMounted(loadSnapshot)
</script>

<template>
  <section class="flex h-full min-h-[470px] flex-col overflow-hidden rounded-xl border border-amber-200 bg-white shadow-sm" aria-labelledby="document-review-title">
    <header class="flex items-start gap-3 border-b border-amber-200 bg-amber-50 px-4 py-3">
      <AlertTriangle class="mt-0.5 size-4 shrink-0 text-amber-700" aria-hidden="true" />
      <div>
        <h2 id="document-review-title" class="text-sm font-semibold text-amber-950">人工复核</h2>
        <p class="mt-1 text-xs leading-5 text-amber-800">逐项确认低置信度内容。提交时会校验任务、计划和 Snapshot 哈希。</p>
      </div>
    </header>

    <div v-if="loading" class="flex flex-1 items-center justify-center gap-2 text-sm text-slate-500">
      <LoaderCircle class="size-4 animate-spin" aria-hidden="true" />
      正在读取证据
    </div>
    <div v-else class="flex-1 space-y-3 overflow-y-auto p-4">
      <article v-for="issue in issues" :key="issue.issue_id" class="rounded-xl border border-slate-200 p-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <p class="text-xs font-semibold text-slate-900">第 {{ issue.page_number }} 页 · {{ issue.kind }}</p>
          <span class="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800">
            置信度 {{ Math.round(issue.confidence * 100) }}%
          </span>
        </div>
        <p class="mt-2 text-xs leading-5 text-slate-600">{{ issue.message }}</p>
        <div class="mt-2 rounded-lg bg-slate-50 p-2 text-xs text-slate-700">
          {{ targetText(issue) || '（空值）' }}
        </div>
        <div class="mt-3 flex flex-wrap gap-2">
          <label v-for="option in issue.options" :key="option" class="inline-flex items-center gap-1.5 text-xs text-slate-700">
            <input v-model="actions[issue.issue_id].action" type="radio" :name="issue.issue_id" :value="option">
            {{ option === 'ACCEPT' ? '接受' : option === 'EDIT' ? '编辑' : '标记未知' }}
          </label>
        </div>
        <textarea
          v-if="actions[issue.issue_id].action === 'EDIT'"
          v-model="actions[issue.issue_id].value"
          class="mt-2 min-h-20 w-full rounded-lg border border-slate-300 p-2 text-xs outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
          :aria-label="`编辑第 ${issue.page_number} 页复核值`"
        />
      </article>
    </div>
    <footer class="border-t border-slate-200 p-4">
      <Button class="w-full" :disabled="loading || submitting || !issues.length" @click="submitReview">
        <LoaderCircle v-if="submitting" class="size-4 animate-spin" aria-hidden="true" />
        <CheckCircle2 v-else class="size-4" aria-hidden="true" />
        提交 {{ issues.length }} 项复核并继续
      </Button>
    </footer>
  </section>
</template>
