<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import AppShell from '@/components/layout/AppShell.vue'
import WorkCenterHost from '@/features/work-center/WorkCenterHost.vue'
import DeploymentNotice from '@/components/layout/DeploymentNotice.vue'
import CuttingResourceRecoveryNotice from '@/features/cutting-operations/CuttingResourceRecoveryNotice.vue'
import AssistantHost from '@/features/assistant/AssistantHost.vue'
import CollaborationHost from '@/features/collaboration/CollaborationHost.vue'
import { useAuthStore } from '@/stores/auth'
const auth = useAuthStore()
const privateHostsReady = computed(() => auth.isAuthenticated && !auth.currentUser?.force_password_change && !auth.isConfirmingSession)
import '@/features/work-center/work-center.css'
const workCenterEnabled = import.meta.env.VITE_WORK_CENTER_ENABLED !== 'false'
const collaborationEnabled = import.meta.env.VITE_COLLABORATION_ENABLED !== 'false'
const authorizationChanged = ref(false)
const onChanged = () => { authorizationChanged.value = true }
onMounted(() => window.addEventListener('authorization-context-changed', onChanged))
onUnmounted(() => window.removeEventListener('authorization-context-changed', onChanged))
</script>

<template>
  <div v-if="auth.isConfirmingSession" class="session-confirmation" role="status">正在确认工作空间身份…</div>
  <AppShell v-else />
  <DeploymentNotice />
  <CuttingResourceRecoveryNotice v-if="privateHostsReady" />
  <AssistantHost v-if="privateHostsReady" />
  <CollaborationHost v-if="privateHostsReady && collaborationEnabled" />
  <WorkCenterHost v-if="privateHostsReady && workCenterEnabled" />
  <aside v-if="privateHostsReady && authorizationChanged" role="status" class="authorization-update-notice">
    <span>任职或授权已更新。提交前请核对当前厂区与可用操作。</span>
    <button type="button" @click="authorizationChanged = false">知道了</button>
  </aside>
</template>

<style scoped>
.session-confirmation { min-height:100svh; display:grid; place-content:center; background:#083831; color:#f7faf6; font-size:16px; }
.authorization-update-notice { position:fixed; left:50%; bottom:20px; transform:translateX(-50%); z-index:100; display:flex; gap:16px; align-items:center; width:max-content; max-width:calc(100vw - 24px); padding:14px 18px; border:1px solid #a9cfc5; border-radius:12px; background:#edf8f4; color:#155c4e; box-shadow:0 8px 28px #173c291a; font-size:14px; }
.authorization-update-notice button { flex-shrink:0; padding:6px 10px; border-radius:6px; background:white; }
</style>
