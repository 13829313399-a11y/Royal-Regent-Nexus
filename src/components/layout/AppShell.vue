<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import SidebarNav from '@/components/layout/SidebarNav.vue'
import TopBar from '@/components/layout/TopBar.vue'
import AiAssistantDrawer from '@/features/ai-assistant/AiAssistantDrawer.vue'
import { acquireBodyScrollLock, type BodyScrollLockRelease } from '@/lib/bodyScrollLock'
import { usePresenceHeartbeat } from '@/composables/usePresenceHeartbeat'

const route = useRoute()
usePresenceHeartbeat()
const isMobileNavigationOpen = ref(false)
let releaseNavigationScrollLock: BodyScrollLockRelease | null = null
let desktopMediaQuery: MediaQueryList | null = null

const isFullPage = computed(() => Boolean(route.meta.fullPage))

watch(() => route.path, () => {
  isMobileNavigationOpen.value = false
})

watch(isMobileNavigationOpen, (isOpen) => {
  if (isOpen) {
    releaseNavigationScrollLock ??= acquireBodyScrollLock()
    return
  }
  releaseNavigationScrollLock?.()
  releaseNavigationScrollLock = null
})

function closeNavigationOnEscape(event: KeyboardEvent) {
  if (event.key === 'Escape' && isMobileNavigationOpen.value) {
    isMobileNavigationOpen.value = false
  }
}

function closeNavigationAtDesktop(event: MediaQueryListEvent) {
  if (event.matches) {
    isMobileNavigationOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('keydown', closeNavigationOnEscape)
  desktopMediaQuery = window.matchMedia('(min-width: 1024px)')
  desktopMediaQuery.addEventListener('change', closeNavigationAtDesktop)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', closeNavigationOnEscape)
  desktopMediaQuery?.removeEventListener('change', closeNavigationAtDesktop)
  releaseNavigationScrollLock?.()
  releaseNavigationScrollLock = null
})
</script>

<template>
  <RouterView v-if="isFullPage" />

  <div v-else class="app-shell">
    <a
      href="#app-content"
      class="fixed left-4 top-3 z-[80] -translate-y-16 rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white shadow-xl transition-transform focus:translate-y-0"
    >
      跳到主要内容
    </a>
    <TopBar
      :navigation-open="isMobileNavigationOpen"
      @toggle-navigation="isMobileNavigationOpen = !isMobileNavigationOpen"
    />
    <div class="app-shell-content flex min-w-0">
      <SidebarNav
        :mobile-open="isMobileNavigationOpen"
        @close="isMobileNavigationOpen = false"
      />
      <main id="app-content" class="app-main w-full max-w-full flex-1 px-4 py-6 sm:px-6 lg:py-7 xl:px-8 xl:py-8 2xl:px-10">
        <RouterView v-slot="{ Component }">
          <Transition name="route-page" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </main>
    </div>
  </div>

  <!-- Teleported overlay: available on full-page business routes without changing their grid. -->
  <AiAssistantDrawer />
</template>
