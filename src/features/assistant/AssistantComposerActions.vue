<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUp, Square, Plus, Globe } from '@lucide/vue'
import AssistantMenu from './AssistantMenu.vue'
import type { Capabilities } from './types'
import type { SearchMode, ThinkingMode } from './v2'
const props = defineProps<{ capabilities: Capabilities | null; search: SearchMode; thinking: ThinkingMode; busy: boolean; disabled: boolean; uploading: boolean; hasPage: boolean }>()
const emit = defineEmits<{ 'update:search': [SearchMode]; 'update:thinking': [ThinkingMode]; files: []; images: []; context: []; stop: []; open: [boolean]; focus: [] }>()
const labels = { auto: '自动思考', on: '深度思考', off: '直接回答' }
const items = computed(() => [
  { id: 'files', label: props.uploading ? '正在上传…' : '上传文件', disabled: props.uploading || !props.capabilities?.materials?.available },
  ...(props.capabilities?.profiles[0]?.vision ? [{ id: 'images', label: '上传图片', disabled: props.uploading }] : []),
  ...(props.hasPage ? [{ id: 'context', label: '带入当前页面与选中记录' }] : []),
  ...(props.capabilities?.profiles[0]?.thinking === 'toggle' ? (['auto','on','off'] as const).map(mode => ({ id: mode, label: `${props.thinking === mode ? '✓ ' : ''}${labels[mode]}` })) : []),
])
function select(id: string) {
  if (id === 'files') emit('files')
  else if (id === 'images') emit('images')
  else if (id === 'context') { emit('context'); emit('focus') }
  else { emit('update:thinking', id as ThinkingMode); emit('focus') }
}
</script>
<template>
  <div class="yl-composer-actions">
    <div>
      <AssistantMenu label="添加资料与更多选项" :items="items" @select="select" @open="emit('open',$event)"><Plus :size="20"/></AssistantMenu>
      <label class="yl-search-choice"><Globe :size="16"/><select :value="search" aria-label="联网模式" @change="emit('update:search',($event.target as HTMLSelectElement).value as SearchMode)"><option value="auto">自动</option><option value="on">联网</option><option value="off">关闭</option></select></label>
      <span v-if="capabilities?.profiles[0]?.thinking === 'toggle'" class="yl-thinking-label">{{ labels[thinking] }}</span>
    </div>
    <button v-if="busy" type="button" class="yl-send" aria-label="停止生成" @click="emit('stop')"><Square :size="17"/></button>
    <button v-else class="yl-send" type="submit" aria-label="发送问题" :disabled="disabled" aria-describedby="yl-send-reason"><ArrowUp :size="21"/></button>
  </div>
</template>
