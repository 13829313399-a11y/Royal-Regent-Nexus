<script setup lang="ts">
import { computed, ref } from 'vue'
import { quotePaperMaterialGroups, standardQuotePaperName } from '@/lib/internalQuotePaperMaterials'
const value = defineModel<string>({ required: true })
defineProps<{ disabled?: boolean }>()
const editingCustom = ref(false)
const selection = computed(() => standardQuotePaperName(value.value) ?? (value.value || editingCustom.value ? '__custom__' : ''))
function select(event: Event) {
  const name = (event.target as HTMLSelectElement).value
  editingCustom.value = name === '__custom__'
  if (editingCustom.value) {
    if (standardQuotePaperName(value.value)) value.value = ''
  } else value.value = name
}
</script>
<template>
  <div class="paper-name">
    <select :value="selection" :disabled="disabled" aria-label="纸材名称" @change="select">
      <option value="">请选择纸材</option>
      <optgroup v-for="group in quotePaperMaterialGroups" :key="group.label" :label="group.label">
        <option v-for="name in group.names" :key="name" :value="name">{{ name }}</option>
      </optgroup>
      <option value="__custom__">其他／自定义材质</option>
    </select>
    <input v-if="selection === '__custom__'" v-model="value" :disabled="disabled" maxlength="128" placeholder="填写其他纸材名称" aria-label="自定义纸材名称">
  </div>
</template>
<style scoped>
.paper-name { display:grid; gap:6px; min-width:150px; } select,input { min-width:0; width:100%; padding:8px; border:1px solid var(--input); border-radius:6px; background:var(--background); color:var(--foreground); } :disabled { opacity:.5; }
</style>
