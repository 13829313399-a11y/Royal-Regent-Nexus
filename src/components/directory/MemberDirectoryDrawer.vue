<script setup lang="ts">
import ConnectDirectoryDrawer from '@/features/collaboration/ConnectDirectoryDrawer.vue'
withDefaults(defineProps<{ open: boolean; currentFactoryId?: string; currentDepartment?: string }>(), { currentFactoryId: '', currentDepartment: '' })
const emit = defineEmits<{ close: [] }>()
</script>
<template><ConnectDirectoryDrawer :open="open" :current-factory-id="currentFactoryId" :current-department="currentDepartment" @close="emit('close')" /></template>
