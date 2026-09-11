<script setup lang="ts">
import { computed, ref } from 'vue'
import { useVirtualizer } from '@tanstack/vue-virtual'
import type { Entity } from '../workspace'
const props=withDefaults(defineProps<{items:Entity[];rowHeight?:number;height?:number;label:string}>(),{rowHeight:64,height:520})
const container=ref<HTMLElement|null>(null)
const virtualizer=useVirtualizer(computed(()=>({count:props.items.length,getScrollElement:()=>container.value,estimateSize:()=>props.rowHeight,overscan:6,getItemKey:(index:number)=>props.items[index]?.id??index})))
const visible=computed(()=>virtualizer.value.getVirtualItems())
function scrollTo(index:number){virtualizer.value.scrollToIndex(index,{align:'center'})}
defineExpose({scrollTo})
</script>
<template><div ref="container" class="spray-virtual" :aria-label="label" role="list" tabindex="0" :style="{height:Math.min(height,Math.max(128,items.length*rowHeight))+'px'}"><div :style="{height:virtualizer.getTotalSize()+'px',position:'relative'}"><div v-for="row in visible" :key="String(row.key)" role="listitem" :aria-posinset="row.index+1" :aria-setsize="items.length" class="spray-virtual-item" :style="{height:row.size+'px',transform:`translateY(${row.start}px)`}"><slot :item="items[row.index]!" :index="row.index" /></div></div></div></template>
<style scoped>.spray-virtual{overflow:auto;contain:strict;min-height:120px;border:1px solid var(--border);border-radius:10px;background:var(--card)}.spray-virtual-item{position:absolute;top:0;left:0;width:100%;border-bottom:1px solid var(--border);padding:8px 12px;display:flex;align-items:center;gap:12px}.spray-virtual:focus-visible{outline:2px solid var(--primary);outline-offset:2px}</style>
