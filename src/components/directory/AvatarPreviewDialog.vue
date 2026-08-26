<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import UserAvatar from '@/components/common/UserAvatar.vue'
import type { DirectoryMember } from '@/api/directory'
import { useDialogFocus } from '@/composables/useDialogFocus'
import { acquireBodyScrollLock, type BodyScrollLockRelease } from '@/lib/bodyScrollLock'
import { directoryDepartmentLabel, directoryFactoryLabel } from '@/lib/directoryLabels'

const props = defineProps<{
  member: DirectoryMember | null
}>()

const emit = defineEmits<{
  close: []
}>()

const dialogRoot = ref<HTMLElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
const isOpen = computed(() => Boolean(props.member))
let releaseScrollLock: BodyScrollLockRelease | null = null

useDialogFocus(
  () => isOpen.value,
  dialogRoot,
  {
    onEscape: () => emit('close'),
    openAnnouncement: () => props.member ? `已打开${props.member.display_name}的头像预览` : '',
    initialFocus: () => closeButton.value,
  },
)

watch(isOpen, (open) => {
  if (open) releaseScrollLock ??= acquireBodyScrollLock()
  else {
    releaseScrollLock?.()
    releaseScrollLock = null
  }
})

onBeforeUnmount(() => {
  releaseScrollLock?.()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="nav-backdrop">
      <div
        v-if="member"
        class="fixed inset-0 z-[90] grid place-items-center bg-slate-950/55 p-4 backdrop-blur-sm"
        role="presentation"
        @click.self="emit('close')"
      >
        <section
          ref="dialogRoot"
          role="dialog"
          aria-modal="true"
          aria-labelledby="directory-avatar-title"
          tabindex="-1"
          class="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl outline-none"
        >
          <header class="flex items-start justify-between gap-4">
            <div>
              <p class="text-[11px] font-bold tracking-[0.16em] text-teal-700">成员头像</p>
              <h2 id="directory-avatar-title" class="mt-1 text-lg font-semibold text-slate-950">
                {{ member.display_name }}
              </h2>
            </div>
            <button
              ref="closeButton"
              type="button"
              aria-label="关闭头像预览"
              class="rounded-lg p-2 text-slate-500 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
              @click="emit('close')"
            >
              <X class="size-5" aria-hidden="true" />
            </button>
          </header>
          <div class="mt-5 flex justify-center rounded-2xl bg-slate-50 p-6">
            <UserAvatar
              :src="member.avatar_url"
              :name="member.display_name"
              size="xl"
              loading="eager"
              class="!h-64 !w-64 max-h-[min(64vw,320px)] max-w-[min(64vw,320px)] !text-6xl ring-1 ring-slate-200"
            />
          </div>
          <p class="mt-4 text-center text-sm text-slate-600">
            {{ member.position }} · {{ directoryFactoryLabel(member.primary_factory_id) }} · {{ directoryDepartmentLabel(member.primary_department) }}
          </p>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
