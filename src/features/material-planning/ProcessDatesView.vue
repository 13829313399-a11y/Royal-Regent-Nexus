<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useRoute, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { trialApi as api, statusText, quantityText, type Access, type DateDemand } from './api'

const route = useRoute(), auth = useAuthStore()
const access = ref<Access | null>(null), rows = ref<DateDemand[]>([]), selected = ref<DateDemand | null>(null)
const dates = ref<Record<string, string>>({}), reason = ref('核对各工序物料期'), error = ref(''), notice = ref('')
const busy = ref(false), loading = ref(false), dirty = ref(false), pending = ref<{ id: string; body: unknown } | null>(null)
let epoch = 0, replacing = false
const ready = computed(() => route.query.factory === 'huakang-c' && access.value?.enabled && access.value.schema_ready)
const locked = computed(() => loading.value || busy.value || !!pending.value)
const writable = computed(() => ready.value && access.value?.can_write && selected.value?.status !== 'SELF_REVIEWED_DATA_PENDING')
function reset() {
  access.value = null; rows.value = []; selected.value = null; pending.value = null; dirty.value = false
  replacing = true; dates.value = {}; reason.value = '核对各工序物料期'; replacing = false
  error.value = ''; notice.value = ''; loading.value = false; busy.value = false
}
function failure(e: unknown) {
  const cause = e as { response?: { status?: number; data?: { detail?: unknown } }; message?: string }
  if ([401, 403].includes(cause.response?.status || 0)) { epoch++; reset() }
  error.value = typeof cause.response?.data?.detail === 'string' ? cause.response.data.detail : cause.message || '保存失败，请核对日期后重试。'
}
function discard() { return !locked.value && (!dirty.value || window.confirm('物料期尚未保存，是否放弃改动？')) }
function adopt(row: DateDemand) {
  selected.value = row; replacing = true
  dates.value = Object.fromEntries(row.processes.map(p => [p, row.process_dates[p] || '']))
  replacing = false; dirty.value = false
}
function open(row: DateDemand) { if (discard()) { adopt(row); notice.value = ''; error.value = '' } }
async function load() {
  if (!discard()) return
  if (route.query.factory !== 'huakang-c') { reset(); return }
  const token = ++epoch; loading.value = true; error.value = ''
  selected.value = null; rows.value = []; dirty.value = false
  try {
    const a = await api.dateAccess(); if (token !== epoch) return
    access.value = a
    if (a.enabled && a.schema_ready) {
      const data = await api.dateWorkspace(); if (token !== epoch) return
      rows.value = data.items
    }
  } catch (e) { if (token === epoch) failure(e) }
  finally { if (token === epoch) loading.value = false }
}
async function save() {
  if (!selected.value || !writable.value || locked.value || !reason.value.trim()) return
  pending.value = { id: selected.value.id, body: { factory_id: 'huakang-c', operation_id: crypto.randomUUID(),
    expected_version: selected.value.version, reason: reason.value,
    dates: Object.fromEntries(selected.value.processes.map(p => [p, dates.value[p] || null])) } }
  await retry()
}
async function retry() {
  const original = pending.value; if (!original || busy.value) return
  const token = epoch; busy.value = true; error.value = ''
  try {
    const saved = await api.saveDates(original.id, original.body); if (token !== epoch) return
    // A successful retry may return an older receipt after Sales has reviewed
    // or withdrawn the request. Read current state before offering more edits.
    pending.value = null; selected.value = null; rows.value = []; dirty.value = false
    notice.value = `物料期已保存：${statusText(saved.status)}。`
    const current = await api.dateWorkspace(); if (token !== epoch) return
    rows.value = current.items
    const fresh = current.items.find(r => r.id === saved.id && r.version >= saved.version)
    if (fresh) adopt(fresh)
  } catch (e) {
    if (token !== epoch) return
    const status = (e as { response?: { status?: number } }).response?.status
    if (status && status < 500) pending.value = null
    failure(e)
  } finally { if (token === epoch) busy.value = false }
}
watch([dates, reason], () => { if (!replacing) dirty.value = true }, { deep: true, flush: 'sync' })
watch(() => [route.query.factory, auth.sessionVersion, auth.authorizationVersion], () => {
  epoch++; reset(); if (route.query.factory === 'huakang-c') void load()
}, { immediate: true })
function beforeUnload(e: BeforeUnloadEvent) { if (dirty.value || pending.value) { e.preventDefault(); e.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onBeforeRouteLeave(discard); onBeforeRouteUpdate(discard)
onBeforeUnmount(() => { epoch++; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <main class="process-dates space-y-5">
    <PageHeader title="工序物料期" description="采购按已提交需求逐工序填写物料期，再由原业务自审。">
      <template #actions><Button variant="outline" :disabled="locked" @click="load">刷新需求</Button></template>
    </PageHeader>
    <p v-if="route.query.factory !== 'huakang-c'">请在华康 C 打开工序物料期。</p>
    <p v-if="loading" role="status">正在读取需求…</p>
    <p v-if="error" role="alert" class="rounded-md bg-red-50 p-3 text-red-800">{{ error }}</p>
    <p v-if="notice" role="status" class="text-teal-800">{{ notice }}</p>
    <div v-if="pending && !busy"><p>保存结果尚未确认，请重试原请求。</p><Button @click="retry">核对并重试原请求</Button></div>
    <SectionPanel v-if="access && !ready" title="物料期流程尚未开放" subtitle="请管理员完成部署及启用。" />
    <template v-if="ready">
      <SectionPanel title="已提交需求" subtitle="仅包含业务提交的固定需求版本，不显示私人草稿。">
        <p v-if="!rows.length">暂无已提交需求。</p>
        <div v-else class="overflow-x-auto"><table><thead><tr><th>货号</th><th>业务</th><th>数量</th><th>状态／版本</th><th>操作</th></tr></thead><tbody><tr v-for="r in rows" :key="r.id"><td>{{ r.item_no }}</td><td>{{ r.owner_name }}</td><td>{{ r.quantity }} {{ r.unit }}</td><td>{{ statusText(r.status) }} · v{{ r.version }}</td><td><Button size="sm" variant="outline" :disabled="locked" @click="open(r)">查看／填期</Button></td></tr></tbody></table></div>
      </SectionPanel>
      <SectionPanel v-if="selected" :title="`${selected.item_no} · 工序物料期`">
        <p class="mb-3 text-sm text-slate-600">各工序分别设置，可先保存部分日期。日期不是实收到料或供应商在途证明，不据此抵扣库存、生成采购单或自动排产。</p>
        <p v-if="selected.status === 'SELF_REVIEWED_DATA_PENDING'" class="mb-3">业务已自审；修改前须由业务退回草稿重新提交。</p>
        <form @submit.prevent="save"><fieldset :disabled="locked || !writable">
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"><label v-for="p in selected.processes" :key="p">{{ p }}物料期<input v-model="dates[p]" type="date" :aria-label="`${p}物料期`" /></label></div>
          <label class="my-3">填期说明<input v-model="reason" maxlength="500" required /></label>
          <Button type="submit" :disabled="!reason.trim()">保存物料期</Button>
        </fieldset></form>
        <p v-if="selected.date_actor" class="my-3 text-sm">最近填期：{{ selected.date_actor.name }} · {{ selected.date_actor.at }}</p>
        <div class="mt-4 overflow-x-auto"><table><caption>本次用料依据（同编码不同属性分别保留）</caption><thead><tr><th>工序</th><th>物料</th><th>本次属性</th><th>含损耗用量</th><th>单位</th></tr></thead><tbody><tr v-for="line in selected.lines" :key="line.key"><td>{{ line.process }}</td><td>{{ line.code }} {{ line.name }}</td><td>{{ line.attribute }}</td><td>{{ quantityText(line.gross) }}</td><td>{{ line.unit }}</td></tr></tbody></table></div>
      </SectionPanel>
    </template>
  </main>
</template>

<style scoped>
.process-dates label { display: flex; flex-direction: column; gap: .35rem; font-size: .875rem; }
.process-dates input { width: 100%; min-width: 0; border: 1px solid var(--color-slate-300); border-radius: var(--radius-md); padding: .5rem .65rem; background: white; }
.process-dates table { width: 100%; min-width: 640px; border-collapse: collapse; font-size: .875rem; }
.process-dates th, .process-dates td { padding: .65rem; border-bottom: 1px solid var(--color-slate-200); text-align: center; }
.process-dates th { background: var(--color-slate-50); }
.process-dates caption { text-align: left; font-weight: 600; padding: .6rem 0; }
</style>
