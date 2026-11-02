<script setup lang="ts">
import { ref, useId } from 'vue'
withDefaults(defineProps<{ label?: string; moreLabel?: string; inlineActions?: boolean }>(), { label: '筛选条件', moreLabel: '更多筛选', inlineActions: false })
const moreOpen = ref(false)
const moreId = useId()
</script>

<template>
  <div class="carton-filter-bar" role="group" :aria-label="label">
    <div class="carton-filter-main" :class="{ 'carton-filter-inline': inlineActions }">
    <div class="carton-filter-fields"><slot /></div>
    <div v-if="$slots.actions || $slots.more" class="carton-filter-actions">
      <button v-if="$slots.more && inlineActions" type="button" :aria-expanded="moreOpen" :aria-controls="moreId" class="bg-white" @click="moreOpen = !moreOpen"><span aria-hidden="true">{{ moreOpen ? '▾' : '▸' }}</span> {{ moreLabel }}</button>
      <details v-else-if="$slots.more" class="carton-filter-more">
        <summary>{{ moreLabel }}</summary>
        <div class="carton-filter-fields carton-filter-extra"><slot name="more" /></div>
      </details>
      <slot name="actions" />
    </div>
    </div>
    <div v-if="inlineActions && $slots.more" v-show="moreOpen" :id="moreId" class="carton-filter-fields carton-filter-extra"><slot name="more" /></div>
    <slot name="footer" />
  </div>
</template>

<style>
.carton-filter-bar { min-width:0; padding:12px 16px; border-bottom:1px solid var(--color-teal-100); background:var(--color-teal-50); font-size:12px; }
.carton-filter-main { display:contents; }
.carton-filter-inline { display:flex; flex-wrap:wrap; align-items:flex-end; gap:10px 12px; }
.carton-filter-inline > .carton-filter-fields { flex:1 1 480px; }
.carton-filter-inline > .carton-filter-actions { flex:0 1 auto; margin-top:0; }
.dark .carton-filter-bar { background:color-mix(in oklch,var(--primary) 16%,var(--card)); border-bottom-color:var(--border); }
.carton-filter-fields { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(145px,100%),1fr)); align-items:end; gap:10px 12px; min-width:0; }
.carton-filter-fields > label,.carton-filter-fields > .carton-filter-field { display:flex; flex-direction:column; align-items:stretch; gap:6px; min-width:0; margin:0; color:var(--muted-foreground); font-size:11px; font-weight:600; }
.carton-filter-fields :is(select,input:not([type=checkbox]),button[aria-haspopup]) { width:100%; min-width:0; max-width:100%; height:36px; margin:0; border:1px solid var(--input); border-radius:8px; padding:0 10px; background:var(--card); color:var(--foreground); font-size:12px; font-weight:400; }
.carton-filter-fields input[type=checkbox] { width:16px; height:16px; margin:0; }
.carton-filter-fields .carton-filter-check { flex-direction:row; align-items:center; align-self:end; min-height:36px; }
.carton-filter-actions { display:flex; flex-wrap:wrap; align-items:center; justify-content:flex-end; gap:8px; margin-top:10px; }
.carton-filter-actions > button { min-height:36px; border:1px solid var(--input); border-radius:8px; padding:0 12px; font-size:12px; white-space:nowrap; }
.carton-filter-more { flex:0 1 auto; min-width:0; }
.carton-filter-more[open] { flex:1 1 100%; }
.carton-filter-more > summary { width:fit-content; cursor:pointer; padding:9px 12px; border:1px solid var(--input); border-radius:8px; background:var(--card); }
.carton-filter-extra { margin-top:10px; }
@media(max-width:639px) { .carton-filter-bar { padding:12px; } .carton-filter-fields { grid-template-columns:repeat(2,minmax(0,1fr)); } }
</style>
