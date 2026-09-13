<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Activity, CircuitBoard, List, Save, Wrench } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type {
  UvExpense,
  UvMachine,
  UvMachineDetail,
  UvPrintJob,
  UvProduct,
  UvReport,
  UvRuntimeWindow,
} from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { newOperationId, useUvCommand, useUvRequest } from '../composables/useUvRequest'
import { useUvToast } from '../composables/useUvToast'
import UvStateBlock from '../components/UvStateBlock.vue'
import UvMachineCard from '../components/UvMachineCard.vue'
import UvTable from '../components/UvTable.vue'
import UvStatusPill from '../components/UvStatusPill.vue'
import UvNumber from '../components/UvNumber.vue'
import UvField from '../components/UvField.vue'
import UvFormField from '../components/UvFormField.vue'
import UvDrawer from '../components/UvDrawer.vue'
import { ADMIN_STATUS, CAPABILITY_LABELS, FRESHNESS, INK_MATERIAL_LABELS, JOB_STATE, QUALITY_STATUS, RAW_UNIT, RECONCILIATION, REPORT_STATUS, TIME_EVIDENCE_LABEL } from '../domain/status'
import { formatDuration, shanghaiDateTimeString, shanghaiTimeString } from '../domain/businessTime'
import { formatMoney } from '../domain/decimal'

/**
 * 机台工作区：卡片/列表可切换；机台详情包含任务时序、班次人员、维护费用与采集能力清单。
 *
 * - 行政状态、遥测状态、新鲜度三个维度分别维护，不信遥测覆盖行政状态；
 * - 普通 PATCH 只能改行政状态/材质/备注，不能伪造遥测；
 * - 运行时序按真实时间刻度，数据缺口留空并标注，不画成「已排未来任务」；
 * - 能力清单说明适配器是否支持准确进度、分色耗墨、稳定作业 ID、真实开始/完成时间。
 */

const ctx = inject(UV_CONTEXT_KEY)!
const transport = inject(UV_TRANSPORT_KEY)!
const route = useRoute()
const router = useRouter()
const toast = useUvToast()
const workspace = ctx.workspace
const scope = computed(() => workspace.scope.value)

const view = ref<'cards' | 'list'>('cards')
const search = ref('')

const machineRequest = useUvRequest<{ items: UvMachine[] }>(
  (signal) => transport.value.machines({ ...scope.value, q: search.value || undefined, page_size: 200 }, signal),
  { watchSource: () => [scope.value.business_date, search.value, ctx.revision.value] },
)

const productRequest = useUvRequest<{ items: UvProduct[] }>(
  (signal) => transport.value.products({ ...scope.value, page_size: 200 }, signal),
  { watchSource: () => [ctx.revision.value] },
)

const machines = computed(() => machineRequest.data.value?.items ?? [])
const products = computed(() => productRequest.data.value?.items ?? [])

const selectedId = computed(() => (typeof route.params.id === 'string' ? route.params.id : ''))

const detailRequest = useUvRequest<UvMachineDetail>(
  (signal) => transport.value.machineDetail(selectedId.value, scope.value, signal),
  { watchSource: () => [selectedId.value, scope.value.business_date, ctx.revision.value] },
)

const detail = computed(() => detailRequest.data.value)

const editOpen = ref(false)
const editAdmin = ref<UvMachine['admin_status']>('normal')
const editMaterial = ref<UvMachine['ink_material']>('hard')
const editNote = ref('')
const saveCommand = useUvCommand<unknown>()

const reportRequest = useUvRequest<{ items: UvReport[] }>(
  (signal) => transport.value.reports({ ...scope.value, page_size: 200 }, signal),
  { watchSource: () => [scope.value.business_date, ctx.revision.value] },
)

function goodQtyFor(machineId: string): number | null {
  const reports = (reportRequest.data.value?.items ?? []).filter((report) =>
    report.machine_id === machineId && report.status === 'confirmed',
  )
  if (!reports.length) return null
  return reports.reduce((total, report) => total + report.good_qty, 0)
}

