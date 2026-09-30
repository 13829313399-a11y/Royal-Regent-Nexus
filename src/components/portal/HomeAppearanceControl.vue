<script setup lang="ts">
import { SlidersHorizontal } from '@lucide/vue'
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from 'reka-ui'
import { useHomeAppearance } from '@/composables/useHomeAppearance'
const { motion, density, reduced, effectiveMotion } = useHomeAppearance()
</script>
<template>
  <PopoverRoot>
    <PopoverTrigger class="home-appearance-trigger" aria-label="首页外观设置"><SlidersHorizontal :size="16" aria-hidden="true" />外观</PopoverTrigger>
    <PopoverPortal><div class="rrn-home rrn-home--overlay" data-home-experience="prism-v4" :data-home-density="density" :data-home-motion="effectiveMotion">
    <PopoverContent class="home-appearance-panel" align="end" :side-offset="8" aria-label="首页外观设置">
      <h2>首页外观</h2>
      <fieldset><legend>显示密度</legend><div class="home-segmented">
        <button type="button" :aria-pressed="density === 'comfortable'" @click="density = 'comfortable'">舒适</button>
        <button type="button" :aria-pressed="density === 'compact'" @click="density = 'compact'">紧凑</button>
      </div></fieldset>
      <fieldset><legend>动效</legend><div class="home-segmented">
        <button type="button" :aria-pressed="motion === 'expressive'" @click="motion = 'expressive'">丰富</button>
        <button type="button" :aria-pressed="motion === 'calm'" @click="motion = 'calm'">简约</button>
        <button type="button" :aria-pressed="motion === 'off'" @click="motion = 'off'">关闭</button>
      </div></fieldset>
      <p v-if="reduced">系统已启用减少动态，当前动效关闭。</p>
      <p v-else>仅用于导航首页，按当前账号记住偏好。</p>
    </PopoverContent>
    </div></PopoverPortal>
  </PopoverRoot>
</template>
