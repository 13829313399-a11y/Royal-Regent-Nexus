<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import WorkCenterBell from '@/features/work-center/WorkCenterBell.vue'
const enabled = import.meta.env.VITE_WORK_CENTER_ENABLED !== 'false'
const LegacyNotificationCenter = defineAsyncComponent(() => import('./LegacyNotificationCenter.vue'))
</script>
<template><WorkCenterBell v-if="enabled" /><LegacyNotificationCenter v-else /></template>
