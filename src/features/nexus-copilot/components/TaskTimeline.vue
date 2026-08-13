<script setup lang="ts">
import { computed } from 'vue'
import { CheckCircle2, CircleDot, Clock3, XCircle } from '@lucide/vue'
import type { AITaskDetail, AITaskEvent } from '@/api/aiTasks'
import ArtifactCard from './ArtifactCard.vue'
import VisionComparisonCard from './VisionComparisonCard.vue'
import PreviewCard from './PreviewCard.vue'
import { parsePreviewManifest } from '../renderers/preview'
import { parseVisionTaskResult } from '../renderers/visionComparison'

const props = defineProps<{
  task: AITaskDetail
  events: AITaskEvent[]
  comparingVision?: boolean
}>()
const emit = defineEmits<{ compareVision: [] }>()

const artifactResult = computed(() => {
  for (const step of props.task.steps) {
    const source = step.result_metadata.source_artifact_id
    const result = step.result_metadata.result_artifact_id
    const fileName = step.result_metadata.result_file_name
    if (
      typeof source === 'string'
      && typeof result === 'string'
      && typeof fileName === 'string'
      && /^aiart-[0-9a-f]{32}$/.test(source)
      && /^aiart-[0-9a-f]{32}$/.test(result)
    ) {
      return { source, result, fileName }
    }
  }
  return null
})

const visionResult = computed(() => {
  for (const step of props.task.steps) {
    const raw = step.result_metadata.vision_comparison
      ?? step.result_metadata.vision_observation
    const parsed = parseVisionTaskResult(raw)
    if (parsed) return parsed
  }
  return null
})

const previewManifests = computed(() => props.task.steps.flatMap((step) => {
  const raw = step.result_metadata.preview_manifests
  if (!Array.isArray(raw)) return []
  return raw.map(parsePreviewManifest).filter((item) => item !== null)
}))

function eventLabel(event: AITaskEvent) {
  if (event.transition_from && event.transition_to) return `${event.transition_from} → ${event.transition_to}`
  return event.reason_code || event.event_type
}
</script>

<template>
  <section class="min-h-0 overflow-y-auto px-3 py-3" aria-labelledby="task-timeline-title" data-task-timeline>
    <div class="flex items-start gap-2">
      <div class="min-w-0 flex-1">
        <h2 id="task-timeline-title" class="truncate text-xs font-bold text-slate-900">{{ task.primary_skill_id }}</h2>
        <p class="mt-1 text-[10px] text-slate-500">{{ task.id }} · 当前 {{ task.state }}</p>
      </div>
      <span class="rounded-full px-2 py-1 text-[10px] font-semibold" :class="task.state === 'COMPLETED' ? 'bg-emerald-100 text-emerald-800' : task.state === 'FAILED' ? 'bg-rose-100 text-rose-800' : 'bg-sky-100 text-sky-800'">
        {{ task.worker_status }}
      </span>
    </div>

    <ol class="mt-3 space-y-2" aria-label="任务步骤">
      <li v-for="step in task.steps" :key="step.id" class="flex gap-2 rounded-xl bg-slate-50 p-2">
        <CheckCircle2 v-if="step.state === 'COMPLETED'" class="mt-0.5 size-3.5 shrink-0 text-emerald-600" aria-hidden="true" />
        <XCircle v-else-if="step.state === 'FAILED' || step.state === 'CANCELLED'" class="mt-0.5 size-3.5 shrink-0 text-rose-600" aria-hidden="true" />
        <Clock3 v-else-if="step.state === 'RUNNING' || step.state === 'RETRY_PENDING'" class="mt-0.5 size-3.5 shrink-0 text-sky-600" aria-hidden="true" />
        <CircleDot v-else class="mt-0.5 size-3.5 shrink-0 text-slate-400" aria-hidden="true" />
        <div class="min-w-0">
          <p class="truncate text-[11px] font-semibold text-slate-800">{{ step.ordinal }}. {{ step.label }}</p>
          <p class="mt-0.5 text-[10px] text-slate-500">{{ step.state }} · 尝试 {{ step.attempt_count }}/{{ step.max_attempts }}</p>
        </div>
      </li>
    </ol>

    <ArtifactCard
      v-if="artifactResult"
      class="mt-3"
      :source-artifact-id="artifactResult.source"
      :result-artifact-id="artifactResult.result"
      :file-name="artifactResult.fileName"
    />

    <VisionComparisonCard
      v-if="visionResult"
      :result="visionResult"
      :comparing="comparingVision"
      @compare="emit('compareVision')"
    />

    <PreviewCard
      v-for="manifest in previewManifests"
      :key="manifest.preview_id"
      :manifest="manifest"
    />

    <h3 class="mt-4 text-[11px] font-bold text-slate-700">持久事件</h3>
    <ol class="mt-2 space-y-2">
      <li v-for="event in events" :key="event.id" class="border-l-2 border-slate-200 pl-2 text-[10px] leading-4 text-slate-600">
        <p class="font-semibold text-slate-800">#{{ event.sequence }} {{ eventLabel(event) }}</p>
        <p>{{ event.event_type }} · {{ event.actor_type }}</p>
      </li>
    </ol>
  </section>
</template>
