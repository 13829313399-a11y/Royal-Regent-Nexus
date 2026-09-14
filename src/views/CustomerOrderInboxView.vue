<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import CustomerOrderInbox, {
  type CustomerOrderInboxRecipient,
} from '@/components/common/CustomerOrderInbox.vue'

const route = useRoute()

const defaultRecipient = computed<CustomerOrderInboxRecipient>(() => {
  if (route.path.includes('/production/')) return 'injection'
  if (route.path.includes('/pmc-warehouse/')) return 'pmc'
  return 'pmc'
})
</script>

<template>
  <CustomerOrderInbox :default-recipient="defaultRecipient" />
</template>
