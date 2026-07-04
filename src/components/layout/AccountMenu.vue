<script setup lang="ts">
import { computed, ref } from 'vue'
import { LogOut } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

withDefaults(defineProps<{
  compact?: boolean
}>(), {
  compact: false,
})

const router = useRouter()
const authStore = useAuthStore()
const isLoggingOut = ref(false)

const displayName = computed(() =>
  authStore.currentUser?.display_name
  || authStore.currentUser?.username
  || '已登录账号',
)

const roleLabel = computed(() => authStore.roles[0] ?? '系统用户')
const userInitial = computed(() => displayName.value.trim().charAt(0) || '账')

async function handleLogout() {
  if (isLoggingOut.value) {
    return
  }

  isLoggingOut.value = true
  try {
    await authStore.logout()
  } catch {
    authStore.clearSession()
  } finally {
    await router.replace({ name: 'login', query: { logged_out: '1' } })
    isLoggingOut.value = false
  }
}
</script>

<template>
  <div class="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1 text-slate-700">
    <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-teal-100 text-[11px] font-bold text-teal-700">
      {{ userInitial }}
    </span>
    <span v-if="!compact" class="hidden min-w-0 leading-tight sm:block">
      <span class="block max-w-28 truncate text-[12px] font-semibold text-slate-800">{{ displayName }}</span>
      <span class="block max-w-28 truncate text-[10px] text-slate-400">{{ roleLabel }}</span>
    </span>
    <button
      type="button"
      class="inline-flex h-7 items-center justify-center gap-1 rounded-md border border-slate-200 px-2 text-[11px] font-semibold text-slate-500 transition hover:border-red-200 hover:bg-red-50 hover:text-red-600 disabled:cursor-wait disabled:opacity-60"
      :disabled="isLoggingOut"
      aria-label="退出登录"
      title="退出登录"
      @click="handleLogout"
    >
      <LogOut class="size-3.5" aria-hidden="true" />
      <span class="hidden 2xl:inline">{{ isLoggingOut ? '退出中' : '退出' }}</span>
    </button>
  </div>
</template>
