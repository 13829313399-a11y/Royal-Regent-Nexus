<script setup lang="ts">
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import OnlineDocumentsWorkspace from '@/features/online-documents/OnlineDocumentsWorkspace.vue'
const app = useAppStore()
const auth = useAuthStore()
</script>
<template>
  <OnlineDocumentsWorkspace :key="`${auth.currentUser?.id}:${auth.currentUser?.identity?.employment_epoch}:${app.activeFactoryId}`" :factory-id="app.activeFactoryId" />
</template>
