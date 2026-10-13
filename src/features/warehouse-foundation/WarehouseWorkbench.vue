<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, type Component } from 'vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'
import { ArrowLeft, BookOpen, Boxes, Building2 } from '@lucide/vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'

const props = defineProps<{
  title: string
  description: string
  factoryLabel: string
  home: RouteLocationRaw
  activePath: string
  sections: { title: string; path: string; to: RouteLocationRaw; icon: Component }[]
  workspaces: { title: string; active: boolean; to: RouteLocationRaw }[]
}>()
defineEmits<{ guide: [] }>()
const rail = ref<HTMLElement>()
function revealActiveSection() {
  const element = rail.value
  const active = element?.querySelector<HTMLElement>('a[aria-current="page"]')
  if (!element || !active || element.scrollWidth <= element.clientWidth) return
  const bounds = element.getBoundingClientRect()
  const selected = active.getBoundingClientRect()
  element.scrollLeft += selected.left - bounds.left - (element.clientWidth - selected.width) / 2
}
function enterSection() { window.scrollTo({ top: 0, left: 0, behavior: 'instant' }); revealActiveSection() }
watch(() => props.activePath, enterSection, { flush: 'post' })
onMounted(() => { enterSection(); window.addEventListener('resize', revealActiveSection) })
onBeforeUnmount(() => window.removeEventListener('resize', revealActiveSection))
</script>

<template>
  <div class="warehouse-shell">
    <a class="warehouse-skip" href="#warehouse-main">跳到工作区内容</a>
    <header class="warehouse-header">
      <div class="warehouse-header-inner">
        <RouterLink :to="home" class="warehouse-back" aria-label="仓管首页"><ArrowLeft :size="16" /><span>PMC / 仓管模块</span></RouterLink>
        <div class="warehouse-brand"><span class="warehouse-brand-icon"><Boxes :size="21" /></span><div><strong>{{ title }}</strong><small>{{ description }}</small></div></div>
        <slot name="search" />
        <div class="warehouse-header-tools">
          <span class="warehouse-factory"><Building2 :size="15" />{{ factoryLabel }}</span>
          <button class="warehouse-guide-trigger" type="button" aria-label="打开仓库使用说明" title="使用说明" @click="$emit('guide')"><BookOpen :size="16" /><span>使用说明</span></button>
          <AccountMenu compact />
        </div>
      </div>
      <div class="warehouse-navigation">
        <nav ref="rail" class="warehouse-rail" :aria-label="`${title}栏目`">
          <RouterLink v-for="item in sections" :key="item.path" :to="item.to" :aria-current="activePath === item.path ? 'page' : undefined"><component :is="item.icon" :size="16" aria-hidden="true" /><span>{{ item.title }}</span></RouterLink>
        </nav>
        <nav class="warehouse-switch" aria-label="切换仓库"><RouterLink v-for="item in workspaces" :key="item.title" :to="item.to" :aria-current="item.active ? 'true' : undefined">{{ item.title }}</RouterLink></nav>
      </div>
    </header>
    <main id="warehouse-main" class="warehouse-main" tabindex="-1"><slot /></main>
    <slot name="overlay" />
  </div>
</template>
