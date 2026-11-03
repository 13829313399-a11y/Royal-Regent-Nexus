<script setup lang="ts">
defineProps<{ problems: Array<{ section_code: string; section_name: string; reason: string }> }>()
defineEmits<{ locate: [code: string] }>()
</script>

<template>
  <div v-if="problems.length" class="quote-output-problems" role="status">
    <strong>内容已保存，以下项目处理完成后才能输出</strong>
    <ul><li v-for="(item, index) in problems" :key="`${item.section_code}:${index}`">
      <span><b>{{ item.section_name }}</b>：{{ item.reason }}</span>
      <button type="button" @click="$emit('locate', item.section_code)">前往处理</button>
    </li></ul>
  </div>
</template>

<style scoped>
.quote-output-problems{width:100%;border:1px solid #fcd34d;border-radius:10px;background:#fffbeb;padding:12px 14px;color:#92400e;font-size:13px}.quote-output-problems ul{margin:8px 0 0;padding:0;list-style:none;display:grid;gap:8px}.quote-output-problems li{display:flex;align-items:center;justify-content:space-between;gap:12px}.quote-output-problems span{white-space:pre-line;overflow-wrap:anywhere}.quote-output-problems button{flex-shrink:0;border:1px solid #d97706;border-radius:7px;padding:6px 10px;background:white;color:#92400e}@media(max-width:600px){.quote-output-problems li{align-items:flex-start;flex-direction:column}}
</style>
