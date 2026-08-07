<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, ShieldCheck, X } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import { downloadPlanExport } from '../api/injectionSchedulingV2Api'
import type { FactoryId, PlanExportMode, PlanExportResult, SchedulingPlanRecord } from '../types'

const props = defineProps<{
  open: boolean
  factoryId: FactoryId
  plan: SchedulingPlanRecord | null
  canExport: boolean
  sourceMode: 'live' | 'fallback'
  pendingCount: number
}>()
const emit = defineEmits<{ close: []; exported: [result: PlanExportResult] }>()
const mode = ref<PlanExportMode>('SYSTEM_STANDARD')
const busy = ref(false)
const error = ref('')
const result = ref<PlanExportResult | null>(null)
const sourceCompatibleAvailable = computed(() => Boolean(
  props.plan?.exportBindingSource === 'IMPORT_PROFILE'
  && props.plan.exportProfileId
  && props.plan.exportProfileRevision,
))
const canSubmit = computed(() => Boolean(
  props.plan
  && props.canExport
  && props.sourceMode === 'live'
  && props.pendingCount === 0
  && (!sourceCompatibleAvailable.value ? mode.value !== 'SOURCE_COMPATIBLE' : true),
))

watch(() => [props.open, props.plan?.id, props.plan?.revision] as const, ([open]) => {
  if (!open) return
  mode.value = sourceCompatibleAvailable.value ? 'SOURCE_COMPATIBLE' : 'SYSTEM_STANDARD'
  busy.value = false
  error.value = ''
  result.value = null
})

function saveBlob(exported: PlanExportResult) {
  const url = URL.createObjectURL(exported.blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = exported.fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

async function exportPlan() {
  if (!props.plan || !canSubmit.value || busy.value) return
  busy.value = true
  error.value = ''
  result.value = null
  try {
    const exported = await downloadPlanExport(props.factoryId, props.plan, mode.value)
    result.value = exported
    saveBlob(exported)
    emit('exported', exported)
  } catch (cause) {
    error.value = getApiErrorMessage(cause)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div v-if="open" class="export-backdrop" @mousedown.self="emit('close')">
    <section role="dialog" aria-modal="true" aria-labelledby="plan-export-title">
      <header><div><FileSpreadsheet :size="19" /><strong id="plan-export-title">导出计划工作簿</strong></div><button aria-label="关闭" @click="emit('close')"><X :size="17" /></button></header>
      <div class="export-body">
        <p v-if="sourceMode !== 'live'" class="notice"><AlertTriangle :size="16" />当前为只读演示，不能生成正式导出审计。</p>
        <p v-else-if="pendingCount" class="notice"><AlertTriangle :size="16" />存在 {{ pendingCount }} 项未保存修改，请先保存或放弃后再导出。</p>
        <p v-if="error" class="notice error"><AlertTriangle :size="16" />{{ error }}</p>
        <dl v-if="plan" class="snapshot">
          <div><dt>当前快照</dt><dd>{{ plan.status }} · r{{ plan.revision }}</dd></div>
          <div><dt>计算版本</dt><dd>{{ plan.calculationVersion || '历史计划未标记' }}</dd></div>
          <div><dt>来源绑定</dt><dd>{{ plan.exportProfileFamily || plan.exportBindingSource || 'LEGACY_UNKNOWN' }}</dd></div>
        </dl>
        <fieldset>
          <legend>选择导出契约</legend>
          <label :class="{ disabled: !sourceCompatibleAvailable }"><input v-model="mode" type="radio" value="SOURCE_COMPATIBLE" :disabled="!sourceCompatibleAvailable" /><span><strong>来源兼容格式</strong><small>按计划锁定的 Profile revision 生成，可重新导入同厂区。</small><em v-if="sourceCompatibleAvailable">{{ plan?.exportProfileId }} · r{{ plan?.exportProfileRevision }}</em><em v-else>当前计划没有 IMPORT_PROFILE binding</em></span></label>
          <label><input v-model="mode" type="radio" value="SYSTEM_STANDARD" /><span><strong>系统标准格式</strong><small>生成新的规范字段工作簿，不复用来源模板、公式、宏或外链。</small><em>system_standard_v1</em></span></label>
        </fieldset>
        <p class="security"><ShieldCheck :size="16" />文件包含 veryHidden 的签名元数据；服务端记录计划版本、Profile、SHA-256、操作者与审计编号。</p>
        <button class="export-primary" :disabled="!canSubmit || busy" @click="exportPlan"><Download :size="16" />{{ busy ? '生成与签名中…' : '生成并下载 XLSX' }}</button>
        <div v-if="result" class="export-result"><CheckCircle2 :size="17" /><div><strong>导出完成</strong><p>{{ result.fileName }}</p><small>审计 {{ result.auditId }} · SHA-256 {{ result.fileSha256 }}</small></div></div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.export-backdrop{position:fixed;inset:0;z-index:74;background:rgba(15,23,42,.58);display:grid;place-items:center}.export-backdrop>section{width:min(680px,94vw);max-height:92vh;overflow:auto;background:#fff;border-radius:16px;box-shadow:0 24px 72px rgba(15,23,42,.35)}header{display:flex;justify-content:space-between;align-items:center;padding:16px 18px;border-bottom:1px solid #e2e8f0}header>div{display:flex;gap:8px;align-items:center}button{display:inline-flex;align-items:center;justify-content:center;gap:7px;border:1px solid #cbd5e1;border-radius:9px;padding:8px 11px;background:#fff}.export-body{display:grid;gap:14px;padding:18px}.notice{display:flex;gap:8px;align-items:center;margin:0;padding:10px;border-radius:9px;background:#fff7ed;color:#9a3412}.notice.error{background:#fff1f2;color:#be123c}.snapshot{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0}.snapshot>div{padding:10px;background:#f8fafc;border-radius:9px}.snapshot dt{font-size:11px;color:#64748b}.snapshot dd{margin:4px 0 0;font-size:12px;font-weight:650;overflow-wrap:anywhere}fieldset{display:grid;gap:9px;margin:0;padding:12px;border:1px solid #dbe4ea;border-radius:11px}legend{padding:0 6px;font-size:12px;font-weight:700}fieldset label{display:flex;align-items:flex-start;gap:9px;padding:11px;border:1px solid #dbe4ea;border-radius:9px;cursor:pointer}fieldset label:has(input:checked){border-color:#0f766e;background:#f0fdfa}fieldset label.disabled{opacity:.55;cursor:not-allowed}fieldset span{display:grid;gap:3px}fieldset small,fieldset em{font-size:11px;color:#64748b;font-style:normal}.security{display:flex;gap:8px;margin:0;padding:10px;background:#eff6ff;color:#1e40af;border-radius:9px;font-size:12px}.export-primary{background:#0f766e;color:#fff;border-color:#0f766e}.export-primary:disabled{opacity:.5}.export-result{display:flex;gap:9px;padding:11px;background:#f0fdf4;color:#166534;border-radius:9px}.export-result p{margin:3px 0;font-size:12px}.export-result small{overflow-wrap:anywhere}@media(max-width:620px){.snapshot{grid-template-columns:1fr}}
</style>