const orderedMachines = computed(() => [...machines.value].sort((a, b) => a.code.localeCompare(b.code, 'en')))

function openMachine(machineId: string) {
  void router.push({ path: `${workspace.workspacePath}/machines/${machineId}`, query: route.query })
}

function closeDetail() {
  void router.push({ path: `${workspace.workspacePath}/machines`, query: route.query })
}

function productLabel(productId: string | null): string {
  if (!productId) return '未匹配产品'
  const product = products.value.find((candidate) => candidate.id === productId)
  return product ? `${product.product_no} · ${product.name}` : productId
}

function openEdit(machine: UvMachine) {
  editAdmin.value = machine.admin_status
  editMaterial.value = machine.ink_material
  editNote.value = machine.note
  saveCommand.clearError()
  editOpen.value = true
}

async function saveMachine() {
  const machine = detail.value?.machine
  if (!machine) return
  const operationId = newOperationId()
  const result = await saveCommand.execute(operationId, async () => {
    const response = await transport.value.saveMachine({
      factory_id: 'huakang-a',
      operation_id: operationId,
      expected_version: machine.version,
      id: machine.id,
      admin_status: editAdmin.value,
      ink_material: editMaterial.value,
      note: editNote.value,
      enabled: editAdmin.value !== 'disabled',
    })
    return response.data
  })
  if (!result) return
  ctx.markDirty()
  editOpen.value = false
  toast.push({
    message: `已保存机台档案：${machine.code}`,
    detail: '行政状态不会改变遥测状态与心跳新鲜度；普通保存不能伪造设备状态。',
    tone: 'green',
    retryable: false,
  })
}

/* ---------------- 运行时序 ---------------- */

const DAY_START_HOUR = 7
const DAY_END_HOUR = 24

/** 时序按真实时间刻度定位；gap 表示无采集数据的缺口。 */
function windowStyle(window: UvRuntimeWindow): Record<string, string> {
  const start = new Date(window.start_at)
  const end = window.end_at ? new Date(window.end_at) : new Date(start.getTime() + 15 * 60_000)
  const shanghaiStart = Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Shanghai', hour: '2-digit', hour12: false }).format(start))
  const shanghaiEnd = Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Shanghai', hour: '2-digit', hour12: false }).format(end))
  const span = DAY_END_HOUR - DAY_START_HOUR
  const left = ((shanghaiStart + start.getMinutes() / 60 - DAY_START_HOUR) / span) * 100
  const width = Math.max(1.5, ((shanghaiEnd + end.getMinutes() / 60 - (shanghaiStart + start.getMinutes() / 60)) / span) * 100)
  if (shanghaiStart > DAY_END_HOUR) {
    // 凌晨（夜班后半段）挪到最右侧，避免出现负数宽度。
    return { left: `${Math.min(98, Math.max(0, left))}%`, width: `${Math.min(width, 100)}%` }
  }
  return {
    left: `${Math.min(98, Math.max(0, ((shanghaiStart + start.getMinutes() / 60 - DAY_START_HOUR) / span) * 100))}%`,
    width: `${Math.min(Math.max(width, 1.5), 100)}%`,
  }
}

const runtimeToday = computed(() =>
  (detail.value?.runtime_windows ?? []).filter((window) => {
    const parts = shanghaiDateTimeString(window.start_at)
    return parts.slice(0, 10) === scope.value.business_date
  }),
)

const maintenanceExpenses = computed(() =>
  (detail.value?.expenses ?? []).filter((expense: UvExpense) => expense.category === 'maintenance'),
)

const machineReports = computed(() => detail.value?.reports ?? [])
const machineJobs = computed(() => detail.value?.jobs ?? [])

const efficiency = computed(() => {
  const runMinutes = runtimeToday.value
    .filter((window) => window.kind === 'run')
    .reduce((total, window) => total + (window.duration_minutes ?? 0), 0)
  const gapMinutes = runtimeToday.value
    .filter((window) => window.kind === 'gap')
    .reduce((total, window) => total + (window.duration_minutes ?? 0), 0)
  return { runMinutes, gapMinutes }
})

