<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import AuthExperienceShell from '@/components/auth/AuthExperienceShell.vue'
import SidebarNav from '@/components/layout/SidebarNav.vue'
import TopBar from '@/components/layout/TopBar.vue'
import { acquireBodyScrollLock, type BodyScrollLockRelease } from '@/lib/bodyScrollLock'
import { usePresenceHeartbeat } from '@/composables/usePresenceHeartbeat'
import { getPortalScope, getHomeExperienceScope, resolvePortalShellAttribute } from '@/lib/portalRouteScope'
import { createHomeAppearance, homeAppearanceKey, homeSearchKey } from '@/composables/useHomeAppearance'
import RouteMotionHost from '@/features/route-motion/RouteMotionHost.vue'
import { useRouteMotionHost } from '@/features/route-motion/useRouteMotionHost'
import '@/components/portal/styles/portal.css'
import '@/components/portal/styles/portal-shell.css'
import '@/components/portal/styles/home-prism.css'
import '@/components/portal/styles/home-prism-motion.css'
import '@/components/portal/styles/home-prism-shell.css'

const route = useRoute()
const homeScope = computed(() => getHomeExperienceScope(route))
const homeAppearance = createHomeAppearance()
provide(homeAppearanceKey, homeAppearance)
const { effectiveMotion, density } = homeAppearance
const standardSurface = ref<HTMLElement | null>(null)
const fullPageSurface = ref<HTMLElement | null>(null)
const { ghost } = useRouteMotionHost(homeAppearance, () => {
  const host = isFullPage.value ? fullPageSurface.value : standardSurface.value
  return host?.firstElementChild instanceof HTMLElement ? host.firstElementChild : null
})
const searchRequest = ref(0)
provide(homeSearchKey, searchRequest)
const topbarHeight = ref(72)
usePresenceHeartbeat()
const isMobileNavigationOpen = ref(false)
let releaseNavigationScrollLock: BodyScrollLockRelease | null = null
let desktopMediaQuery: MediaQueryList | null = null

const isFullPage = computed(() => Boolean(route.meta.fullPage))
const isAuthExperience = computed(() => ['login', 'register', 'reset-password', 'change-password'].includes(String(route.name)))

/**
 * 导航表面换肤只作用于白名单门户路由；其他模块路由即使已经加载过门户 CSS，
 * 也不会继续命中 `.app-shell[data-portal-shell]` 规则。
 */
const portalShellAttribute = computed(() => resolvePortalShellAttribute(getPortalScope(route)))

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
  <AuthExperienceShell v-if="isAuthExperience"><RouterView /></AuthExperienceShell>
  <div v-else-if="isFullPage" ref="fullPageSurface" class="rr-route-fullpage"><RouterView /></div>

  <div v-else class="app-shell" :data-portal-shell="portalShellAttribute" :data-home-experience="homeScope ? 'prism-v4' : undefined" :data-home-motion="homeScope ? effectiveMotion : undefined" :data-home-density="homeScope ? density : undefined" :style="homeScope ? { '--home-topbar-height': `${topbarHeight}px` } : undefined">
    <a
      href="#app-content"
      class="fixed left-4 top-3 z-[80] -translate-y-16 rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white shadow-xl transition-transform focus:translate-y-0"
    >
      跳到主要内容
    </a>
    <TopBar
      :navigation-open="isMobileNavigationOpen"
      :home-scope="homeScope"
      @home-search="homeScope === 'department' && searchRequest++"
      @height-change="topbarHeight = $event"
      @toggle-navigation="isMobileNavigationOpen = !isMobileNavigationOpen"
    />
    <div class="app-shell-content flex min-w-0">
      <SidebarNav
        :mobile-open="isMobileNavigationOpen"
        @close="isMobileNavigationOpen = false"
      />
      <main id="app-content" ref="standardSurface" class="app-main w-full max-w-full flex-1 px-4 py-6 sm:px-6 lg:py-7 xl:px-8 xl:py-8 2xl:px-10">
        <RouterView />
      </main>
    </div>
  </div>
  <RouteMotionHost :ghost="ghost" />
</template>
