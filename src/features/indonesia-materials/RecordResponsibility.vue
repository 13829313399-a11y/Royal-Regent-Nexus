<script setup lang="ts">
import { ref } from 'vue'
import { indonesiaMaterialsApi as api, type MaterialRecord, type ResponsiblePerson } from '@/api/indonesiaMaterials'
import { getApiErrorMessage } from '@/lib/http'
import { useMaterials } from './workspace'
const props = defineProps<{ record: MaterialRecord }>()
const ws = useMaterials()
const open = ref(false), loading = ref(false), search = ref(''), assignee = ref(''), reason = ref(''), error = ref(''), refine = ref(false)
const people = ref<ResponsiblePerson[]>([])
const openedVersion = ref(0)
let request = 0
async function load() {
  const epoch = ws.scopeEpoch, id = ++request
  loading.value = true; error.value = ''
  try {
    const result = await api.assignees(ws.factory, search.value)
    if (epoch !== ws.scopeEpoch || id !== request) return
    people.value = result.people; refine.value = result.refine_search
    if (!people.value.some(person => person.id === assignee.value)) assignee.value = ''
  } catch (cause) { if (epoch === ws.scopeEpoch && id === request) error.value = getApiErrorMessage(cause) }
  finally { if (epoch === ws.scopeEpoch && id === request) loading.value = false }
}
function start() { open.value = !open.value; if (open.value) { openedVersion.value = props.record.version; void load() } }
async function transfer() {
  if (!assignee.value || !reason.value.trim() || loading.value) return
  if (await ws.run('draft_transfer', { assignee_id: assignee.value, reason: reason.value.trim() }, { ...props.record, version: openedVersion.value })) {
    open.value = false; reason.value = ''; ws.notice = '已转交负责人；原上传人及转交记录保留。'
  }
}
</script>
<template>
  <div class="im-responsibility">
    <span :title="record.responsibility?.uploader?.username">上传人：{{ record.responsibility?.uploader?.name || '历史未记录' }}</span>
    <strong :title="record.responsibility?.assignee?.username">负责人：{{ record.responsibility?.assignee?.name || '待主管分配' }}</strong>
    <button v-if="record.responsibility?.can_transfer" type="button" :disabled="ws.locked" :aria-expanded="open" @click="start">转交</button>
    <div v-if="open" class="im-transfer im-stack">
      <p class="im-note">转交当前待办；已生成的出货草稿可在出货记录中另行转交。</p>
      <label class="im-field"><span>搜索姓名或账号</span><input v-model="search" maxlength="128" @keydown.enter.prevent="load"></label>
      <button type="button" :disabled="loading || ws.locked" @click="load">查找负责人</button>
      <p v-if="refine" class="im-note">结果较多，请输入姓名或账号缩小范围。</p>
      <label class="im-field"><span>接收人</span><select v-model="assignee" :disabled="loading || ws.locked"><option value="">请选择本厂有维护权限的人员</option><option v-for="person in people" :key="person.id" :value="person.id">{{ person.name }}（{{ person.username }}）</option></select></label>
      <label class="im-field"><span>转交原因</span><input v-model="reason" maxlength="500" :disabled="ws.locked"></label>
      <p v-if="error" class="im-danger-text" role="alert">{{ error }}</p>
      <div class="im-actions"><button type="button" class="im-primary" :disabled="!assignee || !reason.trim() || loading || ws.locked" @click="transfer">确认转交</button><button type="button" :disabled="ws.locked" @click="open = false">取消</button></div>
    </div>
    <details v-if="record.responsibility?.transfers.length" class="im-note"><summary>转交记录</summary><p v-for="(item, index) in record.responsibility.transfers" :key="index">{{ item.at }} · {{ item.by.name }}：{{ item.previous?.name || '未分配' }} → {{ item.assignee.name }} · {{ item.reason }}</p></details>
  </div>
</template>
