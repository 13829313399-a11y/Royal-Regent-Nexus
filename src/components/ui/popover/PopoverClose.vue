<script setup lang="ts">
import type { PopoverCloseProps } from 'reka-ui'
import { PopoverClose } from 'reka-ui'

const props = defineProps<PopoverCloseProps>()
</script>

<template>
  <PopoverClose data-slot="popover-close" v-bind="props">
    <slot />
  </PopoverClose>
</template>
