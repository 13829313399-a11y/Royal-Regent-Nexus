<script setup lang="ts">
import { ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { useSprayWorkspace } from '../workspace'
import { utc, type Resource } from '../contracts'
import WorkspaceDialog from './WorkspaceDialog.vue'
const props = defineProps<{ resource: Resource | null }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const w = useSprayWorkspace()
const windows = ref<{ start: string; end: string; kind: string; reason: string }[]>([])
const busy = ref(false), error = ref('')
const local = (date: string) => new Date(new Date(date).getTime() + 8 * 3600000).toISOString().slice(0, 16)
watch(() => props.resource, resource => {
  windows.value = resource?.calendar.map(row => ({ start: local(row.start_at), end: local(row.end_at), kind: row.kind, reason: row.reason })) ?? []
  error.value = ''
})
async function close() {
  if (w.dirty.value && !(await w.confirmDiscard('放弃未保存的日历调整？'))) return
  w.dirty.value = false
  emit('close')
}
async function save() {
  if (!props.resource) return
  busy.value = true; error.value = ''
  try {
    await w.command(`resources/${props.resource.id}/calendar`, { calendar: windows.value.map(row => ({ start_at: utc(row.start), end_at: utc(row.end), kind: row.kind, reason: row.reason })) }, props.resource.version)
    await w.load(['resources'])
    emit('saved'); emit('close')
  } catch (cause) { error.value = w.explain(cause) } finally { busy.value = false }
}
</script>
<template>
  <WorkspaceDialog :open="!!resource" title="核对资源工作日历" wide @close="close">
    <p class="spray-muted">{{ resource?.name }} · 工作时段、停机和缺勤分别登记。影响已发布任务的调整会被拦截。</p>
    <form id="spray-calendar-form" class="spray-form" @input="w.dirty.value=true" @submit.prevent="save">
      <section v-for="(row, index) in windows" :key="index" class="wide spray-form">
        <label>时段开始<input v-model="row.start" type="datetime-local" required /></label>
        <label>时段结束<input v-model="row.end" type="datetime-local" required /></label>
        <label>时段性质<select v-model="row.kind"><option value="available">工作时段</option><option value="maintenance">停机维护</option><option value="absence">人员缺勤</option></select></label>
        <label>安排依据<input v-model="row.reason" required /></label>
        <button class="spray-text-button" type="button" @click="windows.splice(index,1);w.dirty.value=true">移除此时段</button>
      </section>
      <Button type="button" variant="outline" @click="windows.push({start:'',end:'',kind:'available',reason:''});w.dirty.value=true">增加时段</Button>
      <p v-if="error" class="spray-alert wide" role="alert">{{ error }}</p>
    </form>
    <template #footer><Button variant="outline" @click="close">取消</Button><Button type="submit" form="spray-calendar-form" :disabled="busy">确认日历</Button></template>
  </WorkspaceDialog>
</template>
