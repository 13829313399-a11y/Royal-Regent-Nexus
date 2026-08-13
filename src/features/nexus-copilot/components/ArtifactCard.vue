<script setup lang="ts">
import { Download, FileCheck2, GitBranch } from '@lucide/vue'

const props = defineProps<{
  sourceArtifactId: string
  resultArtifactId: string
  fileName: string
}>()

function downloadUrl() {
  const base = String(import.meta.env?.VITE_API_BASE_URL ?? '/api').replace(/\/+$/, '')
  return `${base}/ai/artifacts/${encodeURIComponent(props.resultArtifactId)}/download`
}
</script>

<template>
  <section class="rounded-xl border border-emerald-200 bg-emerald-50/70 p-3 text-xs text-emerald-950" aria-label="派生文件记录">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <strong class="flex items-center gap-2 text-sm">
          <FileCheck2 class="size-4" aria-hidden="true" />
          可恢复派生文件
        </strong>
        <p class="mt-1 truncate text-emerald-800">{{ fileName }}</p>
      </div>
      <a
        :href="downloadUrl()"
        class="inline-flex shrink-0 items-center gap-1 rounded-lg border border-emerald-300 bg-white px-2.5 py-1.5 font-semibold text-emerald-800"
      >
        <Download class="size-3.5" aria-hidden="true" />重新下载
      </a>
    </div>
    <div class="mt-2 flex items-center gap-2 text-emerald-700">
      <GitBranch class="size-3.5" aria-hidden="true" />
      <span class="truncate">源件 {{ sourceArtifactId }} → 派生件 {{ resultArtifactId }}</span>
    </div>
  </section>
</template>
