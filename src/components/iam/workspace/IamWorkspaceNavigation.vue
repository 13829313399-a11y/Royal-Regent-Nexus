<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { shouldShowPageNavigation } from '@/config/pageAccessPolicy'
import { useAuthStore } from '@/stores/auth'
import { iamNavigation, identityUiEnabled } from './iam-navigation'
const route = useRoute()
const auth = useAuthStore()
const nav = ref<HTMLElement>()
const marker = ref({ left: '0px', width: '0px', opacity: 0 })
const ready = ref(false)
const items = computed(() =>
  iamNavigation.filter(
    (i) =>
      (!i.v2 || identityUiEnabled) && shouldShowPageNavigation(i.permissions, (p) => auth.can(p)),
  ),
)
const activePath = computed(() => (route.path.endsWith('/access') ? '/system/users' : route.path))
let observer: ResizeObserver | undefined
async function measure(reveal = false) {
  await nextTick()
  const active = nav.value?.querySelector<HTMLElement>('[aria-current="page"]')
  if (!active || !nav.value) return
  marker.value = { left: `${active.offsetLeft}px`, width: `${active.offsetWidth}px`, opacity: 1 }
  if (reveal) {
    const right = active.offsetLeft + active.offsetWidth
    if (right > nav.value.scrollLeft + nav.value.clientWidth)
      nav.value.scrollLeft = right - nav.value.clientWidth
    if (active.offsetLeft < nav.value.scrollLeft) nav.value.scrollLeft = active.offsetLeft
  }
}
watch([activePath, items], () => void measure(true))
onMounted(async () => {
  await measure(true)
  requestAnimationFrame(() => {
    ready.value = true
  })
  if (typeof ResizeObserver !== 'undefined' && nav.value) {
    observer = new ResizeObserver(() => void measure())
    observer.observe(nav.value)
  }
  void document.fonts?.ready.then(() => measure())
})
onBeforeUnmount(() => observer?.disconnect())
</script>
<template>
  <nav ref="nav" class="iamx-navigation" aria-label="权限与组织导航" @scroll="measure()">
    <span
      class="iamx-navigation-marker"
      :class="{ 'is-ready': ready }"
      :style="marker"
      aria-hidden="true"
    />
    <RouterLink
      v-for="item in items"
      :key="item.to"
      :to="item.to"
      :class="{ 'iamx-account-link': item.to.endsWith('/registration') }"
      :aria-current="activePath === item.to ? 'page' : undefined"
    >
      <component :is="item.icon" :size="17" aria-hidden="true" />{{ item.label }}
    </RouterLink>
  </nav>
</template>
