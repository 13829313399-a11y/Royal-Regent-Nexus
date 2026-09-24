<script setup lang="ts">
import { label, str, type Entity } from '../contracts'
import UvState from './UvState.vue'
defineProps<{rows:Entity[];columns:{key:string;label:string;state?:boolean}[];empty?:string;selectable?:boolean}>()
const emit=defineEmits<{select:[row:Entity]}>()
</script>
<template>
  <div v-if="rows.length" class="uv-table-scroll" tabindex="0" aria-label="数据表格，可横向滚动">
    <table class="uv-table"><thead><tr><th v-for="column in columns" :key="column.key" scope="col">{{column.label}}</th><th v-if="$slots.actions" scope="col">操作</th></tr></thead>
      <tbody><tr v-for="row in rows" :key="row.id"><td v-for="(column,index) in columns" :key="column.key">
        <button v-if="selectable&&index===0" class="uv-link" @click="emit('select',row)">{{str(row,column.key)}}</button>
        <span v-else-if="column.state" class="uv-badge" :data-state="row[column.key]">{{label(row[column.key])}}</span><template v-else>{{str(row,column.key)}}</template>
      </td><td v-if="$slots.actions"><div class="uv-row-actions"><slot name="actions" :row="row" /></div></td></tr></tbody>
    </table>
  </div>
  <UvState v-else :title="empty??'暂无记录'" description="完成业务操作后，记录将显示在这里。" />
</template>
