<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { internalQuoteApi, type ApiInternalQuoteAlternativeFamily, type ApiInternalQuoteVersionComparison, type ApiInternalQuote } from '@/api/internalQuote'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import InternalQuoteComparison from './InternalQuoteComparison.vue'
import InternalQuoteAlternativeSync from './InternalQuoteAlternativeSync.vue'
import type { InternalQuote } from '@/types/internalQuoteDesk'

const props = defineProps<{ quote: InternalQuote; hasUnsavedChanges?: () => boolean }>()
const emit = defineEmits<{ open: [quoteId: string]; changed: [] }>()
const auth = useAuthStore()
const family = ref<ApiInternalQuoteAlternativeFamily>()
const error = ref('')
const message = ref('')
const busy = ref(false)
const showArchived = ref(false)
const kind = ref<'scenario' | 'version'>('scenario')
const copyOpen = ref(false)
const deleteId = ref('')
const name = ref('')
const note = ref('')
const selectionReason = ref('')
const baseId = ref('')
const targetId = ref('')
const comparison = ref<ApiInternalQuoteVersionComparison>()
const comparedBase = ref<ApiInternalQuote>()
const comparedTarget = ref<ApiInternalQuote>()
const canClone = computed(() => ['sales-business', 'engineering'].some(department =>
  auth.can('internal_quote:clone', props.quote.factoryId, department) && auth.can('internal_quote:create', props.quote.factoryId, department)))
const canManage = computed(() => auth.can('internal_quote:sales_edit', props.quote.factoryId, 'sales-business'))
const current = computed(() => family.value?.items.find(item => item.quote_id === props.quote.id))
const groups = computed(() => {
  const rows = (family.value?.items ?? []).filter(item => showArchived.value || !item.archived)
  const ids = [...new Set(rows.map(item => item.scenario_id))]
  return ids.map(id => ({ id, name: rows.find(item => item.scenario_id === id)?.scenario_name, versions: rows.filter(item => item.scenario_id === id).sort((a, b) => b.version_number - a.version_number) }))
})
const isIssued = (status: string) => ['released', 'exported'].includes(status)
const label = (id: string) => {
  const row = family.value?.items.find(item => item.quote_id === id)
  return row ? `${row.scenario_name} · ${row.version_label}` : id
}
function ensureSaved() {
  if (props.hasUnsavedChanges?.()) throw new Error('当前页面还有未保存的内容，请先保存当前款，再复制、切换或对比方案。')
}
async function load() {
  const id = props.quote.id
  family.value = undefined
  comparison.value = undefined
  error.value = ''
  if (!id) return
  try {
    const result = await internalQuoteApi.listAlternatives(id)
    if (id !== props.quote.id) return
    family.value = result
    targetId.value = id
    baseId.value = result.items.find(item => item.quote_id !== id)?.quote_id ?? ''
  } catch (cause) { if (id === props.quote.id) error.value = getApiErrorMessage(cause) }
}
watch(() => props.quote.id, load, { immediate: true })
watch(() => props.quote.headerRevision, () => { void load() })
watch([baseId, targetId], () => { comparison.value = undefined })
async function refreshAfterSync() {
  const id = props.quote.id
  try {
    const latest = await internalQuoteApi.listAlternatives(id)
    if (props.quote.id === id) family.value = latest
  } catch (cause) { error.value = `同步已保存，方案列表读取失败：${getApiErrorMessage(cause)}` }
}
async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  error.value = ''; message.value = ''
  try { await action() } catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
