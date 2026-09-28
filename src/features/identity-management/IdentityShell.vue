<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, UsersRound } from '@lucide/vue'
import './identity.css'
const route = useRoute()
const links = [{ to: '/system/users', title: '人员' }, { to: '/system/iam/requests', title: '变更办理' }, { to: '/system/iam/roles', title: '权限方案' }, { to: '/system/iam/audit', title: '记录' }]
const active = computed(() => Math.max(0, links.findIndex(l => l.to === route.path)))
</script>
<template>
  <main class="iam-workspace">
    <header class="iam-header"><RouterLink to="/" class="iam-back"><ArrowLeft :size="18" /> 返回工作台</RouterLink>
      <div class="iam-heading"><div><p class="iam-eyebrow">ROYAL REGENT NEXUS / ORGANIZATION</p><h1><UsersRound :size="27" /> 人员与权限中心</h1><p>正式任职、授权来源与工作交接，在一处办理。</p></div><slot name="actions" /></div>
      <nav class="iam-nav" aria-label="人员管理导航"><span class="iam-nav-indicator" :style="{ transform: `translateX(${active * 100}%)` }" /><RouterLink v-for="link in links" :key="link.to" :to="link.to" :aria-current="route.path === link.to ? 'page' : undefined">{{ link.title }}</RouterLink></nav>
    </header>
    <div class="iam-content"><slot /></div>
  </main>
</template>
