<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue'
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
const titleId = `directory-avatar-${useId()}`
let releaseScrollLock: BodyScrollLockRelease | null = null

useDialogFocus(
  () => isOpen.value,
  dialogRoot,
  {
    onEscape: () => emit('close'),
    openAnnouncement: () => props.member ? `已打开${props.member.display_name}的头像预览` : '',
    initialFocus: () => closeButton.value,
    inertBackground: true,
  },
)

watch(isOpen, (open) => {
  if (open) releaseScrollLock ??= acquireBodyScrollLock()
  else {
    releaseScrollLock?.()
    releaseScrollLock = null
  }
}, { immediate: true })

onBeforeUnmount(() => {
  releaseScrollLock?.()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="nav-backdrop">
      <div
        v-if="member"
        class="rr-connect directory-avatar-backdrop"
        data-connect-overlay
        role="presentation"
        @click.self="emit('close')"
      >
        <section
          ref="dialogRoot"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          tabindex="-1"
          class="directory-avatar-dialog"
        >
          <header class="flex items-start justify-between gap-4">
            <div>
              <p class="text-[11px] font-bold tracking-[0.16em] text-teal-700">成员头像</p>
              <h2 :id="titleId" class="mt-1 text-lg font-semibold text-slate-950">
                {{ member.display_name }}
              </h2>
            </div>
            <button
              ref="closeButton"
              type="button"
              aria-label="关闭头像预览"
              class="connect-icon-button directory-avatar-close"
              @click="emit('close')"
            >
              <X class="size-5" aria-hidden="true" />
            </button>
          </header>
          <div class="directory-avatar-stage">
            <UserAvatar
              :src="member.avatar_url"
              :name="member.display_name"
              size="xl"
              shape="rounded"
              loading="eager"
              class="directory-avatar-large"
            />
          </div>
          <p class="mt-4 text-center text-sm text-slate-600">
            {{ member.position }} · {{ member.org_name || directoryFactoryLabel(member.primary_factory_id) }} · {{ directoryDepartmentLabel(member.primary_department) }}
          </p>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.directory-avatar-backdrop { position:fixed; inset:0; z-index:90; display:grid; place-items:center; padding:20px; overflow-y:auto; background:#092c2c99; backdrop-filter:blur(7px); }
.directory-avatar-dialog { width:min(100%,416px); max-height:calc(100dvh - 40px); overflow-y:auto; border:1px solid #d7e5df; border-radius:24px; padding:24px; background:#fff; box-shadow:0 24px 80px #092c2c40; outline:none; }
.directory-avatar-dialog header { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.directory-avatar-dialog h2 { overflow-wrap:anywhere; }
.directory-avatar-close { flex:none; }
.directory-avatar-stage { display:flex; justify-content:center; margin:20px 0 16px; padding:12px; border:1px solid #e1ebe6; border-radius:20px; background:#f1f7f3; }
.directory-avatar-large {
  width: min(320px, calc(100vw - 116px), max(120px, calc(100dvh - 260px)));
  height: auto;
  aspect-ratio: 1;
  border-radius: 12px;
  font-size: 80px;
}
.directory-avatar-large :deep(img) { object-fit:contain; }
</style>