watch(selectedId, () => {
  detailRequest.reset()
})
</script>

<template>
  <div class="space-y-4">
    <header class="uv-page-head">
      <div class="uv-page-head__titles">
        <p class="uv-page-head__eyebrow">Machines</p>
        <h1>机台</h1>
        <p class="uv-page-head__desc">
          行政状态（正常/维修/停用）、遥测状态（打印/待机/离线/错误/未知）与采集新鲜度分别维护，三个维度不能互相覆盖。
        </p>
      </div>
      <div class="uv-page-head__actions">
        <Button
          variant="outline"
          type="button"
          :aria-pressed="view === 'cards'"
          @click="view = 'cards'"
        >
          <CircuitBoard class="size-4" aria-hidden="true" />
          卡片
        </Button>
        <Button
          variant="outline"
          type="button"
          :aria-pressed="view === 'list'"
          @click="view = 'list'"
        >
          <List class="size-4" aria-hidden="true" />
          列表
        </Button>
      </div>
    </header>

    <div class="uv-filters">
      <div class="uv-filters__row">
        <div class="uv-filter" style="min-width: 220px">
          <label class="uv-filter__label" for="uv-machine-search">搜索机号 / 品牌 / 型号</label>
          <input id="uv-machine-search" v-model="search" class="uv-input" type="search" placeholder="UV-01">
        </div>
        <div class="uv-filters__meta">
          <span class="uv-filters__summary">共 {{ machines.length }} 台 · 业务日 {{ scope.business_date }}</span>
        </div>
      </div>
    </div>

    <UvStateBlock
      v-if="machineRequest.loading.value && !machines.length"
      state="loading"
      subject="机台列表"
    />
    <UvStateBlock
      v-else-if="machineRequest.error.value"
      state="error"
      subject="机台列表"
      :message="machineRequest.error.value.message"
      retryable
      @retry="machineRequest.run"
    />
    <UvStateBlock
      v-else-if="!machines.length"
      state="no-result"
      subject="机台"
      hint="本厂区没有匹配的机台主数据；机台数量从配置读取，不使用 10/11/12 的硬值。"
      @action="search = ''"
    />

    <div v-else-if="view === 'cards'" class="uv-machine-grid">
      <UvMachineCard
        v-for="machine in orderedMachines"
        :key="machine.id"
        :machine="machine"
        :good-qty="goodQtyFor(machine.id)"
        :reports="(reportRequest.data.value?.items ?? []).filter((report) => report.machine_id === machine.id)"
        :as-of="workspace.sampleAsOf.value"
        :selected="selectedId === machine.id"
        @open="openMachine(machine.id)"
      />
    </div>

    <section v-else class="uv-panel" aria-label="机台列表">
      <div class="uv-panel__body uv-panel__body--flush">
        <UvTable
          :columns="[
            { key: 'code', label: '机号', width: 92 },
            { key: 'name', label: '名称 / 型号' },
            { key: 'admin', label: '行政状态', width: 116 },
            { key: 'runtime', label: '遥测状态', width: 116 },
            { key: 'fresh', label: '新鲜度', width: 116 },
            { key: 'heartbeat', label: '最后心跳', width: 168 },
            { key: 'task', label: '当前任务', width: 190 },
            { key: 'good', label: '今日合格', width: 110, align: 'right' },
            { key: 'open', label: '详情', width: 92, align: 'right' },
          ]"
          :min-width="1180"
          dense
          caption="机台列表"
        >
          <tr v-for="machine in orderedMachines" :key="machine.id">
            <td><span class="uv-mono">{{ machine.code }}</span></td>
            <td>
              <span class="uv-row-primary">{{ machine.name }}</span>
              <span class="uv-row-sub">{{ machine.brand }} {{ machine.model }} · {{ INK_MATERIAL_LABELS[machine.ink_material] }}</span>
            </td>
            <td><UvStatusPill :status="ADMIN_STATUS[machine.admin_status]" compact /></td>
            <td>
              <UvStatusPill :status="machine.runtime_status === 'printing' ? { label: '打印中', tone: 'teal' } : machine.runtime_status === 'idle' ? { label: '待机', tone: 'slate' } : machine.runtime_status === 'offline' ? { label: '离线', tone: 'red' } : machine.runtime_status === 'error' ? { label: '设备报错', tone: 'red' } : { label: '状态未知', tone: 'slate' }" compact />
            </td>
            <td><UvStatusPill :status="FRESHNESS[machine.freshness]" compact /></td>
            <td>
              <span class="uv-mono">
                {{ machine.last_heartbeat_at ? shanghaiDateTimeString(machine.last_heartbeat_at) : '从未上报' }}
              </span>
            </td>
            <td>{{ machine.current_task_name ?? '—' }}</td>
            <td>
              <UvNumber :qty="goodQtyFor(machine.id)" size="sm" :state="goodQtyFor(machine.id) === null ? 'pending' : 'normal'" unit="件" />
            </td>
            <td style="text-align: right">
              <Button variant="outline" size="sm" type="button" @click="openMachine(machine.id)">打开</Button>
            </td>
          </tr>
        </UvTable>
      </div>
    </section>

    <!-- 机台详情 -->
    <UvDrawer
      :open="Boolean(selectedId)"
      size="lg"
      :title="detail ? `${detail.machine.code} · ${detail.machine.name}` : '机台详情'"
      :subtitle="detail ? `${detail.machine.brand} ${detail.machine.model} · 采集器 ${detail.machine.connector_id ?? '未登记'}` : ''"
      @close="closeDetail"
    >
      <UvStateBlock
        v-if="detailRequest.loading.value && !detail"
        state="loading"
        subject="机台详情"
      />
      <UvStateBlock
        v-else-if="detailRequest.error.value"
        state="error"
        subject="机台详情"
        :message="detailRequest.error.value.message"
        retryable
        @retry="detailRequest.run"
      />
      <template v-else-if="detail">
        <div class="uv-section">
          <p class="uv-section__title"><span class="uv-section__index">1</span>状态与档案</p>
          <dl class="uv-detail-grid">
            <UvField label="行政状态" :value="ADMIN_STATUS[detail.machine.admin_status].label" />
            <UvField label="遥测状态" :value="detail.machine.runtime_status === 'printing' ? '打印中' : detail.machine.runtime_status === 'idle' ? '待机' : detail.machine.runtime_status === 'offline' ? '离线' : detail.machine.runtime_status === 'error' ? '设备报错' : '状态未知'" />
            <UvField label="采集新鲜度" :value="FRESHNESS[detail.machine.freshness].label" />
            <UvField
              label="最后心跳"
              :value="detail.machine.last_heartbeat_at ? shanghaiDateTimeString(detail.machine.last_heartbeat_at) : null"
              missing-label="从未连接"
              hint="失联不等于停机，需要同时看最后心跳"
            />
            <UvField label="墨水材质" :value="INK_MATERIAL_LABELS[detail.machine.ink_material]" />
            <UvField label="当前任务" :value="detail.machine.current_task_name" missing-label="没有采集到的运行任务" />
            <UvField label="档案备注" :value="detail.machine.note || null" missing-label="无" :span="2" />
          </dl>
          <div class="uv-actions" style="margin-top: 10px">
            <Button
              variant="outline"
              size="sm"
              type="button"
              :disabled="!workspace.can('uv_printing:master_write')"
              @click="openEdit(detail.machine)"
            >
              <Wrench class="size-3.5" aria-hidden="true" />
              维护档案（行政状态）
            </Button>
            <span v-if="!workspace.can('uv_printing:master_write')" class="uv-readonly-note">
              没有基础资料维护权限
            </span>
          </div>
        </div>

        <div class="uv-section">
          <p class="uv-section__title"><span class="uv-section__index">2</span>采集能力清单</p>
          <ul class="uv-list">
            <li v-for="(label, key) in CAPABILITY_LABELS" :key="key">
              <span class="uv-list__dot" aria-hidden="true" />
              <span>
                {{ label }}：
                <strong>
                  {{ detail.machine.capabilities[key as keyof typeof detail.machine.capabilities] ? '设备提供' : '设备未提供' }}
                </strong>
              </span>
            </li>
          </ul>
          <p class="uv-state__hint">
            能力由适配器逐台确认；「不支持」显示为设备未提供，不能靠推断补齐。三次读不到 UI 不是可靠完工信号。
          </p>
        </div>

        <div class="uv-section">
          <p class="uv-section__title"><span class="uv-section__index">3</span>当天运行区间（真实时间刻度）</p>
          <p class="uv-state__hint">
            刻度 {{ DAY_START_HOUR }}:00 – 24:00（上海时间）。缺口留空并标注，不制造连续数据，也不把历史运行时序画成已排未来任务。
          </p>
          <div v-if="!runtimeToday.length" class="uv-callout">当业务日没有采集到的运行区间。</div>
          <div v-else class="uv-timeline">
            <div v-for="window in runtimeToday" :key="window.id" class="uv-timeline__row">
              <span class="uv-mono">
                {{ shanghaiTimeString(window.start_at) }}–{{ window.end_at ? shanghaiTimeString(window.end_at) : '进行中' }}
              </span>
              <div class="uv-timeline__track">
                <div
                  v-if="window.kind === 'gap'"
                  class="uv-timeline__gap"
                  :style="windowStyle(window)"
                />
                <div
                  v-else
                  class="uv-timeline__bar"
                  :class="window.kind === 'idle' ? 'uv-timeline__bar--cancelled' : ''"
                  :style="windowStyle(window)"
                  :title="`${window.label} · ${window.evidence === 'observed' ? '设备时间' : window.evidence === 'inferred' ? '推断时间' : '时间待确认'}`"
                />
              </div>
            </div>
          </div>
          <dl class="uv-detail-grid" style="margin-top: 10px">
            <UvField label="累计运行（采集区间）" :value="formatDuration(efficiency.runMinutes)" />
            <UvField label="数据缺口" :value="efficiency.gapMinutes ? formatDuration(efficiency.gapMinutes) : '无 30 分钟以上缺口'" />
            <UvField label="时间利用率口径" value="仅按采集到的运行区间 / 当天可用时间" hint="开机率与时间利用率分开，不命名为 OEE" :span="2" />
          </dl>
        </div>

        <div class="uv-section">
          <p class="uv-section__title"><span class="uv-section__index">4</span>当天任务与报工</p>
          <div v-if="!machineJobs.length" class="uv-callout">当天没有采集作业。</div>
          <UvTable
            v-else
            :columns="[
              { key: 'task', label: '原始任务' },
              { key: 'state', label: '作业/核对', width: 176 },
              { key: 'raw', label: '原始次数', width: 116, align: 'right' },
              { key: 'time', label: '时间证据', width: 150 },
            ]"
            :min-width="640"
            dense
            caption="机台当天采集作业"
          >
            <tr v-for="job in machineJobs.slice(0, 20)" :key="job.id">
              <td>
                <span class="uv-row-primary">{{ job.raw_task_name }}</span>
                <span class="uv-row-sub">{{ productLabel(job.product_id) }} · 源作业 {{ job.source_job_id }}</span>
              </td>
              <td>
                <UvStatusPill :status="JOB_STATE[job.state]" compact />
                <UvStatusPill :status="RECONCILIATION[job.reconciliation]" compact />
              </td>
              <td>
                <UvNumber :value="job.raw_count ?? null" state="missing" size="sm" />
                <span class="uv-row-sub">{{ RAW_UNIT[job.raw_unit] }}</span>
              </td>
              <td>{{ TIME_EVIDENCE_LABEL[job.time_evidence] }}</td>
            </tr>
          </UvTable>

          <div v-if="machineReports.length" class="uv-section">
            <p class="uv-section__title">报工记录</p>
            <ul class="uv-list">
              <li v-for="report in machineReports.slice(0, 12)" :key="report.id">
                <span class="uv-list__dot" aria-hidden="true" />
                <span>
                  {{ report.business_date }} {{ report.shift === 'day' ? '白班' : '夜班' }} ·
                  {{ report.product_no }} · 报工 {{ report.reported_qty }} / 合格 {{ report.good_qty }} ·
                  <UvStatusPill :status="REPORT_STATUS[report.status]" compact />
                  <UvStatusPill :status="QUALITY_STATUS[report.quality_status]" compact />
                </span>
              </li>
            </ul>
          </div>
        </div>

        <div class="uv-section">
          <p class="uv-section__title"><span class="uv-section__index">5</span>当班人员与维护费用</p>
          <dl class="uv-detail-grid">
            <UvField
              label="当班人员"
              :value="(detail.assignments.length ? detail.assignments.map((assignment) => assignment.worker_id).join('、') : null)"
              missing-label="当天没有排班"
              hint="人员显示名在人员班次页维护；这里只显示排班关联"
              :span="2"
            />
          </dl>
          <div v-if="!maintenanceExpenses.length" class="uv-callout">该机台没有维修费用记录。</div>
          <ul v-else class="uv-list">
            <li v-for="expense in maintenanceExpenses" :key="expense.id">
              <span class="uv-list__dot" aria-hidden="true" />
              <span>
                {{ expense.occurred_on }} · 维修
                {{ expense.amount ? formatMoney(expense.amount) : '金额待核' }}
                · {{ expense.evidence || '无凭证说明' }}
              </span>
            </li>
          </ul>
          <p class="uv-state__hint">维修费用引用费用记录，不新建备件采购系统。</p>
        </div>

        <div class="uv-callout">
          <Activity class="inline size-3.5" aria-hidden="true" />
          本页只展示采集事实与档案；远程开机、启动打印、修改打印参数等硬件控制不在本期范围。
        </div>
      </template>

      <template #actions>
        <Button variant="outline" type="button" @click="closeDetail">关闭</Button>
      </template>
    </UvDrawer>

    <!-- 档案维护 -->
    <UvDrawer
      :open="editOpen"
      size="sm"
      title="维护机台档案"
      subtitle="只允许修改行政状态、墨水材质与备注；遥测状态与心跳由采集器提供。"
      :busy="saveCommand.pending.value"
      @close="editOpen = false"
    >
      <div class="uv-form">
        <UvFormField label="行政状态" required field-id="uv-m-admin">
          <select id="uv-m-admin" v-model="editAdmin" class="uv-input uv-select">
            <option value="normal">正常</option>
            <option value="maintenance">维修中</option>
            <option value="disabled">已停用</option>
          </select>
        </UvFormField>
        <UvFormField label="墨水材质" required field-id="uv-m-material">
          <select id="uv-m-material" v-model="editMaterial" class="uv-input uv-select">
            <option value="hard">硬墨</option>
            <option value="soft">软墨</option>
            <option value="other">其他材质</option>
          </select>
        </UvFormField>
        <UvFormField label="备注" field-id="uv-m-note" :span="2">
          <textarea id="uv-m-note" v-model="editNote" class="uv-input uv-textarea" rows="3" />
        </UvFormField>
      </div>
      <div v-if="saveCommand.error.value" class="uv-callout uv-callout--warning" role="alert">
        {{ saveCommand.error.value.message }}
      </div>
      <div class="uv-callout">
        停用不会删除历史记录；设备停用后仍可查询历史作业与报工。
      </div>

      <template #actions>
        <Button variant="outline" type="button" @click="editOpen = false">取消</Button>
        <Button type="button" :disabled="saveCommand.pending.value" @click="saveMachine">
          <Save class="size-4" aria-hidden="true" />
          保存档案
        </Button>
      </template>
    </UvDrawer>
  </div>
</template>
