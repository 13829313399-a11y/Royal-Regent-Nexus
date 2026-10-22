<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useUvMotion } from '../composables/useUvMotionPreference'
import { consumeModuleEntryOwnership } from '@/features/route-motion/useModuleEntryMotion'
const routeEntryOwned = consumeModuleEntryOwnership()
const root=ref<HTMLElement|null>(null),revealing=ref(false),motion=useUvMotion()
let timer:ReturnType<typeof setTimeout>|undefined
function finish(){clearTimeout(timer);timer=undefined;revealing.value=false}
onMounted(()=>{
  if(routeEntryOwned||!motion.allowed.value||!root.value)return
  const style=getComputedStyle(root.value),milliseconds=(name:string)=>{const value=style.getPropertyValue(name).trim();return (parseFloat(value)||0)*(value.endsWith('ms')?1:1000)}
  revealing.value=true
  timer=setTimeout(finish,milliseconds('--uv-motion-reveal')+milliseconds('--uv-motion-reveal-max-delay'))
})
watch(motion.allowed,allowed=>{if(!allowed)finish()},{flush:'sync'})
onBeforeUnmount(finish)
</script>
<template><div ref="root" class="uv-page" :data-uv-reveal="revealing?'active':undefined"><slot/></div></template>
