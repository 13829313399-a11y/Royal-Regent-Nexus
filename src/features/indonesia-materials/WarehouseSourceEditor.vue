<script setup lang="ts">
import type { Data } from '@/api/indonesiaMaterials'
import Fields from './Fields.vue'
import { receiptSourceFields, receiptOtherFields } from './warehouseSourceFields'
defineProps<{ model: Data; index: number; issues: string[] }>()
defineEmits<{ save: []; cancel: [] }>()
</script>
<template>
  <div class="im-editor im-stack" :aria-label="`修改实收行 ${index + 1}`">
    <h3>修改第 {{ index + 1 }} 行资料</h3>
    <Fields :model="model" :fields="receiptSourceFields" />
    <details><summary>其他原单资料／装箱资料</summary><Fields :model="model" :fields="receiptOtherFields" /></details>
    <p v-if="issues.length" class="im-note">待核对：{{ issues.join('；') }}</p>
    <div class="im-actions"><button type="button" class="im-primary" @click="$emit('save')">保存并重新匹配</button><button type="button" @click="$emit('cancel')">取消修改</button></div>
    <small class="im-note">收料单号可留空。原文件保留；保存修改后仍需核对 PO 再确认实收。</small>
  </div>
</template>
