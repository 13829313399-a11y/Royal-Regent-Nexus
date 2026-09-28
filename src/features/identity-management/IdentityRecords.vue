<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import { TabsRoot, TabsList, TabsTrigger, TabsContent } from 'reka-ui'
import {
  identityApi,
  changeLabels,
  type ChangeRecord,
  type ChangePreview,
  type HandoverItem,
  type HandoverSummary,
} from '@/api/identity'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { Button } from '@/components/ui/button'
import IamLeaveGuard from '@/components/iam/workspace/IamLeaveGuard.vue'
import IamStatusBadge from '@/components/iam/workspace/IamStatusBadge.vue'
import IamDisclosure from '@/components/iam/workspace/IamDisclosure.vue'
import {
  changeStatusPresentation,
  handoverStatusPresentation,
} from '@/components/iam/workspace/iam-status'
import IdentityShell from './IdentityShell.vue'
import AccessImpact from './AccessImpact.vue'
import AuditTimeline from './AuditTimeline.vue'
const appliedState = ref('')
const route = useRoute()
const audit = computed(() => route.path.endsWith('/audit'))
const rows = ref<ChangeRecord[]>([])
const selected = ref<ChangeRecord>()
const preview = ref<ChangePreview>()
const items = ref<HandoverItem[]>([])
const coverage = ref<HandoverSummary['coverage']>([])
const successors = ref<Record<string, string>>({})
const candidates = ref<Record<string, { id: string; display_name: string }[]>>({})
const loading = ref(false)
const busy = ref(false)
const detailLoading = ref(false)
const error = ref('')
const detailError = ref('')
const notice = ref('')
const state = ref('')
const reason = ref('')
const page = ref(1)
const total = ref(0)
const confirmed = ref(false)
const tab = ref('content')
const uncertain = ref(false)
const itemBusy = ref<Record<string, boolean>>({})
const key = ref(createRandomUuid())
const leaveGuard = ref<InstanceType<typeof IamLeaveGuard>>()
const dirty = computed(() =>
  Boolean(reason.value.trim() || confirmed.value || Object.values(successors.value).some(Boolean)),
)
const acting = computed(() => busy.value || Object.values(itemBusy.value).some(Boolean))
async function permitLeave() {
  if (acting.value) {
    detailError.value = '办理请求正在处理中，请等待结果后离开。'
    return false
  }
  return (await leaveGuard.value?.permitLeave()) ?? true
}
onBeforeRouteLeave(permitLeave)
onBeforeRouteUpdate(permitLeave)
async function backToQueue() {
  if (await permitLeave()) clearSelection()
}
let selectionGeneration = 0
let listGeneration = 0
let handoverGeneration = 0
function clearSelection() {
  ++selectionGeneration
  ++handoverGeneration
  selected.value = undefined
  preview.value = undefined
  confirmed.value = false
  detailError.value = ''
  notice.value = ''
  reason.value = ''
  items.value = []
  candidates.value = {}
  successors.value = {}
  coverage.value = []
  tab.value = 'content'
  busy.value = false
  detailLoading.value = false
  uncertain.value = false
  itemBusy.value = {}
}
function changePage(delta: number) {
  page.value += delta
  void load()
}
async function load(reset = false) {
  if (reset) {
    if (!(await permitLeave())) {
      state.value = appliedState.value
      return
    }
    page.value = 1
    clearSelection()
  }
  const generation = ++listGeneration
  loading.value = true
  error.value = ''
  try {
    const result = await identityApi.changes({
      state: state.value,
      page: page.value,
      target_user_id: typeof route.query.person === 'string' ? route.query.person : '',
    })
    if (generation === listGeneration) {
      rows.value = result.items
      total.value = result.total
      appliedState.value = state.value
    }
  } catch (e) {
    if (generation === listGeneration) {
      error.value = getApiErrorMessage(e)
      if ((e as { response?: { status?: number } }).response?.status === 403) {
        rows.value = []
        total.value = 0
        clearSelection()
      }
    }
  } finally {
    if (generation === listGeneration) loading.value = false
  }
}
async function loadHandover(row: ChangeRecord, generation: number) {
  if (generation !== selectionGeneration) return
  const reading = ++handoverGeneration
  detailLoading.value = true
  try {
    const result = await identityApi.handovers(row.id)
    if (generation !== selectionGeneration || reading !== handoverGeneration) return
    items.value = result.items
    coverage.value = result.coverage
    const people = await Promise.all(
      result.items
        .filter((i) => i.status === 'pending')
        .map(
          async (item) => [item.id, (await identityApi.handoverCandidates(item.id)).items] as const,
        ),
    )
    if (generation === selectionGeneration && reading === handoverGeneration)
      candidates.value = Object.fromEntries(people)
  } catch (e) {
    if (generation === selectionGeneration && reading === handoverGeneration) {
      detailError.value = getApiErrorMessage(e)
      if ((e as { response?: { status?: number } }).response?.status === 403) {
        items.value = []
        coverage.value = []
        candidates.value = {}
        successors.value = {}
      }
    }
  } finally {
    if (generation === selectionGeneration && reading === handoverGeneration)
      detailLoading.value = false
  }
}
async function select(row: ChangeRecord) {
  if (!(await permitLeave())) return
  clearSelection()
  selected.value = row
  void loadHandover(row, selectionGeneration)
}
async function previewSelected() {
  const row = selected.value
  if (!row || busy.value || uncertain.value) return
  const generation = selectionGeneration
  busy.value = true
  detailError.value = ''
  preview.value = undefined
  confirmed.value = false
  try {
    const result = await identityApi.preview(row.id)
    if (generation === selectionGeneration) {
      preview.value = result
      key.value = createRandomUuid()
      tab.value = 'impact'
    }
  } catch (e) {
    if (generation === selectionGeneration) detailError.value = getApiErrorMessage(e)
  } finally {
    if (generation === selectionGeneration) busy.value = false
  }
}
async function mutate(operation: (row: ChangeRecord) => Promise<ChangeRecord>, committing = false) {
  const row = selected.value
  if (!row || busy.value) return
  const generation = selectionGeneration
  busy.value = true
  detailError.value = ''
  notice.value = ''
  try {
    const result = await operation(row)
    if (generation !== selectionGeneration) return
    selected.value = result
    preview.value = undefined
    confirmed.value = false
    notice.value = `办理${changeStatusPresentation(result.state).label}。`
    reason.value = ''
    successors.value = {}
    uncertain.value = false
    await load()
    if (generation === selectionGeneration) await loadHandover(result, generation)
  } catch (e) {
    if (generation === selectionGeneration) {
      const code = (e as { response?: { status?: number } }).response?.status
      uncertain.value = committing && (!code || code >= 500)
      detailError.value = uncertain.value
        ? '提交结果待核查，请先查询服务器结果。'
        : getApiErrorMessage(e)
    }
  } finally {
    if (generation === selectionGeneration) busy.value = false
  }
}
function apply() {
  if (!preview.value || !confirmed.value || uncertain.value) return
  if (Date.parse(preview.value.expires_at) <= Date.now()) {
    detailError.value = '预览已过期，请重新核对并预览。'
    preview.value = undefined
    confirmed.value = false
    return
  }
  const impact = preview.value
  return mutate(
    (row) => identityApi.commit(row, impact, key.value, row.state === 'pending_approval'),
    true,
  )
}
function decide(action: 'cancel' | 'reject') {
  if (!reason.value.trim()) {
    detailError.value = '请填写办理原因'
    return
  }
  return mutate((row) => identityApi.decide(row, action, reason.value))
}
async function verifyResult() {
  const row = selected.value
  if (!row || busy.value) return
  const generation = selectionGeneration
  busy.value = true
  try {
    const result = await identityApi.change(row.id)
    if (generation !== selectionGeneration) return
    selected.value = result
    uncertain.value = false
    detailError.value = ''
    if (
      result.state !== row.state ||
      result.revision !== row.revision ||
      !['draft', 'pending_approval'].includes(result.state)
    ) {
      preview.value = undefined
      confirmed.value = false
    }
    notice.value = `服务器当前状态：${changeStatusPresentation(result.state).label}。`
    await load()
  } catch (e) {
    if (generation === selectionGeneration) detailError.value = getApiErrorMessage(e)
  } finally {
    if (generation === selectionGeneration) busy.value = false
  }
}
async function refreshHandover() {
  const row = selected.value
  if (!row || busy.value) return
  const generation = selectionGeneration
  busy.value = true
  detailError.value = ''
  try {
    await identityApi.refreshHandover(row.id)
    if (generation === selectionGeneration) {
      await loadHandover(row, generation)
      const latest = await identityApi.change(row.id)
      if (generation === selectionGeneration) selected.value = latest
    }
  } catch (e) {
    if (generation === selectionGeneration) detailError.value = getApiErrorMessage(e)
  } finally {
    if (generation === selectionGeneration) busy.value = false
  }
}
async function reassign(item: HandoverItem) {
  const row = selected.value
  const successor = successors.value[item.id]
  if (!row || !successor || itemBusy.value[item.id]) return
  const generation = selectionGeneration
  itemBusy.value[item.id] = true
  detailError.value = ''
  try {
    await identityApi.reassign(item, successor)
    if (generation === selectionGeneration) {
      await loadHandover(row, generation)
      successors.value[item.id] = ''
      notice.value = '接管结果已刷新。'
    }
  } catch (e) {
    if (generation === selectionGeneration) detailError.value = getApiErrorMessage(e)
  } finally {
    if (generation === selectionGeneration) itemBusy.value[item.id] = false
  }
}
watch(
  () => route.fullPath,
  () => {
    clearSelection()
    page.value = 1
    if (!audit.value) void load()
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  ++selectionGeneration
  ++listGeneration
})
</script>
<template>
  <IdentityShell
    ><AuditTimeline v-if="audit" />
    <section v-else class="iamx-surface">
      <header class="iamx-section-head">
        <div>
          <h2>
            变更办理 <span class="iamx-count">{{ total }} 条</span>
          </h2>
          <p>查看办理结果，核对影响并完成工作交接</p>
        </div>
        <Button variant="outline" :disabled="loading" @click="load()">刷新</Button>
      </header>
      <div class="iamx-toolbar">
        <label
          >办理状态
          <select v-model="state" :disabled="busy" @change="load(true)">
            <option value="">全部</option>
            <option
              v-for="s in [
                'draft',
                'pending_approval',
                'scheduled',
                'applied',
                'cancelled',
                'rejected',
              ]"
              :key="s"
              :value="s"
            >
              {{ changeStatusPresentation(s).label }}
            </option>
          </select></label
        ><span v-if="route.query.person" class="iamx-muted">人员：{{ route.query.person }}</span>
      </div>
      <p v-if="error" role="alert" class="iamx-error">
        {{ error }} <Button variant="outline" @click="load()">重试</Button>
      </p>
      <p v-if="loading" role="status" class="iamx-notice">正在读取办理队列…</p>
      <div class="iamx-queue-layout" :class="{ 'has-selection': selected }">
        <aside class="iamx-queue" aria-label="变更单列表">
          <button
            v-for="row in rows"
            :key="row.id"
            class="iamx-queue-item"
            :disabled="busy || Object.values(itemBusy).some(Boolean)"
            :aria-pressed="selected?.id === row.id"
            @click="select(row)"
          >
            <strong>{{ changeLabels[row.request_type] }}</strong
            ><IamStatusBadge :presentation="changeStatusPresentation(row.state)" />
            <p>{{ row.reason || '未填写原因' }}</p>
            <small>人员：{{ row.target_user_id }}</small
            ><small>{{ formatBusinessDateTime(row.created_at) }}</small>
          </button>
          <p v-if="!rows.length && !loading && !error" class="iamx-empty">当前筛选没有变更单。</p>
          <div class="iamx-pagination">
            <span>{{ total }} 条 · 第 {{ page }} 页</span>
            <div class="iamx-actions">
              <Button
                variant="outline"
                :disabled="loading || busy || page === 1"
                @click="changePage(-1)"
                >上一页</Button
              ><Button
                variant="outline"
                :disabled="loading || busy || page * 30 >= total"
                @click="changePage(1)"
                >下一页</Button
              >
            </div>
          </div>
        </aside>
        <section v-if="selected" class="iamx-record-detail">
          <Button variant="outline" class="iamx-back-to-queue" :disabled="busy" @click="backToQueue"
            >返回队列</Button
          >
          <header>
            <div class="iamx-actions">
              <h3>{{ changeLabels[selected.request_type] }}</h3>
              <IamStatusBadge :presentation="changeStatusPresentation(selected.state)" />
            </div>
            <p>{{ selected.reason }}</p>
            <RouterLink
              :to="`/system/users?person=${selected.target_user_id}`"
              class="iamx-link-button"
              >查看人员与任职</RouterLink
            >
            <p v-if="selected.effective_at" class="iamx-muted">
              生效：{{ formatBusinessDateTime(selected.effective_at) }}（北京时间）
            </p>
          </header>
          <p v-if="detailError" role="alert" class="iamx-error">{{ detailError }}</p>
          <p v-if="notice" role="status" class="iamx-success">{{ notice }}</p>
          <Button v-if="uncertain" variant="outline" :disabled="busy" @click="verifyResult"
            >核查提交结果</Button
          >
          <TabsRoot v-model="tab"
            ><TabsList class="iamx-tabs" aria-label="变更详情栏目"
              ><TabsTrigger value="content">变更内容</TabsTrigger
              ><TabsTrigger value="impact">权限影响</TabsTrigger
              ><TabsTrigger value="handover">工作交接</TabsTrigger></TabsList
            >
            <TabsContent value="content"
              ><div class="iamx-assignment">
                <h3>办理说明</h3>
                <p>{{ selected.reason || '未填写原因' }}</p>
                <p>申请人：{{ selected.requester_user_id }}</p>
                <p v-if="selected.payload.new_assignment">
                  {{ selected.payload.new_assignment.org_unit_id }} ·
                  {{ selected.payload.new_assignment.department_code }} ·
                  {{ selected.payload.new_assignment.official_position_title }}
                </p>
                <IamDisclosure title="查看原始办理内容">
                  <pre class="iamx-evidence">{{ JSON.stringify(selected.payload, null, 2) }}</pre>
                </IamDisclosure>
              </div>
              <div
                v-if="['draft', 'pending_approval', 'scheduled'].includes(selected.state)"
                class="iamx-form"
              >
                <label>撤回 / 驳回原因<textarea v-model="reason" rows="2" /></label>
                <div class="iamx-actions">
                  <Button
                    variant="outline"
                    :disabled="busy || uncertain || !reason.trim()"
                    @click="decide('cancel')"
                    >撤回变更</Button
                  ><Button
                    v-if="selected.state === 'pending_approval'"
                    variant="destructive"
                    :disabled="busy || uncertain || !reason.trim()"
                    @click="decide('reject')"
                    >驳回</Button
                  >
                </div>
              </div></TabsContent
            >
            <TabsContent value="impact"
              ><div
                v-if="['draft', 'pending_approval'].includes(selected.state)"
                class="iamx-assignment"
              >
                <Button :disabled="busy || uncertain" @click="previewSelected"
                  >重新核对并预览</Button
                ><AccessImpact v-if="preview" :preview="preview" /><template v-if="preview"
                  ><label class="iamx-actions"
                    ><input v-model="confirmed" type="checkbox" />已核对变更影响</label
                  ><Button :disabled="busy || uncertain || !confirmed" @click="apply">{{
                    selected.state === 'pending_approval'
                      ? '批准办理'
                      : preview.requires_approval
                        ? '提交审核'
                        : '确认办理'
                  }}</Button></template
                >
              </div>
              <p v-else class="iamx-empty">
                此变更已离开待提交阶段，请在授权与人员记录中查看历史事实。
              </p></TabsContent
            >
            <TabsContent value="handover"
              ><p v-if="detailLoading" role="status">正在读取交接范围…</p>
              <p v-if="selected.handover_refresh_pending" role="status" class="iamx-notice">
                任职已按服务器时间生效。交接清单仍待后台重新评估，可点击下方按钮刷新。
              </p>
              <div class="iamx-assignment">
                <Button
                  v-if="['applied', 'scheduled'].includes(selected.state)"
                  variant="outline"
                  :disabled="busy"
                  @click="refreshHandover"
                  >重新评估 / 重试</Button
                >
                <p class="iamx-muted">接管会再次检查单据版本、未完成状态和接管人的实际资格。</p>
              </div>
              <ul class="iamx-coverage">
                <li v-for="item in coverage" :key="item.module">
                  <strong>{{ item.module }}</strong
                  ><span>{{
                    item.status === 'uncovered'
                      ? '需人工核实'
                      : item.status === 'role_queue'
                        ? '按角色队列办理'
                        : '已接入'
                  }}</span
                  ><small>{{ item.basis }}</small>
                </li>
              </ul>
              <article v-for="item in items" :key="item.id" class="iamx-assignment">
                <strong>{{ item.resource_id }}</strong>
                <p>
                  {{ item.factory_id }} ·
                  <IamStatusBadge :presentation="handoverStatusPresentation(item.status)" />
                </p>
                <div v-if="item.status === 'pending'" class="iamx-form">
                  <label
                    >接管人<select v-model="successors[item.id]" :disabled="itemBusy[item.id]">
                      <option value="">请选择</option>
                      <option
                        v-for="person in candidates[item.id]"
                        :key="person.id"
                        :value="person.id"
                      >
                        {{ person.display_name }}
                      </option>
                    </select></label
                  >
                  <p v-if="!detailLoading && !candidates[item.id]?.length" class="iamx-muted">
                    当前没有符合资格的接管人。
                  </p>
                  <Button
                    :disabled="itemBusy[item.id] || busy || !successors[item.id]"
                    @click="reassign(item)"
                    >确认接管</Button
                  >
                </div>
              </article>
              <p v-if="!items.length && !detailLoading" class="iamx-notice">
                暂无已识别的个人交接项，未适配模块仍需人工核实。
              </p></TabsContent
            ></TabsRoot
          >
        </section>
        <p v-else class="iamx-empty">选择一条变更，查看内容、权限影响和工作交接。</p>
      </div>
    </section>
    <IamLeaveGuard
      ref="leaveGuard"
      :dirty="dirty"
      :busy="acting"
      description="撤回原因、接管人选择或确认勾选尚未提交。"
  /></IdentityShell>
</template>
