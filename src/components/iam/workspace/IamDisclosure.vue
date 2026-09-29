<script setup lang="ts">
import { CollapsibleRoot, CollapsibleTrigger, CollapsibleContent } from 'reka-ui'
import { ChevronDown } from '@lucide/vue'
defineProps<{ title: string; defaultOpen?: boolean }>()
</script>
<template>
  <CollapsibleRoot class="iamx-disclosure" :default-open="defaultOpen"
    ><CollapsibleTrigger class="iamx-disclosure-trigger"
      >{{ title }}<ChevronDown :size="17" aria-hidden="true" /></CollapsibleTrigger
    ><CollapsibleContent class="iamx-disclosure-content"
      ><div><slot /></div></CollapsibleContent
  ></CollapsibleRoot>
</template>
