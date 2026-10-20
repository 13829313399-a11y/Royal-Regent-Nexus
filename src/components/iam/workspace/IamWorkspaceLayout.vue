<script setup lang="ts">
import { computed, provide, watch } from 'vue'
import { setIdentityViewer } from './identity-ui-context'
import { RouterView, useRoute } from 'vue-router'
import { ArrowLeft, ShieldCheck } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import IamWorkspaceNavigation from './IamWorkspaceNavigation.vue'
import { iamPageGroup, identityUiEnabled, positionWorkbenchEnabled, consolidatedIamEnabled } from './iam-navigation'
import '@/features/identity-management/workspace/workspace.css'
import './iam-studio.css'
import './iam-motion.css'
import '@/features/identity-management/workspace/permission-studio.css'
const auth = useAuthStore()
const activeRoute = useRoute()
const positionWorkspace = computed(() => activeRoute.name === 'position-workbench-compatible' || activeRoute.name === 'system-users' && identityUiEnabled && positionWorkbenchEnabled)
provide('iam-workspace', true)
watch(
  () => auth.currentUser?.id,
  (id) => setIdentityViewer(id || ''),
  { immediate: true, flush: 'sync' },
)
</script>
<template>
  <div class="rrn-iam-studio iamx-workspace notranslate" :class="{ 'iw-shell': consolidatedIamEnabled, 'iw-studio-shell': consolidatedIamEnabled }" translate="no">
    <a class="iamx-skip" href="#iamx-main">跳到主要内容</a>
    <header class="iamx-workspace-header">
      <div class="iamx-brand-row">
        <div class="iamx-brand">
          <span v-if="consolidatedIamEnabled" class="iw-brand-title"><ShieldCheck :size="26" aria-hidden="true" />权限与组织</span>
          <RouterLink to="/" class="iamx-back"><ArrowLeft :size="17" />返回工作台</RouterLink
          ><span class="iamx-brand-rule" />
          <span v-if="positionWorkspace && !consolidatedIamEnabled" class="flex items-center gap-2 font-semibold"><ShieldCheck :size="22" />组织协作 · 权限管理</span>
          <h1 v-else-if="!consolidatedIamEnabled"><ShieldCheck :size="25" />权限与组织</h1>
        </div>
        <div class="iamx-session">
          <AccountMenu :variant="consolidatedIamEnabled ? 'obsidian' : 'light'" />
        </div>
      </div>
      <IamWorkspaceNavigation v-if="consolidatedIamEnabled || !positionWorkspace" />
    </header>
    <main id="iamx-main" class="iamx-main" tabindex="-1" data-iam-focus-fallback>
      <RouterView v-slot="{ Component, route }"
        ><Transition name="iamx-page" mode="out-in"
          ><component :is="Component" :key="iamPageGroup(route.path)" /></Transition
      ></RouterView>
    </main>
  </div>
</template>

<style scoped>
.iamx-session { display: flex; }
</style>
