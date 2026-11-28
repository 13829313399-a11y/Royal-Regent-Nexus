<script setup lang="ts">
import { RouterLink, type RouteLocationRaw } from 'vue-router'
defineProps<{ title:string; eyebrow?:string; value?:string|number; unit?:string; status?:string; progress?:number; to?:RouteLocationRaw; detailLabel?:string; unavailable?:boolean }>()
defineEmits<{ detail:[] }>()
</script>
<template>
  <article class="cutting-visual-card">
    <header><div><p v-if="eyebrow" class="cutting-muted">{{eyebrow}}</p><h3>{{title}}</h3></div><span v-if="status&&!$slots.headingAction" class="cutting-card-state">{{status}}</span><slot name="headingAction" /></header>
    <p v-if="value!==undefined" class="cutting-card-value">{{value}} <small>{{unit}}</small></p>
    <slot />
    <div v-if="progress!==undefined&&Number.isFinite(progress)" class="cutting-card-meter" role="meter" :aria-label="title+'进度'" :aria-valuenow="Math.round(Math.max(0,Math.min(100,progress)))" aria-valuemin="0" aria-valuemax="100"><span :style="{width:Math.max(0,Math.min(100,progress))+'%'}" /></div>
    <footer><slot name="action" /><RouterLink v-if="to&&!unavailable" :to="to" class="cutting-detail-link">{{detailLabel??'查看明细'}} <span aria-hidden="true">→</span></RouterLink><button v-else type="button" class="cutting-detail-link" :disabled="unavailable" @click="$emit('detail')">{{detailLabel??'查看明细'}} <span aria-hidden="true">→</span></button></footer>
  </article>
</template>
