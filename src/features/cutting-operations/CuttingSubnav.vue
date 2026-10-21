<script setup lang="ts">
defineProps<{modelValue:string;items:Array<{id:string;label:string}>;label?:string}>()
defineEmits<{ 'update:modelValue':[value:string] }>()
</script>
<template>
  <nav class="cutting-section-nav cutting-subnav" :aria-label="label??'页内工作视图'">
    <button v-for="item in items" :key="item.id" type="button" :aria-pressed="modelValue===item.id" @click="$emit('update:modelValue',item.id)">{{item.label}}</button>
  </nav>
</template>
