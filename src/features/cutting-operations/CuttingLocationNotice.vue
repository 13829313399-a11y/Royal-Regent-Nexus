<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Button } from '@/components/ui/button'
import { cuttingDestination, type CuttingLocation } from './location'
const props = defineProps<{ location?: CuttingLocation; selectedId?: string }>()
const root = ref<HTMLElement>(), found = ref(false)
let observer: MutationObserver | undefined, focused: HTMLElement | undefined
function locate() {
  if (!props.location || props.location.lineId !== props.selectedId) return
  const page = root.value?.closest('.cutting-page')
  if (!page || !props.location.kind || !props.location.id) return
  const attribute = `data-cutting-${props.location.kind}`
  const target = Array.from(page.querySelectorAll<HTMLElement>(`[${attribute}]`))
    .find(element => element.getAttribute(attribute) === props.location!.id)
  found.value = !!target
  if (!target || target === focused) return
  focused?.removeAttribute('data-cutting-focused')
  focused = target
  for (let element: HTMLElement | null = target; element; element = element.parentElement) {
    if (element instanceof HTMLDetailsElement) element.open = true
  }
  target.setAttribute('data-cutting-focused', 'true')
  target.setAttribute('tabindex', '-1')
  target.scrollIntoView?.({ block: 'center' })
  target.focus({ preventScroll: true })
}
function reset() { focused?.removeAttribute('data-cutting-focused'); focused = undefined; found.value = false; locate() }
watch(() => [props.location, props.selectedId], reset, { flush: 'post' })
onMounted(() => {
  const page = root.value?.closest('.cutting-page')
  if (page) { observer = new MutationObserver(locate); observer.observe(page, { childList: true, subtree: true }) }
  locate()
})
onBeforeUnmount(() => { observer?.disconnect(); focused?.removeAttribute('data-cutting-focused') })
</script>
<template>
  <div ref="root" style="display: contents">
    <p v-if="location && location.lineId === selectedId" class="cutting-notice" role="status">
      已打开关联订单<span v-if="location.month"> · 核对月份 {{ location.month }}</span>。
      <span v-if="location.id">{{ found ? '已定位关联记录' : '关联记录尚未显示，请核对加载状态及记录是否仍可查看' }}：{{ location.id }}。
        <Button v-if="found" size="sm" variant="outline" @click="reset">定位关联记录</Button>
      </span>
      <RouterLink v-if="location.month" :to="cuttingDestination(location.lineId, location.month, 'closing')">返回该月核对</RouterLink>
    </p>
  </div>
</template>
