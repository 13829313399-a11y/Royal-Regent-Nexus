<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { internalQuoteApi, type ApiInternalQuoteAlternativeFamily, type ApiAlternativeSyncRequest, type ApiAlternativeSyncPreview, type ApiInternalQuoteVersionComparison } from '@/api/internalQuote'
import type { InternalQuote } from '@/types/internalQuoteDesk'
import { getApiErrorMessage } from '@/lib/http'
import InternalQuoteComparison from './InternalQuoteComparison.vue'

const props = defineProps<{ quote: InternalQuote; family: ApiInternalQuoteAlternativeFamily; hasUnsavedChanges?: () => boolean }>()
const emit = defineEmits<{ changed: []; open: [id: string] }>()
const opened = ref(false), busy = ref(false), error = ref(''), reason = ref('')
const blocks = ref<string[]>([]), targets = ref<string[]>([]), copyDrafts = ref<string[]>([])
const options = ref<Array<{ key: string; label: string; department: string }>>([])
const preview = ref<ApiAlternativeSyncPreview>()
const confirmedRequest = ref<ApiAlternativeSyncRequest>()
const results = ref<Array<{ quote_id: string; version_label: string; changed: boolean }>>([])
const candidates = computed(() => props.family.items.filter(item => item.quote_id !== props.quote.id && !item.archived))
let generation = 0
function clearPreview() { generation++; preview.value = undefined; confirmedRequest.value = undefined }
watch([blocks, targets, copyDrafts, reason, () => props.quote.headerRevision, () => props.family.revision], clearPreview, { deep: true })
watch(() => props.quote.id, () => { clearPreview(); opened.value = false; blocks.value = []; targets.value = []; results.value = [] })
function saved() { if (props.hasUnsavedChanges?.()) throw new Error('请先保存当前报价，再预览或确认同步。') }
async function start() {
  error.value = ''; results.value = []
  try { saved(); busy.value = true; options.value = await internalQuoteApi.syncOptions(props.quote.id); opened.value = true }
  catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
async function review() {
  clearPreview(); error.value = ''; results.value = []
  const current = generation, id = props.quote.id
  try {
    saved()
    if (!blocks.value.length || !targets.value.length || !reason.value.trim()) throw new Error('请选择同步类别、目标方案，并填写说明。')
    busy.value = true
    const selected = [...targets.value]
    const quotes = await Promise.all(selected.map(target => internalQuoteApi.get(target)))
    const payload: ApiAlternativeSyncRequest = { revision: props.quote.headerRevision, family_revision: props.family.revision,
      blocks: [...blocks.value], reason: reason.value.trim(), targets: quotes.map(quote => ({ quote_id: quote.id, revision: quote.header_revision,
        create_version: quote.final_release_status === 'issued' || copyDrafts.value.includes(quote.id) })) }
    const response = await internalQuoteApi.previewAlternativeSync(id, payload)
    if (generation !== current || props.quote.id !== id) return
    confirmedRequest.value = { ...payload, preview_token: response.preview_token }; preview.value = response
  } catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
async function apply() {
  error.value = ''
  try {
    saved()
    if (!confirmedRequest.value || !preview.value) return
    busy.value = true
    const response = await internalQuoteApi.applyAlternativeSync(props.quote.id, confirmedRequest.value)
    results.value = response.targets; clearPreview(); emit('changed')
  } catch (cause) { clearPreview(); error.value = `${getApiErrorMessage(cause)}；请刷新方案核对结果，再重新预览。` }
  finally { busy.value = false }
}
function comparisonFor(target: ApiAlternativeSyncPreview['targets'][number]): ApiInternalQuoteVersionComparison {
  return { sections: target.sections, header_changes: [], total_before_hkd: '0', total_after_hkd: '0', total_delta_hkd: '0' } as unknown as ApiInternalQuoteVersionComparison
}
</script>

<template>
  <section class="sync" aria-label="批量同步资料">
    <button type="button" :disabled="busy" @click="start">批量同步到其他方案</button>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <div v-if="results.length" role="status" class="success"><strong>同步已完成</strong><p v-for="result in results" :key="result.quote_id">{{ result.version_label }}：{{ result.changed ? '已保存，请打开核对计算结果及依赖提示' : '资料相同，未修改' }} <button type="button" @click="emit('open', result.quote_id)">打开 {{ result.version_label }}</button></p></div>
    <div v-if="opened" class="sync-form">
      <h3>以当前 {{ quote.versionLabel }} 为来源</h3>
      <p>按勾选类别整体替换，目标类别中来源没有的明细会删除。先核对下方预览，再确认；未选类别、汇率、料价及报价倍率保留。</p>
      <fieldset :disabled="busy"><legend>1. 选择要同步的类别</legend><label v-for="option in options" :key="option.key"><input v-model="blocks" type="checkbox" :value="option.key">{{ option.department }} · {{ option.label }}</label><p v-if="!options.length">当前账号没有可同步的部门资料。</p></fieldset>
      <fieldset :disabled="busy"><legend>2. 选择目标方案</legend><div v-for="item in candidates" :key="item.quote_id" class="target"><label><input v-model="targets" type="checkbox" :value="item.quote_id">{{ item.scenario_name }} · {{ item.version_label }}</label><span v-if="item.status === 'exported'">已输出，自动复制新版本后同步，原版保留</span><label v-else><input v-model="copyDrafts" type="checkbox" :value="item.quote_id">先复制新版本（不勾选则更新此草稿）</label></div><p v-if="!candidates.length">暂无其他未归档方案，请先复制新方案。</p></fieldset>
      <label class="reason">3. 同步说明<input v-model="reason" :disabled="busy" maxlength="1000" placeholder="例如：产品统一改用加长螺丝" /></label>
      <div class="actions"><button type="button" :disabled="busy" @click="review">预览同步差异</button><button type="button" :disabled="busy" @click="opened = false; clearPreview()">收起</button></div>
      <div v-if="preview" class="preview"><article v-for="target in preview.targets" :key="target.quote_id"><h4>{{ target.version_label }} · {{ target.changed ? (target.create_version ? '将复制新版本并同步' : '将更新此草稿') : '资料相同，无需同步' }}</h4><InternalQuoteComparison v-if="target.changed" :base="target.before" :target="target.after" :comparison="comparisonFor(target)" :base-label="`${target.version_label} · 同步前`" target-label="同步后" preview-only /></article><p>确认后一次保存全部所选目标；任何一个目标版本冲突，整批停止并要求重新预览。</p><button type="button" :disabled="busy || !preview.targets.some(target => target.changed)" @click="apply">确认同步并保存</button></div>
    </div>
  </section>
</template>

<style scoped>
.sync{border-top:1px solid #e2e8f0;padding-top:14px;font-size:13px}.sync button{padding:8px 12px;background:white;border:1px solid #99d5cc;border-radius:7px;color:#0f766e;cursor:pointer}.sync button:disabled{opacity:.5;cursor:not-allowed}.sync-form{margin-top:12px;padding:16px;border:1px solid #cbd5e1;border-radius:10px;background:#fafcfd;display:grid;gap:14px}.sync h3,.sync h4{margin:0;font-size:14px}.sync p{margin:6px 0;color:#64748b;line-height:1.6}.sync fieldset{display:grid;gap:9px;border:1px solid #dbe5eb;border-radius:8px;padding:12px}.sync legend{font-weight:600}.sync label{display:flex;align-items:center;gap:8px}.target{display:flex;align-items:center;flex-wrap:wrap;gap:16px}.target span{font-size:12px;color:#64748b}.sync .reason{display:grid;gap:6px}.reason input{border:1px solid #cbd5e1;border-radius:6px;padding:9px;background:white}.actions{display:flex;gap:9px}.preview article{padding:14px;background:white;border:1px solid #dbe5eb;border-radius:8px;margin-bottom:12px}.error{color:#b91c1c!important}.success{padding:12px;background:#ecfdf5;color:#047857}
</style>
