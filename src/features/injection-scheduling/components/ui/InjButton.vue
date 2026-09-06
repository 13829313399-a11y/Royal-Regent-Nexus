<script setup lang="ts">
import { LoaderCircle } from '@lucide/vue';
defineProps<{ pending?: boolean; primary?: boolean; disabled?: boolean }>();
</script>
<template>
  <button
    type="button"
    class="inj-button"
    :class="{ 'inj-primary': primary }"
    :disabled="disabled || pending"
    :aria-busy="pending || undefined"
  >
    <span class="inj-button-symbol" v-if="pending || $slots.icon"
      ><LoaderCircle v-if="pending" class="inj-spin" aria-hidden="true" /><slot
        v-else
        name="icon"
    /></span>
    <slot />
  </button>
</template>
