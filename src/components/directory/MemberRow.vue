<script setup lang="ts">
import UserAvatar from '@/components/common/UserAvatar.vue'
import PresenceBadge from '@/components/directory/PresenceBadge.vue'
import type { DirectoryMember } from '@/api/directory'
import { directoryDepartmentLabel, directoryFactoryLabel } from '@/lib/directoryLabels'

const props = withDefaults(defineProps<{
  member: DirectoryMember
  index?: number
  variant?: 'default' | 'drawer'
}>(), {
  index: 0,
  variant: 'default',
})

const emit = defineEmits<{
  preview: [member: DirectoryMember]
}>()
</script>

<template>
  <article
    class="flex min-w-0 items-center gap-3 rounded-xl border border-slate-200/80 bg-white px-3 py-3 shadow-sm"
    :class="props.variant === 'drawer' ? 'directory-member-card' : ''"
    :data-presence="member.presence_state"
    data-directory-member
    :data-directory-variant="props.variant"
    :style="props.variant === 'drawer' ? { '--member-delay': `${Math.min(props.index, 10) * 42}ms` } : undefined"
  >
    <button
      type="button"
      class="directory-avatar-trigger shrink-0 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/35"
      :aria-label="`预览${member.display_name}的头像`"
      @click="emit('preview', member)"
    >
      <UserAvatar
        :src="member.avatar_url"
        :name="member.display_name"
        size="lg"
        loading="lazy"
      />
    </button>
    <div class="min-w-0 flex-1">
      <div class="flex min-w-0 items-center justify-between gap-2">
        <h3 class="portal-member-name truncate text-sm font-semibold text-slate-950">{{ member.display_name }}</h3>
        <PresenceBadge :state="member.presence_state" />
      </div>
      <p class="portal-member-position mt-1 truncate text-xs text-slate-600">{{ member.position }}</p>
      <p v-if="props.variant !== 'drawer'" class="portal-member-org mt-1 truncate text-[11px] text-slate-500">
        {{ directoryFactoryLabel(member.primary_factory_id) }} · {{ directoryDepartmentLabel(member.primary_department) }}
      </p>
    </div>
  </article>
</template>

<style scoped>
.directory-member-card {
  --directory-spring: cubic-bezier(0.16, 1, 0.3, 1);
  position: relative;
  isolation: isolate;
  overflow: hidden;
  border-color: rgb(203 213 225 / 76%);
  background: linear-gradient(118deg, rgb(255 255 255 / 96%), rgb(241 245 249 / 86%) 52%, rgb(255 255 255 / 96%));
  box-shadow: 0 8px 22px -19px rgb(15 23 42 / 74%), inset 0 1px 0 rgb(255 255 255 / 95%);
  animation: directory-member-enter 520ms var(--directory-spring) backwards;
  animation-delay: var(--member-delay, 0ms);
  transition: border-color 240ms ease, box-shadow 300ms ease, transform 360ms var(--directory-spring);
}

.directory-member-card::before {
  position: absolute;
  inset: 0;
  z-index: -1;
  background: linear-gradient(108deg, transparent 24%, rgb(255 255 255 / 72%) 46%, transparent 68%);
  content: '';
  pointer-events: none;
  transform: translateX(-135%);
  transition: transform 720ms var(--directory-spring);
}

.directory-member-card::after {
  position: absolute;
  inset: 12px auto 12px 0;
  width: 3px;
  border-radius: 0 999px 999px 0;
  background: rgb(148 163 184 / 70%);
  content: '';
}

.directory-member-card[data-presence='online']::after { background: rgb(20 184 166); }
.directory-member-card[data-presence='away']::after { background: rgb(245 158 11); }

.directory-member-card:hover {
  border-color: rgb(94 234 212 / 72%);
  box-shadow: 0 14px 28px -20px rgb(13 148 136 / 62%), inset 0 1px 0 rgb(255 255 255 / 100%);
  transform: translateY(-2px);
}

.directory-member-card:hover::before {
  transform: translateX(135%);
}

.directory-avatar-trigger {
  box-shadow: 0 8px 16px -12px rgb(13 148 136 / 75%);
  transition: transform 300ms var(--directory-spring), box-shadow 240ms ease;
}

.directory-avatar-trigger:hover {
  box-shadow: 0 10px 20px -12px rgb(13 148 136 / 90%);
  transform: scale(1.04);
}

.directory-avatar-trigger:active {
  transform: scale(0.98);
}

@keyframes directory-member-enter {
  from {
    opacity: 0;
    filter: blur(2px);
    transform: translateY(12px) scale(0.985);
  }

  to {
    opacity: 1;
    filter: blur(0);
    transform: translateY(0) scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .directory-member-card,
  .directory-member-card::before,
  .directory-avatar-trigger {
    animation-duration: 0.01ms !important;
    animation-delay: 0ms !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
