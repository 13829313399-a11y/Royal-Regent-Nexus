<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { casdonWorkbookApi, type CasdonWorkbookPreview, type CasdonWorkbookAction } from '@/api/casdonWorkbook'
import { getApiErrorMessageAsync } from '@/lib/http'

const props = defineProps<{ factoryId: string }>()
const file = ref<File | null>(null)
const preview = ref<CasdonWorkbookPreview | null>(null)
const busy = ref(false)
const message = ref('')
const search = ref('')
const section = ref<'active' | 'shipped'>('active')
const selected = ref<string[]>([])
const page = ref(1)
const reason = ref('')
const confirming = ref(false)
let sequence = 0
function checkedPreview(result: CasdonWorkbookPreview) {
  if (result.factory_id !== props.factoryId || result.factory_id !== 'huadeng' || result.customer_code !== 'casdon') {
    throw new Error('预览厂区或客户不一致，请重新选择排期')
  }
  return result
}
const matches = computed(() => (preview.value?.rows ?? []).filter(r => r.section === section.value
  && [r.contract, r.reference, r.product, r.customer].join(' ').toLowerCase().includes(search.value.trim().toLowerCase())))
const pages = computed(() => Math.max(1, Math.ceil(matches.value.length / 30)))
const visible = computed(() => matches.value.slice((page.value - 1) * 30, page.value * 30))
const chosen = computed(() => preview.value?.rows.filter(r => selected.value.includes(r.id)) ?? [])
watch([search, section], () => { page.value = 1; selected.value = []; confirming.value = false })
watch(() => props.factoryId, reset)
onUnmounted(() => { sequence++ })
function reset() {
  sequence++; file.value = null; preview.value = null; selected.value = []; confirming.value = false
  reason.value = ''; message.value = ''; busy.value = false; page.value = 1
}
async function choose(event: Event) {
  const next = (event.target as HTMLInputElement).files?.[0]
  reset()
  if (!next) return
  if (!/\.xlsx$/i.test(next.name) || next.size > 35 * 1024 * 1024 || !next.size) {
    message.value = '请选择不超过35MB的 .xlsx 排期'; return
  }
  file.value = next
  const token = ++sequence; busy.value = true
  try {
    const result = await casdonWorkbookApi.preview(props.factoryId, next)
    if (token === sequence) preview.value = checkedPreview(result)
  } catch (error) {
    const detail = await getApiErrorMessageAsync(error)
    if (token === sequence) message.value = detail || '预览失败，请检查文件后重试'
  } finally { if (token === sequence) busy.value = false }
}
async function generate(action: CasdonWorkbookAction) {
  if (busy.value || !preview.value || !file.value || props.factoryId !== 'huadeng') return
  if (action !== 'prepare' && (!confirming.value || !selected.value.length || selected.value.length > 200 || reason.value.trim().length < 4)) return
  const token = ++sequence; busy.value = true; message.value = ''
  try {
    const result = await casdonWorkbookApi.export(props.factoryId, file.value, preview.value.fingerprint,
      action, action === 'prepare' ? [] : [...selected.value], reason.value.trim())
    if (token !== sequence) return
    const url = URL.createObjectURL(result.blob)
    const link = document.createElement('a'); link.href = url; link.download = result.name
    document.body.appendChild(link); link.click(); link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    file.value = new File([result.blob], result.name, { type: result.blob.type })
    preview.value = null; selected.value = []; confirming.value = false; reason.value = ''; page.value = 1
    message.value = `已下载 ${result.name}。后续操作基于此副本；原文件和台账未改动。`
      + (result.warningCount ? ` ${result.warningCount}行未找到唯一价格来源，金额留空或保留原值，请核对。` : '')
      + (result.auditId ? ` 导出记录：${result.auditId}` : '')
    try {
      const latest = await casdonWorkbookApi.preview(props.factoryId, file.value)
      if (token === sequence) preview.value = checkedPreview(latest)
    } catch {
      if (token === sequence) message.value += ' 副本自动预览失败，请重新选择下载文件后继续。'
    }
  } catch (error) {
    const detail = await getApiErrorMessageAsync(error)
    if (token === sequence) message.value = detail || '整理失败，未生成新文件'
  } finally { if (token === sequence) busy.value = false }
}
</script>

