<script setup lang="ts">
import { computed } from 'vue'
import { ChevronLeft, ChevronRight, PanelRightClose, PanelRightOpen } from '@lucide/vue'

const props = withDefaults(defineProps<{
  railCollapsed: boolean
  inspectorOpen: boolean
  inspectorWidth: number
  controlsEnabled?: boolean
}>(), { controlsEnabled: true })

const emit = defineEmits<{
  toggleRail: []
  toggleInspector: []
  inspectorWidth: [width: number]
}>()

const gridStyle = computed(() => ({
  '--ai-rail-width': props.railCollapsed ? '3rem' : '18.75rem',
  '--ai-inspector-width': props.inspectorOpen ? `${props.inspectorWidth}px` : '3rem',
}))

function beginInspectorResize(event: PointerEvent) {
  if (!props.inspectorOpen || event.button !== 0) return
  const startX = event.clientX
  const startWidth = props.inspectorWidth
  const target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)
  const move = (moveEvent: PointerEvent) => {
    emit('inspectorWidth', Math.min(520, Math.max(300, startWidth + startX - moveEvent.clientX)))
  }
  const stop = () => {
    target.removeEventListener('pointermove', move)
    target.removeEventListener('pointerup', stop)
    target.removeEventListener('pointercancel', stop)
  }
  target.addEventListener('pointermove', move)
  target.addEventListener('pointerup', stop)
  target.addEventListener('pointercancel', stop)
}
</script>

<template>
  <div
    class="ai-workbench-shell grid min-h-0 flex-1 grid-cols-1"
    :style="gridStyle"
    data-workbench-shell
  >
    <aside class="relative hidden min-h-0 border-r border-slate-200 bg-white lg:flex" data-workbench-rail>
      <div v-if="!railCollapsed" class="min-w-0 flex-1"><slot name="rail" /></div>
      <button
        v-if="controlsEnabled"
        type="button"
        class="absolute -right-3 top-3 z-10 flex size-6 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 shadow-sm hover:text-slate-950 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600"
        :aria-label="railCollapsed ? '展开会话栏' : '折叠会话栏'"
        @click="emit('toggleRail')"
      >
        <ChevronRight v-if="railCollapsed" class="size-3.5" aria-hidden="true" />
        <ChevronLeft v-else class="size-3.5" aria-hidden="true" />
      </button>
    </aside>

    <slot />

    <aside class="relative hidden min-h-0 border-l border-slate-200 bg-white xl:flex" data-workbench-inspector>
      <div
        v-if="inspectorOpen && controlsEnabled"
        class="absolute -left-1 top-0 z-10 h-full w-2 cursor-col-resize touch-none"
        role="separator"
        aria-label="调整上下文检查器宽度"
        aria-orientation="vertical"
        :aria-valuenow="inspectorWidth"
        aria-valuemin="300"
        aria-valuemax="520"
        tabindex="0"
        @pointerdown="beginInspectorResize"
        @keydown.left.prevent="emit('inspectorWidth', Math.min(520, inspectorWidth + 16))"
        @keydown.right.prevent="emit('inspectorWidth', Math.max(300, inspectorWidth - 16))"
      />
      <div v-if="inspectorOpen" class="min-w-0 flex-1"><slot name="inspector" /></div>
      <button
        v-else-if="controlsEnabled"
        type="button"
        class="m-2 flex size-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-950 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600"
        aria-label="展开上下文检查器"
        @click="emit('toggleInspector')"
      >
        <PanelRightOpen class="size-4" aria-hidden="true" />
      </button>
      <button
        v-if="inspectorOpen && controlsEnabled"
        type="button"
        class="absolute right-2 top-2 z-20 flex size-7 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600"
        aria-label="收起上下文检查器"
        @click="emit('toggleInspector')"
      >
        <PanelRightClose class="size-4" aria-hidden="true" />
      </button>
    </aside>
  </div>
</template>

<style scoped>
@media (min-width: 1024px) {
  .ai-workbench-shell {
    grid-template-columns: var(--ai-rail-width) minmax(0, 1fr);
  }
}

@media (min-width: 1280px) {
  .ai-workbench-shell {
    grid-template-columns: var(--ai-rail-width) minmax(0, 1fr) var(--ai-inspector-width);
  }
}
</style>
