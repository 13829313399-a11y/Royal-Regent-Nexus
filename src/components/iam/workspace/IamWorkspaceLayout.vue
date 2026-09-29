<script setup lang="ts">
import { provide, watch } from 'vue'
import { setIdentityViewer } from './identity-ui-context'
import { RouterView } from 'vue-router'
import { ArrowLeft, ShieldCheck } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import IamWorkspaceNavigation from './IamWorkspaceNavigation.vue'
import { iamPageGroup } from './iam-navigation'
import './iam-studio.css'
import './iam-motion.css'
const auth = useAuthStore()
provide('iam-workspace', true)
watch(
  () => auth.currentUser?.id,
  (id) => setIdentityViewer(id || ''),
  { immediate: true, flush: 'sync' },
)
</script>
<template>
  <div class="rrn-iam-studio iamx-workspace notranslate" translate="no">
    <a class="iamx-skip" href="#iamx-main">跳到主要内容</a>
    <header class="iamx-workspace-header">
      <div class="iamx-brand-row">
        <div class="iamx-brand">
          <RouterLink to="/" class="iamx-back"><ArrowLeft :size="17" />返回工作台</RouterLink
          ><span class="iamx-brand-rule" />
          <h1><ShieldCheck :size="25" />权限与组织</h1>
        </div>
        <div class="iamx-session">
          <span class="iamx-avatar">{{
            (auth.currentUser?.display_name || auth.currentUser?.username || '我').slice(-2)
          }}</span
          ><span
            >{{ auth.currentUser?.display_name || auth.currentUser?.username || '已登录账号'
            }}<small>Royal Regent Nexus</small></span
          >
        </div>
      </div>
      <IamWorkspaceNavigation />
    </header>
    <main id="iamx-main" class="iamx-main" tabindex="-1" data-iam-focus-fallback>
      <RouterView v-slot="{ Component, route }"
        ><Transition name="iamx-page" mode="out-in"
          ><component :is="Component" :key="iamPageGroup(route.path)" /></Transition
      ></RouterView>
    </main>
  </div>
</template>
