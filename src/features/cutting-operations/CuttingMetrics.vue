<script setup lang="ts">
defineProps<{items:Array<{label:string;value:string|number;unit?:string;hint?:string}>}>()
</script>
<template>
  <div class="cutting-metrics" aria-label="当前范围汇总">
    <article v-for="item in items" :key="item.label">
      <p>{{item.label}}</p><strong>{{item.value}} <small>{{item.unit}}</small></strong><span v-if="item.hint">{{item.hint}}</span>
    </article>
  </div>
</template>
