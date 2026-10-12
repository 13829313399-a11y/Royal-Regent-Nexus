<script setup lang="ts">
import { MessageCircle } from '@lucide/vue'
import { useMessagingStore } from '@/stores/messaging'
const messaging = useMessagingStore()
</script>
<template><button v-if="messaging.ready" type="button" class="connect-message-entry" :aria-label="`打开私信，${messaging.unread} 条未读`" title="私信" @click="messaging.openPanel"><MessageCircle :size="20" /><span v-if="messaging.unread">{{ messaging.unread > 99 ? '99+' : messaging.unread }}</span></button></template>
