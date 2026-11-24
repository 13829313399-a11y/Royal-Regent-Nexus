<script setup lang="ts">
import { computed } from 'vue'
import { Check } from '@lucide/vue'
import { workflow } from './metadata'
import type { WorkEntry } from './types'
const props = defineProps<{ entry: WorkEntry }>()
const track = computed(() => workflow(props.entry))
</script>
<template>
  <ol v-if="track" class="nc-steps" aria-label="业务阶段">
    <li
      v-for="(label, index) in track.labels"
      :key="label"
      :class="{
        done: index < track.current,
        current: index === track.current,
        warning: index === track.current && track.warning,
      }"
      :aria-current="index === track.current ? 'step' : undefined"
    >
      <span class="nc-node"><Check v-if="index < track.current" :size="10" /></span
      ><span>{{ index === track.current && track.warning ? track.warning : label }}</span>
    </li>
  </ol>
</template>
