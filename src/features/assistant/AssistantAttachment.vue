<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { assistantApi } from './api'
const props = defineProps<{ id: string }>()
const url = ref(''), error = ref(''), expanded = ref(false)
let alive = true
onMounted(async () => { try { const blob = await assistantApi.attachment(props.id); if(alive) url.value=URL.createObjectURL(blob) } catch { if(alive) error.value='图片已删除、过期或不可读取' } })
onUnmounted(() => { alive=false; if(url.value) URL.revokeObjectURL(url.value) })
</script>
<template><div class="yl-history-image"><button v-if="url" aria-label="放大已上传图片" @click="expanded=!expanded"><img :src="url" alt="已上传图片" :class="{expanded}"/></button><p v-else class="yl-muted">{{ error || '正在读取图片…' }}</p></div></template>
