<script setup lang="ts">
import { inject, ref, type Ref } from 'vue'
import { LoaderCircle } from '@lucide/vue'
import { Button } from '@/components/ui/button'

/* 高触感按钮：共享 Button 的变体、尺寸与语义完全保留，只叠加三件事：
   1) 状态自适应 Spin Loader：忙碌时在图标位显示旋转指示，文案与宽度不变；
   2) 悬停扫光与金属微渐变由样式层按 data-variant 应用；
   3) 点击波纹由工作区根节点的委托监听统一处理。
   未使用本组件的历史按钮同样获得质感与波纹，因此本组件只是显式的推荐写法。 */
const props = withDefaults(defineProps<{
  variant?: 'default' | 'outline' | 'secondary' | 'soft' | 'ghost' | 'destructive' | 'link'
  size?: 'default' | 'xs' | 'sm' | 'lg' | 'icon' | 'icon-xs' | 'icon-sm' | 'icon-lg'
  busy?: boolean
  sheen?: boolean
  disabled?: boolean
}>(), { variant: 'default', size: 'default', busy: false, sheen: false, disabled: false })

/* 桌面工作区与浏览器标签页隐藏时关闭扫光等装饰动效，与样式层 .spray-quiet 同一口径。 */
const quiet = inject<Ref<boolean>>('sprayQuiet', ref(false))
void props
</script>

<template>
  <Button
    :variant="variant"
    :size="size"
    :class="[sheen ? 'spray-sheen' : '', { 'spray-btn-busy': busy, 'spray-icon-btn': String(size).startsWith('icon') }]"
    :aria-busy="busy || undefined"
    :disabled="busy || disabled || undefined"
    :data-spray-sheen="!quiet"
  >
    <LoaderCircle v-if="busy" :size="15" aria-hidden="true" />
    <slot />
  </Button>
</template>
