<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import AppShell from '@/components/layout/AppShell.vue'
const authorizationChanged = ref(false)
const onChanged = () => { authorizationChanged.value = true }
onMounted(() => window.addEventListener('authorization-context-changed', onChanged))
onUnmounted(() => window.removeEventListener('authorization-context-changed', onChanged))
</script>

<template>
  <AppShell />
  <aside v-if="authorizationChanged" role="status" class="authorization-update-notice">
    <span>任职或授权已更新。提交前请核对当前厂区与可用操作。</span>
    <button type="button" @click="authorizationChanged = false">知道了</button>
  </aside>
</template>

<style scoped>
.authorization-update-notice { position:fixed; left:50%; bottom:20px; transform:translateX(-50%); z-index:100; display:flex; gap:16px; align-items:center; width:max-content; max-width:calc(100vw - 24px); padding:14px 18px; border:1px solid #a9cfc5; border-radius:12px; background:#edf8f4; color:#155c4e; box-shadow:0 8px 28px #173c291a; font-size:14px; }
.authorization-update-notice button { flex-shrink:0; padding:6px 10px; border-radius:6px; background:white; }
</style>
