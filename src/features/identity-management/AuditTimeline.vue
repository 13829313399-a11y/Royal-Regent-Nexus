<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { changeLabels } from '@/api/identity'
import { getAuditEvents, type AuditEventOut, type AuditFilters } from '@/api/iam-audit'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { Button } from '@/components/ui/button'
import IamDisclosure from '@/components/iam/workspace/IamDisclosure.vue'
const events = ref<AuditEventOut[]>([])
const loading = ref(false)
const error = ref('')
const loaded = ref(false)
const applied = ref('')
const filters = reactive<AuditFilters>({
  actor_user_id: '',
  target_user_id: '',
  module_code: '',
  factory_id: '',
  department: '',
  from: '',
  to: '',
  limit: 100,
})
let generation = 0
const labels: Record<string, string> = {
  role_template_updated: '权限方案调整',
  access_request_approved: '授权申请获批',
  access_request_rejected: '授权申请驳回',
  access_request_submitted: '提交授权申请',
  permission_override_removed: '移除个人例外',
  permission_override_set: '设置个人例外',
  role_binding_add: '新增授权来源',
  role_binding_revoke: '撤销授权来源',
  system_position_assign: '分配旧权限职位',
  identity_enrollment: '注册建立正式任职',
  identity_cancelled: '撤回人员变更',
  identity_rejected: '驳回人员变更',
  ...Object.fromEntries(
    Object.entries(changeLabels).map(([code, label]) => [`identity_${code}`, label]),
  ),
}
const groups = computed(() => {
  const result = new Map<string, AuditEventOut[]>()
  for (const event of events.value) {
    const day = formatBusinessDateTime(event.created_at).slice(0, 10)
    result.set(day, [...(result.get(day) ?? []), event])
  }
  return [...result].map(([day, rows]) => ({ day, rows }))
})
async function load() {
  const request = ++generation
  loading.value = true
  error.value = ''
  const query = { ...filters }
  try {
    if (query.from && query.to && query.from > query.to)
      throw new Error('开始时间不能晚于结束时间。')
    const result = await getAuditEvents(query)
    if (request !== generation) return
    events.value = result
    loaded.value = true
    applied.value = `读取上限 ${query.limit} 条${query.from || query.to ? ` · 北京时间 ${query.from || '不限'} 至 ${query.to || '不限'}` : ''}`
  } catch (e) {
    if (request === generation) {
      error.value = getApiErrorMessage(e)
      if ((e as { response?: { status?: number } }).response?.status === 403) {
        events.value = []
        loaded.value = false
      }
    }
  } finally {
    if (request === generation) loading.value = false
  }
}
onMounted(load)
onBeforeUnmount(() => {
  ++generation
})
</script>
<template>
  <section class="iamx-surface">
    <header class="iamx-section-head">
      <div>
        <h2>授权与人员记录</h2>
        <p>按时间查看操作人与授权变化</p>
      </div>
      <Button variant="outline" :disabled="loading" @click="load">刷新</Button>
    </header>
    <form class="iamx-audit-filters" @submit.prevent="load">
      <label>操作人 ID<input v-model="filters.actor_user_id" placeholder="留空不限" /></label
      ><label>目标人员 ID<input v-model="filters.target_user_id" placeholder="留空不限" /></label
      ><label>模块代码<input v-model="filters.module_code" placeholder="例如 system" /></label
      ><label>厂区 ID<input v-model="filters.factory_id" placeholder="留空不限" /></label
      ><label>部门代码<input v-model="filters.department" placeholder="留空不限" /></label
      ><label>开始时间（北京时间）<input v-model="filters.from" type="datetime-local" /></label
      ><label>结束时间（北京时间）<input v-model="filters.to" type="datetime-local" /></label
      ><label
        >读取上限<select v-model.number="filters.limit">
          <option :value="100">100 条</option>
          <option :value="200">200 条</option>
          <option :value="500">500 条</option>
        </select></label
      ><Button type="submit" :disabled="loading">查询记录</Button>
    </form>
    <p v-if="error" role="alert" class="iamx-error">
      {{ error }} <Button variant="outline" @click="load">重试</Button>
    </p>
    <p v-if="loading" role="status" class="iamx-notice">正在读取记录…</p>
    <div class="iamx-audit-list">
      <p v-if="loaded" class="iamx-notice">
        本次返回 {{ events.length }} 条可见记录。{{
          applied
        }}。结果受读取上限和可见范围限制，不代表完整历史或总数。
      </p>
      <p v-if="loaded && !events.length && !error" class="iamx-empty">本次查询未返回可见记录。</p>
      <section v-for="group in groups" :key="group.day">
        <h3 class="iamx-audit-day">{{ group.day }}</h3>
        <article v-for="event in group.rows" :key="event.id" class="iamx-audit-event">
          <header>
            <strong>{{ labels[event.event_type] || '其他操作记录' }}</strong
            ><small>{{ formatBusinessDateTime(event.created_at) }}（北京时间）</small>
          </header>
          <p>
            {{ event.actor_name || event.actor_user_id || '未记录操作人' }} →
            {{ event.target_user_name || event.target_user_id || '无指定人员' }}
          </p>
          <p>{{ event.reason || '未填写原因' }}</p>
          <small>{{
            [event.permission_code, event.factory_id, event.department].filter(Boolean).join(' · ')
          }}</small
          ><IamDisclosure title="查看记录依据"
            ><p>事件代码：{{ event.event_type }}</p>
            <p>请求：{{ event.request_id || '—' }} · 来源 IP：{{ event.ip_address || '—' }}</p>
            <h3>变更前</h3>
            <pre class="iamx-evidence">{{
              JSON.stringify(event.before_value, null, 2) ?? '未记录'
            }}</pre>
            <h3>变更后</h3>
            <pre class="iamx-evidence">{{
              JSON.stringify(event.after_value, null, 2) ?? '未记录'
            }}</pre>
          </IamDisclosure>
        </article>
      </section>
    </div>
  </section>
</template>
