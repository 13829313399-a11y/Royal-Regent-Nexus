<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { useMessagingStore } from '@/stores/messaging'
import ChatPanel from '@/features/collaboration/ChatPanel.vue'
const messaging = useMessagingStore(), route = useRoute()
watch([() => route.query.conversation, () => messaging.ready], ([id, ready]) => { if (ready && typeof id === 'string') void messaging.select(id) }, { immediate: true })
</script>
<template><main class="rr-connect connect-messages-page" :data-motion="messaging.preferences?.motion || 'rich'"><ChatPanel v-if="messaging.ready" full-page /><p v-else class="connect-empty">{{ messaging.error || '当前身份尚未开启私信。' }}</p></main></template>