function startCopy(nextKind: 'scenario' | 'version') {
  error.value = ''
  try { ensureSaved() } catch (cause) { error.value = (cause as Error).message; return }
  kind.value = nextKind; copyOpen.value = true; name.value = ''; note.value = ''
}
async function copy() {
  await run(async () => {
    ensureSaved()
    if (!family.value || !canClone.value) return
    if (kind.value === 'scenario' && !name.value.trim()) throw new Error('请填写方案名称，例如开窗盒包装。')
    const created = await internalQuoteApi.createAlternative(props.quote.id, {
      revision: props.quote.headerRevision, family_revision: family.value.revision, kind: kind.value,
      name: kind.value === 'scenario' ? name.value.trim() : current.value?.scenario_name ?? '', change_note: note.value.trim(),
    })
    copyOpen.value = false
    emit('open', created.id)
  })
}
function open(id: string) {
  try { ensureSaved(); emit('open', id) } catch (cause) { error.value = (cause as Error).message }
}
async function select(id: string) {
  await run(async () => {
    if (!family.value || !canManage.value) return
    if (!selectionReason.value.trim()) throw new Error('请填写客户采用或改选的说明。')
    family.value = await internalQuoteApi.selectAlternative(props.quote.id, { family_revision: family.value.revision, selected_quote_id: id, reason: selectionReason.value.trim() })
    selectionReason.value = ''; message.value = id ? `已记录客户采用：${label(id)}` : '已清除客户采用标记，历史记录保留。'
  })
}
async function reported() {
  await run(async () => {
    if (!canManage.value) return
    family.value = await internalQuoteApi.markReported(props.quote.id, props.quote.headerRevision)
    message.value = '已记录此方案版本实际报客日期。'; emit('changed')
  })
}
async function archive(id: string, archived: boolean) {
  await run(async () => {
    if (!family.value || !canManage.value) return
    if (!selectionReason.value.trim()) throw new Error('请先填写归档或恢复说明。')
    family.value = await internalQuoteApi.archiveAlternative(id, { family_revision: family.value.revision, archived, reason: selectionReason.value.trim() })
    selectionReason.value = ''; message.value = archived ? '此版本已归档，历史资料保留。' : '此版本已恢复显示。'
  })
}
async function removeDraft(id: string) {
  await run(async () => {
    ensureSaved()
    if (!family.value || !family.value.items.find(item => item.quote_id === id)?.can_delete) return
    const fallback = family.value.family_id
    const target = await internalQuoteApi.get(id)
    await internalQuoteApi.deleteQuote(id, target.header_revision)
    deleteId.value = ''
    family.value = await internalQuoteApi.listAlternatives(fallback)
    message.value = '未使用草稿已删除。'
    if (props.quote.id === id) emit('open', fallback)
    else emit('changed')
  })
}

async function compare() {
  await run(async () => {
    ensureSaved()
    if (!baseId.value || !targetId.value || baseId.value === targetId.value) throw new Error('请选择两个不同的方案版本。')
    const base = baseId.value, target = targetId.value
    const quoteId = props.quote.id
    comparison.value = undefined
    const [result, baseQuote, targetQuote] = await Promise.all([
      internalQuoteApi.compareVersion(target, base), internalQuoteApi.get(base), internalQuoteApi.get(target),
    ])
    if (props.quote.id === quoteId && baseId.value === base && targetId.value === target) {
      comparedBase.value = baseQuote; comparedTarget.value = targetQuote; comparison.value = result
    }
  })
}
</script>

