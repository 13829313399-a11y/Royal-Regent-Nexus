<script setup lang="ts">
import { computed, ref, watch } from 'vue'

type AvatarSize = 'sm' | 'md' | 'lg' | 'xl'

const props = withDefaults(defineProps<{
  src?: string
  name?: string
  size?: AvatarSize
  alt?: string
}>(), {
  src: '',
  name: '当前账号',
  size: 'md',
  alt: '',
})

const hasLoadedImage = ref(Boolean(props.src))

watch(
  () => props.src,
  (src) => {
    hasLoadedImage.value = Boolean(src)
  },
)

const sizeClass = computed(() => ({
  sm: 'h-6 w-6 text-[11px]',
  md: 'h-8 w-8 text-[12px]',
  lg: 'h-11 w-11 text-[15px]',
  xl: 'h-24 w-24 text-[30px]',
})[props.size])

const fallbackInitial = computed(() => props.name.trim().charAt(0) || '账')
const imageAlt = computed(() => props.alt || `${props.name}的头像`)

function showFallback() {
  hasLoadedImage.value = false
}
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-teal-100 font-bold text-teal-700"
    :class="sizeClass"
  >
    <img
      v-if="hasLoadedImage && src"
      :src="src"
      :alt="imageAlt"
      class="h-full w-full object-cover"
      @error="showFallback"
    >
    <span v-else aria-hidden="true">{{ fallbackInitial }}</span>
  </span>
</template>
