<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import CollaborativeSheetsWorkspace from '@/features/collaborative-sheets/CollaborativeSheetsWorkspace.vue'
const app = useAppStore()
const auth = useAuthStore()
</script>

<template>
  <main class="collaborative-workbench">
    <nav><RouterLink :to="{ path: '/tools', query: { factory: app.activeFactoryId } }">← 返回公共工具栏</RouterLink><span>{{ auth.currentUser?.display_name }}</span></nav>
    <CollaborativeSheetsWorkspace :key="`${auth.currentUser?.id}:${app.activeFactoryId}`" :factory-id="app.activeFactoryId" :account-id="auth.currentUser?.id" />
  </main>
</template>

<style scoped>
.collaborative-workbench { min-height: 100vh; padding: 16px 24px; background: #f3f8f8; }
nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; color: #0f766e; font-size: 13px; }
@media (max-width: 700px) { .collaborative-workbench { padding: 12px 8px; } }
</style>