<template>
  <section class="alternatives" aria-label="包装方案与版本">
    <header><div><h2>包装方案与版本</h2><p>不同包装或结构建立不同方案；同一方案的后续修改复制新版本。在本报价单内切换和编辑，各份独立保存，已输出版本保留原样。</p></div><div class="actions"><button v-if="canClone" :disabled="busy || !family" @click="startCopy('scenario')">复制为新方案</button><button v-if="canClone" :disabled="busy || !family" @click="startCopy('version')">复制新版本</button><button :disabled="busy" @click="load">刷新方案</button></div></header>
    <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="message" role="status" class="success">{{ message }}</p>
    <form v-if="copyOpen" class="copy-form" @submit.prevent="copy"><strong>{{ kind === 'scenario' ? '在本报价单中复制新方案' : '从当前版本复制后续版本' }}</strong><label v-if="kind === 'scenario'">方案名称<input v-model="name" maxlength="120" placeholder="例如：开窗盒包装" required></label><label>修改说明<input v-model="note" maxlength="1000" placeholder="例如：客户要求调整包装尺寸"></label><p>复制当前产品的完整资料、图片、模具及参考价格；新方案或版本仍归入本报价单，可继续切换其他产品。</p><div class="actions"><button type="submit" :disabled="busy">确认复制</button><button type="button" :disabled="busy" @click="copyOpen = false">取消</button></div></form>
    <div v-if="family" class="cards"><article v-for="group in groups" :key="group.id"><h3>{{ group.name }}</h3><div v-for="(item, index) in group.versions" :key="item.quote_id" class="version" :class="{ current: item.quote_id === quote.id, chosen: family.selected_quote_id === item.quote_id }"><details :open="index === 0 || item.quote_id === quote.id || family.selected_quote_id === item.quote_id"><summary><b>{{ item.version_label }}</b><span>{{ item.archived ? '已归档' : isIssued(item.status) ? '已输出' : '草稿 / 历史流程' }}</span><em v-if="family.selected_quote_id === item.quote_id">客户采用</em><small v-if="item.quote_id === quote.id">当前打开</small></summary><p>{{ item.change_note || '无修改说明' }}</p><p>{{ item.reported_at ? `已报客：${item.reported_at}` : '尚未标记实际报客' }}</p><div class="actions"><button :disabled="busy || item.quote_id === quote.id" @click="open(item.quote_id)">打开</button><button v-if="canManage && isIssued(item.status) && !item.archived && family.selected_quote_id !== item.quote_id" :disabled="busy" @click="select(item.quote_id)">客户采用此版</button><button v-if="canManage && family.selected_quote_id !== item.quote_id" :disabled="busy" @click="archive(item.quote_id, !item.archived)">{{ item.archived ? '恢复显示' : '归档此版' }}</button><button v-if="item.can_delete && item.quote_id !== family.family_id" :disabled="busy" @click="deleteId = item.quote_id">删除未使用草稿</button></div><div v-if="deleteId === item.quote_id" class="draft-delete" role="alert"><p>确认删除此草稿及其资料？删除后无法恢复。</p><button :disabled="busy" @click="removeDraft(item.quote_id)">确认删除草稿</button><button :disabled="busy" @click="deleteId = ''">取消</button></div><p v-else-if="item.delete_block_reason" class="delete-reason">{{ item.delete_block_reason }}</p></details></div></article></div>
    <div v-if="family" class="management"><label><input v-model="showArchived" type="checkbox">显示已归档版本</label><template v-if="canManage"><label class="reason">采用 / 改选 / 归档说明<input v-model="selectionReason" maxlength="1000" placeholder="例如：客户确认采用开窗盒 V2"></label><button v-if="family.selected_quote_id" :disabled="busy" @click="select('')">清除采用标记</button><button v-if="current && isIssued(current.status) && !current.reported_at && !current.archived" :disabled="busy" @click="reported">标记当前版已报客</button></template></div>
    <InternalQuoteAlternativeSync v-if="family && family.items.length > 1" :quote="quote" :family="family" :has-unsaved-changes="hasUnsavedChanges" @changed="refreshAfterSync" @open="open" />
    <div v-if="family && family.items.length > 1" class="compare"><h3>任选两版对比</h3><div class="actions"><select v-model="baseId" aria-label="比较基准版本"><option value="">选择基准版本</option><option v-for="item in family.items" :key="item.quote_id" :value="item.quote_id">{{ label(item.quote_id) }}</option></select><select v-model="targetId" aria-label="比较目标版本"><option v-for="item in family.items" :key="item.quote_id" :value="item.quote_id">{{ label(item.quote_id) }}</option></select><button :disabled="busy || !baseId || baseId === targetId" @click="compare">比较两版</button></div><InternalQuoteComparison v-if="comparison && comparedBase && comparedTarget" :comparison="comparison" :base="comparedBase" :target="comparedTarget" :base-label="label(baseId)" :target-label="label(targetId)" /></div>
  </section>
</template>

<style scoped>
.alternatives{border:1px solid #99f6e4;border-radius:14px;background:#fff;padding:18px;display:grid;gap:14px;color:#334155}.alternatives header{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}.alternatives h2{margin:0;font-size:17px;color:#134e4a}.alternatives h3{font-size:14px;margin:0 0 10px}.alternatives p{font-size:12px;line-height:1.6;margin:6px 0}.actions,.management{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.alternatives button,.alternatives input:not([type=checkbox]),.alternatives select{border:1px solid #cbd5e1;border-radius:7px;background:white;padding:8px 10px;font-size:12px;color:#334155}.alternatives button{border-color:#99d5cc;color:#0f766e}.alternatives button:disabled{opacity:.45;cursor:not-allowed}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}.cards article{border:1px solid #e2e8f0;border-radius:10px;padding:12px;background:#f8fafc}.version{padding:8px;margin-top:7px;background:white;border:1px solid #e2e8f0;border-radius:8px}.version.current{border-color:#14b8a6}.version.chosen{background:#ecfdf5}.version summary{cursor:pointer;font-size:12px}.version summary>*{margin-right:7px}.version em{color:#047857;font-style:normal}.copy-form{display:grid;gap:10px;background:#f0fdfa;padding:14px;border-radius:9px}.copy-form label,.reason{display:grid;gap:5px;font-size:12px}.reason{flex:1;min-width:240px}.management{font-size:12px}.error{color:#b91c1c;background:#fef2f2;padding:10px}.success{color:#047857;background:#ecfdf5;padding:10px}.compare{border-top:1px solid #e2e8f0;padding-top:14px}
</style>
