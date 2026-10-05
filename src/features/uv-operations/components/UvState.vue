<script setup lang="ts">
import { AlertCircle, Inbox, LoaderCircle, ShieldCheck, WifiOff } from '@lucide/vue'
withDefaults(defineProps<{kind?:'empty'|'loading'|'error'|'denied'|'offline';title:string;description?:string}>(),{kind:'empty'})
</script>
<template>
  <div class="uv-state" :role="kind==='error'?'alert':undefined">
    <component :is="kind==='loading'?LoaderCircle:kind==='denied'?ShieldCheck:kind==='offline'?WifiOff:kind==='error'?AlertCircle:Inbox" :class="{'uv-spin':kind==='loading'}" :size="30" />
    <h3>{{title}}</h3><p v-if="description">{{description}}</p><div class="uv-state-actions"><slot /></div>
  </div>
</template>
