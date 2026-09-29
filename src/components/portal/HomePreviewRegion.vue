<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { Eye, X } from '@lucide/vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription, DialogClose } from 'reka-ui'
import type { EnterpriseModule } from '@/data/enterpriseMock'
import type { HomeIdentity } from './homePrismPresentation'
import { homePaletteStyle } from './homePrismPresentation'
import HomeModulePreview from './HomeModulePreview.vue'
import { useHomeAppearance } from '@/composables/useHomeAppearance'
const props = defineProps<{ module: EnterpriseModule | null; pinned: boolean; searching: boolean; narrow: boolean; identity: HomeIdentity; opener: HTMLElement | null }>()
const open = defineModel<boolean>('open', { default: false })
defineEmits<{ unpin: [] }>()
const { effectiveMotion, density } = useHomeAppearance()
const summaryOpener = ref<HTMLElement | null>(null)
watch(() => props.narrow, () => { open.value = false })
function openSummary(event: MouseEvent) {
  summaryOpener.value = event.currentTarget as HTMLElement
  open.value = true
}
function restoreFocus(event: Event) {
  event.preventDefault()
  const target = summaryOpener.value ?? props.opener
  summaryOpener.value = null
  void nextTick(() => {
    if (target?.isConnected && target.getClientRects().length) target.focus()
    else document.querySelector<HTMLInputElement>('#home-module-search')?.focus()
  })
}
</script>
<template>
  <HomeModulePreview v-if="!narrow" :module="module" :pinned="pinned" :searching="searching" @unpin="$emit('unpin')" />
  <div v-else class="home-preview-summary">
    <div><h2>模块聚焦</h2><p>{{ module?.title ?? (searching ? '没有匹配的入口' : '当前没有可显示的模块') }}</p></div>
    <button v-if="module" type="button" class="home-preview-button" @click="openSummary"><Eye :size="16" aria-hidden="true" />模块介绍</button>
  </div>
  <DialogRoot v-if="narrow" v-model:open="open">
    <DialogPortal>
      <div class="rrn-home rrn-home--overlay" data-home-experience="prism-v4" :data-home-motion="effectiveMotion" :data-home-density="density" :style="homePaletteStyle(identity)">
        <DialogOverlay class="home-dialog-overlay" />
        <DialogContent class="home-dialog" @close-auto-focus="restoreFocus">
          <header class="home-dialog-header"><div><DialogTitle>模块介绍</DialogTitle><DialogDescription>目录信息与当前厂区入口</DialogDescription></div><DialogClose class="home-dialog-close" aria-label="关闭模块预览"><X :size="20" /></DialogClose></header>
          <HomeModulePreview v-if="open" :module="module" :pinned="pinned" :searching="searching" @unpin="$emit('unpin')" />
        </DialogContent>
      </div>
    </DialogPortal>
  </DialogRoot>
</template>
