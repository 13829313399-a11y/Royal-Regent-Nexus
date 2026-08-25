<script setup lang="ts">
import { LoaderCircle, RotateCcw, Users } from '@lucide/vue'
import MemberRow from '@/components/directory/MemberRow.vue'
import type { DirectoryMember } from '@/api/directory'

withDefaults(defineProps<{
  members: DirectoryMember[]
  loading?: boolean
  error?: string
  stale?: boolean
  grid?: boolean
  variant?: 'default' | 'drawer'
}>(), {
  variant: 'default',
})

const emit = defineEmits<{
  retry: []
  preview: [member: DirectoryMember]
}>()
</script>

<template>
  <Transition name="directory-content" mode="out-in">
    <div v-if="loading && !members.length" key="loading" class="space-y-3" aria-label="正在加载组织成员">
      <div v-if="variant === 'drawer'" class="flex items-center justify-center gap-2 py-1 text-xs font-semibold text-teal-700" role="status">
        <LoaderCircle class="directory-list-spin size-4" aria-hidden="true" />
        正在同步成员状态
      </div>
      <div v-for="index in 5" :key="index" class="flex items-center gap-3 rounded-xl border border-slate-100 bg-white p-3">
        <span class="skeleton-shimmer size-11 rounded-full" />
        <span class="min-w-0 flex-1 space-y-2">
          <span class="skeleton-shimmer block h-3.5 w-2/5 rounded" />
          <span class="skeleton-shimmer block h-3 w-4/5 rounded" />
        </span>
      </div>
    </div>

    <div
      v-else-if="error && !members.length"
      key="error"
      class="rounded-xl border border-rose-200 bg-rose-50 p-5 text-center"
      role="alert"
    >
      <p class="text-sm font-semibold text-rose-800">成员列表暂时无法加载</p>
      <p class="mt-1 text-xs leading-5 text-rose-700">{{ error }}</p>
      <button
        type="button"
        class="mt-4 inline-flex h-9 items-center gap-2 rounded-lg border border-rose-300 bg-white px-3 text-sm font-semibold text-rose-800 transition-transform hover:bg-rose-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400/30 active:scale-[0.98]"
        @click="emit('retry')"
      >
        <RotateCcw class="size-4" aria-hidden="true" />
        重试
      </button>
    </div>

    <div v-else-if="!members.length" key="empty" class="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
      <Users class="mx-auto size-8 text-slate-400" aria-hidden="true" />
      <p class="mt-3 text-sm font-semibold text-slate-700">没有匹配的成员</p>
      <p class="mt-1 text-xs text-slate-500">请调整搜索词或筛选条件后重试。</p>
    </div>

    <div v-else key="members" :class="grid ? 'grid gap-3 md:grid-cols-2 xl:grid-cols-3' : 'space-y-3'">
      <div
        v-if="stale"
        class="flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 md:col-span-2 xl:col-span-3"
        role="status"
      >
        <span>刷新失败，正在展示上次成功获取的数据。</span>
        <button type="button" class="font-semibold underline underline-offset-2" @click="emit('retry')">重试</button>
      </div>
      <MemberRow
        v-for="(member, index) in members"
        :key="member.id"
        :member="member"
        :index="index"
        :variant="variant"
        @preview="emit('preview', $event)"
      />
    </div>
  </Transition>
</template>

<style scoped>
.directory-content-enter-active,
.directory-content-leave-active {
  transition: opacity 180ms ease, transform 360ms cubic-bezier(0.16, 1, 0.3, 1), filter 180ms ease;
}

.directory-content-enter-from,
.directory-content-leave-to {
  opacity: 0;
  filter: blur(2px);
  transform: translateY(8px) scale(0.99);
}

.directory-list-spin {
  animation: directory-list-spin 760ms linear infinite;
}

@keyframes directory-list-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .directory-content-enter-active,
  .directory-content-leave-active {
    transition-duration: 0.01ms !important;
  }

  .directory-list-spin {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
</style>