<template>
  <section class="casdon-tools" aria-label="Casdon Excel整理" :aria-busy="busy">
    <h3>Casdon Excel 整理</h3>
    <p>上传统一排期，补充 ITEM 金额栏，或将选中的整条订单标记为已走货／恢复未走货。只生成 Excel 副本，不修改系统台账走货数量；部分走货请勿在这里整行归档。</p>
    <label>选择统一排期 <input type="file" accept=".xlsx" :disabled="busy" @change="choose"></label>
    <p v-if="file">当前文件：{{ file.name }}</p>
    <p v-if="busy" role="status">正在处理，请稍候…</p>
    <p v-if="message" role="status">{{ message }}</p>
    <template v-if="preview">
      <button type="button" class="casdon-tools__primary" :disabled="busy" @click="generate('prepare')">补充金额栏并下载</button>
      <div class="casdon-tools__filters">
        <label>Excel 区域 <select v-model="section" :disabled="busy || confirming"><option value="active">未走货</option><option value="shipped">已走货</option></select></label>
        <label>查找订单 <input v-model="search" type="search" placeholder="单号、完整货号或客户" :disabled="busy || confirming"></label>
      </div>
      <p>共 {{ matches.length }} 条，已选 {{ selected.length }} 条（每次最多200条）。取消单不参与整理。</p>
      <div class="casdon-tools__table" tabindex="0" role="region" aria-label="Casdon订单明细，可横向滚动"><table><thead><tr><th>选择</th><th>原行号</th><th>合同 / SO</th><th>完整货号</th><th>客户</th><th>数量</th></tr></thead>
        <tbody><tr v-for="row in visible" :key="row.id"><td><input v-model="selected" type="checkbox" :value="row.id" :aria-label="`选择第${row.row}行 ${row.product}`" :disabled="busy || confirming || (selected.length >= 200 && !selected.includes(row.id))"></td><td>{{ row.row }}</td><td>{{ row.contract }} / {{ row.reference }}</td><td>{{ row.product }}</td><td>{{ row.customer }}</td><td>{{ row.quantity }}</td></tr>
        <tr v-if="!visible.length"><td colspan="6">没有符合条件的订单</td></tr></tbody></table></div>
      <div class="casdon-tools__actions"><button :disabled="page <= 1 || busy" @click="page--">上一页</button><span>{{ page }} / {{ pages }}</span><button :disabled="page >= pages || busy" @click="page++">下一页</button>
        <button :disabled="!selected.length || busy || confirming" @click="confirming = true">{{ section === 'active' ? '标记已走货' : '恢复未走货' }}</button></div>
      <fieldset v-if="confirming" class="casdon-tools__confirm"><legend>确认{{ section === 'active' ? '移入已走货' : '恢复未走货' }} {{ chosen.length }} 条</legend>
        <p>仅整理下列 Excel 订单，不推断走货日期，不变更台账数量。</p>
        <ul><li v-for="row in chosen" :key="row.id">第{{ row.row }}行 · {{ row.reference }} · {{ row.product }} · {{ row.quantity }}件</li></ul>
        <label>操作原因（至少4字）<input v-model="reason" maxlength="500" :disabled="busy"></label>
        <div class="casdon-tools__actions"><button :disabled="busy" @click="confirming = false">取消</button><button class="casdon-tools__primary" :disabled="busy || reason.trim().length < 4" @click="generate(section === 'active' ? 'ship' : 'restore')">确认并下载副本</button></div>
      </fieldset>
    </template>
  </section>
</template>

<style scoped>
.casdon-tools { padding: 20px; border: 1px solid var(--border); border-radius: 12px; background: var(--card); color: var(--foreground); margin: 16px 0; }
.casdon-tools h3 { margin: 0 0 12px; font-size: 17px; font-weight: 600; }
.casdon-tools p { margin: 10px 0; line-height: 1.6; overflow-wrap: anywhere; }
.casdon-tools label { display: inline-flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.casdon-tools input:not([type=checkbox]), .casdon-tools select, .casdon-tools button { min-height: 40px; border: 1px solid var(--input); border-radius: 8px; padding: 8px 12px; background: var(--card); color: var(--foreground); max-width: 100%; font: inherit; }
.casdon-tools button { font-weight: 600; }
.casdon-tools .casdon-tools__primary { background: var(--primary); color: var(--primary-foreground); border-color: var(--primary); }
.casdon-tools input[type=checkbox] { accent-color: var(--primary); }
.casdon-tools button:disabled { opacity: .5; cursor: not-allowed; }
.casdon-tools :is(button, input, select, .casdon-tools__table):focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.casdon-tools__filters, .casdon-tools__actions { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 12px 0; }
.casdon-tools__table { overflow-x: auto; max-height: 420px; }
.casdon-tools table { width: 100%; border-collapse: collapse; text-align: left; }
.casdon-tools th, .casdon-tools td { padding: 8px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.casdon-tools th { background: var(--muted); color: var(--muted-foreground); position: sticky; top: 0; }
.casdon-tools__confirm { border: 1px solid var(--border); padding: 16px; border-radius: 8px; margin-top: 16px; }
.casdon-tools__confirm ul { max-height: 180px; overflow-y: auto; padding-left: 20px; margin: 12px 0; }
@media (max-width: 640px) { .casdon-tools { padding: 16px; } .casdon-tools button { min-height: 44px; } }
</style>
