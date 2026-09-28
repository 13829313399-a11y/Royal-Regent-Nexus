<script setup lang="ts">
import { ArrowUpRight, ChevronRight, Eye, Pin } from '@lucide/vue'
import { computed } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import type { EnterpriseModule } from '@/data/enterpriseMock'
import StatusPill from '@/components/common/StatusPill.vue'
import HomeSearchText from '@/components/portal/HomeSearchText.vue'

const props = withDefaults(defineProps<{
  module: EnterpriseModule
  active?: boolean
  /** 门户首屏级联入场的次序，仅用于动画先后。 */
  index?: number
  previewable?: boolean
  pinned?: boolean
  searchQuery?: string
}>(), {
  active: false,
  index: 0,
  previewable: false,
  pinned: false,
  searchQuery: '',
})
const emit = defineEmits<{ preview: [event: MouseEvent]; peek: []; cancelPeek: []; focusPreview: [] }>()

const router = useRouter()
const isExternalLink = (href: string) => /^https?:\/\//i.test(href)

/** 卡片自身是否是一个导航目标。没有目标的展示卡不呈现手型、焦点或键盘激活。 */
const isNavigable = computed(() => Boolean(props.module.route))

function openModule(module: EnterpriseModule) {
  if (!module.route) {
    return
  }

  void router.push(module.route)
}

/**
 * 只有焦点落在卡片本身时才处理 Enter / Space。
 * 内部链接获得焦点后按键会冒泡到这里，若不区分就会多跳一次路由。
 */
function handleKeydown(event: KeyboardEvent, module: EnterpriseModule) {
  if (event.target !== event.currentTarget) {
    return
  }
  if (event.key !== 'Enter' && event.key !== ' ') {
    return
  }
  event.preventDefault()
  openModule(module)
}
</script>

<template>
  <article
    class="portal-module-card interactive-surface group relative overflow-hidden rounded-xl border p-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-500"
    :data-featured="active ? 'true' : 'false'"
    :data-pinned="pinned ? 'true' : undefined"
    :data-navigable="isNavigable ? 'true' : 'false'"
    :data-portal-tone="module.statusTone"
    :style="{ '--portal-card-index': index }"
    :class="[
      active
        ? 'border-teal-300 bg-gradient-to-br from-white via-white to-teal-50/35 shadow-[0_12px_32px_-22px_rgba(13,148,136,0.5)]'
        : 'border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]',
      module.route ? 'cursor-pointer hover:border-teal-300' : '',
    ]"
    :role="module.route ? 'link' : undefined"
    :tabindex="module.route ? 0 : undefined"
    :aria-label="module.route ? `打开${module.title}` : undefined"
    @click="openModule(module)"
    @keydown="handleKeydown($event, module)"
    @pointerenter="previewable && emit('peek')"
    @pointerleave="emit('cancelPeek')"
    @focusin="previewable && emit('focusPreview')"
  >
    <span
      v-if="active"
      class="absolute inset-y-5 left-0 w-0.5 rounded-r-full bg-teal-600"
      aria-hidden="true"
    />
    <div class="mb-5 flex items-start gap-4">
      <span
        class="portal-module-card__icon flex size-10 shrink-0 items-center justify-center rounded-xl ring-1 ring-inset ring-white/70 transition-transform duration-200 group-hover:scale-105"
      >
        <component :is="module.icon" class="size-5" aria-hidden="true" />
      </span>
      <div class="min-w-0">
        <h3 class="portal-module-card__title font-semibold text-slate-950"><HomeSearchText :text="module.title" :query="searchQuery" /></h3>
        <p class="portal-module-card__owner mt-1 text-xs text-slate-500">{{ module.owner }}</p>
      </div>
    </div>
    <p class="portal-module-card__summary text-sm leading-6 text-slate-700"><HomeSearchText :text="module.summary" :query="searchQuery" /></p>
    <div
      v-if="module.statusMetrics.length"
      class="portal-module-card__metrics mt-4 grid gap-3 sm:grid-cols-3"
    >
      <div
        v-for="metric in module.statusMetrics"
        :key="`${module.id}-${metric.label}`"
        class="portal-module-card__metric rounded-lg border border-slate-200/80 bg-slate-50/70 px-3 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]"
        :data-tone="metric.tone"
      >
        <p class="portal-module-card__metric-label text-[11px] uppercase tracking-wide text-slate-500">{{ metric.label }}</p>
        <p class="portal-module-card__metric-value mt-1 text-sm font-semibold">{{ metric.value }}</p>
      </div>
    </div>
    <div v-if="module.children.length" class="portal-module-card__children mt-4 flex flex-wrap gap-2">
      <span
        v-for="child in (previewable ? module.children : module.children.slice(0, 3))"
        :key="`${module.id}-${child.label}`"
        class="portal-module-card__child rounded-full bg-slate-100/90 px-3 py-1 text-xs font-medium text-slate-600 ring-1 ring-inset ring-slate-200/70"
      >
        <HomeSearchText :text="child.label" :query="searchQuery" />
      </span>
    </div>
    <div class="portal-module-card__footer mt-4 flex items-center justify-between gap-3">
      <StatusPill :label="module.status" :tone="module.statusTone" compact />
      <span class="portal-module-card__stats text-xs text-slate-500">{{ module.stats }}</span>
    </div>
    <div
      v-if="module.route || module.href"
      class="portal-module-card__actions mt-5 flex flex-wrap items-center gap-3"
    >
      <RouterLink
        v-if="module.route"
        :to="module.route"
        class="portal-action portal-action--primary inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
        @click.stop
      >
        查看模块
        <ChevronRight class="portal-action__arrow size-4" aria-hidden="true" />
      </RouterLink>
      <RouterLink
        v-if="module.href && !isExternalLink(module.href)"
        :to="module.href"
        class="portal-action portal-action--secondary inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-teal-200 hover:bg-teal-50/60 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/25"
        @click.stop
      >
        打开系统
        <ArrowUpRight class="portal-action__arrow size-4" aria-hidden="true" />
      </RouterLink>
      <a
        v-else-if="module.href"
        :href="module.href"
        target="_blank"
        rel="noreferrer"
        class="portal-action portal-action--secondary inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-teal-200 hover:bg-teal-50/60 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/25"
        @click.stop
      >
        打开系统
        <ArrowUpRight class="portal-action__arrow size-4" aria-hidden="true" />
      </a>
      <button v-if="previewable && (module.route || module.href)" type="button" class="home-preview-button" :aria-label="`预览${module.title}`" :aria-pressed="pinned" @click.stop="emit('preview', $event)">
        <component :is="pinned ? Pin : Eye" :size="16" aria-hidden="true" />{{ pinned ? '已固定' : '预览' }}
      </button>
    </div>
  </article>
</template>
