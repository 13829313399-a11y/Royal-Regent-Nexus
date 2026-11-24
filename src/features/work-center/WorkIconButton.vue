<script setup lang="ts">
import type { Component } from 'vue'
import { Button, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui'
defineProps<{ label: string; icon: Component; disabled?: boolean; pressed?: boolean }>()
defineEmits<{ activate: [] }>()
</script>
<template>
  <TooltipProvider
    ><Tooltip
      ><TooltipTrigger as-child>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          :aria-label="label"
          :aria-pressed="pressed"
          :disabled="disabled"
          @click.stop="$emit('activate')"
          ><component :is="icon" :size="16" aria-hidden="true"
        /></Button> </TooltipTrigger
      ><TooltipContent>{{ label }}</TooltipContent></Tooltip
    ></TooltipProvider
  >
</template>
