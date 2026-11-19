<script setup lang="ts">
import { ClipboardList, CircleAlert } from '@lucide/vue';
defineProps<{ title: string; description?: string; failed?: boolean }>();
</script>
<template>
  <div class="inj-empty-state" :role="failed ? 'alert' : 'status'">
    <component
      :is="failed ? CircleAlert : ClipboardList"
      aria-hidden="true"
    /><strong>{{ title }}</strong>
    <p v-if="description">{{ description }}</p>
    <slot />
  </div>
</template>
