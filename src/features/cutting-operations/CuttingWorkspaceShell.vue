<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute, onBeforeRouteUpdate } from 'vue-router'
import { ArrowLeft, Scissors, CalendarRange, ClipboardCheck, Boxes, CalendarCheck2, Settings2, Calculator } from '@lucide/vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { CUTTING_BASE, CUTTING_FACTORY, CUTTING_WORKSPACES, isCuttingFactory } from './navigation'
import { guardCuttingFactory } from './routes'
import './workspace.css'

const route = useRoute()
const logoUrl = '/brand/huadeng_group_dynamic_logo_topbar.svg'
const validFactory = computed(() => isCuttingFactory(route.query.factory))
const icons = { CalendarRange, ClipboardCheck, Boxes, CalendarCheck2, Settings2, Calculator }
const productionRoute = { path: '/modules/production', query: { factory: CUTTING_FACTORY } }
// Parent beforeEnter does not run for query-only or sibling navigation.
onBeforeRouteUpdate(guardCuttingFactory)
</script>

<template>
  <div v-if="validFactory" class="cutting-shell">
    <a class="cutting-skip" href="#cutting-main">跳到工作区内容</a>
    <header class="cutting-header">
      <RouterLink :to="productionRoute" class="cutting-brand" aria-label="裁床部，返回华康 C 生产部">
        <img :src="logoUrl" alt="华登集团" />
        <span><strong>裁床部</strong><small>华康 C · 生产管理</small></span>
      </RouterLink>
      <span class="cutting-scope"><Scissors :size="16" aria-hidden="true" /> 本厂 / 外发裁剪</span>
      <RouterLink :to="productionRoute" class="cutting-back"><ArrowLeft :size="16" aria-hidden="true" />生产部</RouterLink>
      <AccountMenu compact />
    </header>
    <nav class="cutting-rail" aria-label="裁床工作区导航">
      <RouterLink v-for="workspace in CUTTING_WORKSPACES" :key="workspace.path"
        :to="{ path: `${CUTTING_BASE}/${workspace.path}`, query: { factory: CUTTING_FACTORY } }"
        :aria-label="workspace.title" :aria-current="route.path === `${CUTTING_BASE}/${workspace.path}` ? 'page' : undefined">
        <component :is="icons[workspace.icon]" :size="21" aria-hidden="true" />
        <span>{{ workspace.short }}</span>
      </RouterLink>
    </nav>
    <main id="cutting-main" class="cutting-main" tabindex="-1">
      <RouterView v-slot="{ Component }"><component :is="Component" :key="route.path" /></RouterView>
    </main>
  </div>
</template>
