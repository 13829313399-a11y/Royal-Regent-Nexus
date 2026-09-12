<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useSprayMotionPreference } from '../composables/useSprayMotionPreference'
import { useSprayRipple } from '../composables/useSprayRipple'

/* 交互层：为工作区内所有按钮与导航项统一提供点击波纹反馈。
   通过根节点事件委托实现，不包裹、不替换任何业务控件，因此
   不影响既有事件、禁用状态、可访问名称或测试断言。 */
const anchor = ref<HTMLElement | null>(null)
const root = ref<HTMLElement | null>(null)
const { motionAllowed } = useSprayMotionPreference()
onMounted(() => { root.value = anchor.value?.parentElement ?? null })
useSprayRipple(root, motionAllowed)
</script>

<template>
  <!-- 零尺寸锚点：只承载委托监听，不参与布局与可访问性树。 -->
  <span ref="anchor" class="spray-interactions" aria-hidden="true" />
</template>

<style scoped>
.spray-interactions {
  display: none;
}
</style>
