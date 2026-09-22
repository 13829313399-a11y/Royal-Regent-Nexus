<script setup lang="ts">
import { ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { useSprayWorkspace } from '../workspace'
import WorkspaceDialog from './WorkspaceDialog.vue'
const w = useSprayWorkspace(), reason = ref('')
watch(w.actionQuestion, () => { reason.value = '' })
</script>
<template>
  <WorkspaceDialog :open="!!w.actionQuestion.value" :title="w.actionQuestion.value?.requiresReason?'记录处理依据':'保留当前填写'" @close="w.finishAction(null)">
    <p>{{ w.actionQuestion.value?.message }}</p>
    <form id="spray-action-question" class="spray-form" @submit.prevent="w.finishAction(w.actionQuestion.value?.requiresReason?reason.trim():'confirmed')">
      <label v-if="w.actionQuestion.value?.requiresReason" class="wide">处理依据<textarea v-model="reason" required /></label>
    </form>
    <template #footer><Button variant="outline" @click="w.finishAction(null)">{{ w.actionQuestion.value?.requiresReason?'取消':'继续填写' }}</Button><Button form="spray-action-question" type="submit" :disabled="w.actionQuestion.value?.requiresReason&&!reason.trim()">{{ w.actionQuestion.value?.requiresReason?'确认处理':'放弃填写' }}</Button></template>
  </WorkspaceDialog>
</template>
