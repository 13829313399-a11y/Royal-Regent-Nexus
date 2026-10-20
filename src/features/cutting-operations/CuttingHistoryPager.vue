<script setup lang="ts">
import { Button } from '@/components/ui/button'
import type { HistoryPagination } from './reportingApi'
defineProps<{ value: HistoryPagination; busy?: boolean }>()
defineEmits<{ page: [page: number] }>()
</script>
<template>
  <nav class="cutting-pagination" aria-label="历史明细分页">
    <span>历史明细第 {{ value.page }} 页 · 共 {{ value.total }} 条操作记录（汇总按全部有效记录计算）</span>
    <div class="cutting-master-actions">
      <Button variant="outline" :disabled="busy||value.page<=1" @click="$emit('page',value.page-1)">上一页历史</Button>
      <Button variant="outline" :disabled="busy||value.page*value.page_size>=value.total" @click="$emit('page',value.page+1)">下一页历史</Button>
    </div>
  </nav>
</template>
