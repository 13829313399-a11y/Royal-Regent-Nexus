<script setup lang="ts">
import { computed, ref, onBeforeUnmount, watch } from 'vue'
import type { InternalQuote } from '@/types/internalQuoteDesk'
import { useAuthStore } from '@/stores/auth'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import { moldingMaterialReferences, moldingMachineReferences } from '@/lib/internalQuoteMoldingReferences'
import { quotePaperPrices, paperRowsError, type QuotePaperPrice } from '@/lib/internalQuotePaper'
import { registerQuoteNavigationGuard } from '@/features/internal-quote/navigationGuard'
import InternalQuotePaperPriceEditor from './InternalQuotePaperPriceEditor.vue'
const props = defineProps<{ quote: InternalQuote; hasUnsavedChanges?: boolean; readOnly?: boolean }>()
const emit = defineEmits<{ saved: [] }>()
const auth = useAuthStore(), store = useInternalQuoteDeskStore()
const materials = computed(() => moldingMaterialReferences(props.quote.referenceSnapshot))
const machines = computed(() => moldingMachineReferences(props.quote.referenceSnapshot))
const papers = computed(() => quotePaperPrices(props.quote.referenceSnapshot))
const sales = computed(() => props.quote.sections.find(s => s.code === 'sales')?.payload ?? {})
const canEdit = computed(() => !props.readOnly && !store.submitting && !store.detailLoading && !store.refreshWarning && !props.quote.versionArchived && !props.quote.documentArchive
  && !['final_pending','released','exported','archived'].includes(props.quote.status)
  && (auth.can('internal_quote:sales_edit', props.quote.factoryId, 'sales-business') || auth.can('internal_quote:engineering_edit', props.quote.factoryId, 'engineering')))
const editing = ref(false), busy = ref(false), error = ref(''), notice = ref('')
const paperDraft = ref<QuotePaperPrice[]>([])
let revision = 0, initial = ''
const dirty = computed(() => editing.value && JSON.stringify(paperDraft.value) !== initial)
function start() { if (!canEdit.value || props.hasUnsavedChanges) return; paperDraft.value = papers.value.map(p => ({ ...p })); initial = JSON.stringify(paperDraft.value); revision = props.quote.headerRevision; editing.value = true; error.value = ''; notice.value = '' }
function cancel() { if (busy.value) return; if (dirty.value && !window.confirm('放弃未保存的纸材修改？')) return; editing.value = false }
async function save() {
  if (!canEdit.value || busy.value || props.hasUnsavedChanges) return
  error.value = paperRowsError(paperDraft.value); if (error.value) return
  busy.value = true
  try {
    await store.updateReferenceMaterials(props.quote.id, revision, Object.entries(props.quote.referenceSnapshot.material_prices as Record<string, unknown> ?? {}).map(([key, price]) => ({ material: key.slice(0, key.indexOf('|')), grade: key.slice(key.indexOf('|') + 1), price_hkd_lb: String(price) })), paperDraft.value.map(p => ({ ...p, name: p.name.trim(), remark: p.remark.trim() })))
    editing.value = false
    notice.value = store.refreshWarningQuoteId === props.quote.id && store.refreshWarning ? '纸材已保存，但页面读取未完成，请重新读取后核对金额。' : '本报价纸材价目已保存，并已重新核算相关部门。'
    emit('saved')
  } catch (e) { error.value = e instanceof Error ? e.message : '保存失败，请重新读取后核对' }
  finally { busy.value = false }
}
const unregister = registerQuoteNavigationGuard(() => !busy.value && (!dirty.value || window.confirm('纸材价目尚未保存，是否放弃修改并离开？')))
function unload(e: BeforeUnloadEvent) { if (dirty.value || busy.value) { e.preventDefault(); e.returnValue = '' } }
window.addEventListener('beforeunload', unload)
onBeforeUnmount(() => { unregister(); window.removeEventListener('beforeunload', unload) })
watch(() => props.quote.id, () => { editing.value = false; error.value = ''; notice.value = '' })
</script>
<template>
  <details class="quote-price-basis">
    <summary>本报价采用价目表 <small>{{ quote.factoryName }} · {{ quote.versionLabel }}</small></summary>
    <p>以下是本款已保存采用的价格。基础价目后续调整不会自动覆盖本款；本款专用料价以此处当前值为准。</p>
    <p class="basis-meta">基础价目版本 {{ quote.referenceSnapshot.pricing_baseline_revision ?? '未记录' }} · 损耗 {{ quote.referenceSnapshot.injection_loss_rate_percent ?? '—' }}% · RMB/HKD {{ quote.fxRmbHkd }} · HKD/USD {{ quote.fxHkdUsd }}</p>
    <div class="basis-grid">
      <section><h3>材料价 · HKD/lb</h3><div class="basis-scroll"><table><thead><tr><th>材质</th><th>具体料型</th><th>单价</th></tr></thead><tbody><tr v-for="p in materials" :key="`${p.material}|${p.grade}`"><td>{{ p.material }}</td><td>{{ p.grade }}</td><td>{{ p.priceHkdLb }}</td></tr><tr v-if="!materials.length"><td colspan="3">暂无材料价</td></tr></tbody></table></div></section>
      <section><h3>机型价 · HKD/班</h3><div class="basis-scroll"><table><thead><tr><th>机型范围</th><th>机型</th><th>台班价</th></tr></thead><tbody><tr v-for="p in machines" :key="p.range"><td>{{ p.range }}</td><td>{{ p.machine }}</td><td>{{ p.shiftPriceHkd }}</td></tr><tr v-if="!machines.length"><td colspan="3">暂无机型价</td></tr></tbody></table></div></section>
    </div>
    <section class="basis-paper"><h3>纸材价目 · HKD 系数</h3>
      <p>未选纸材时沿用本单系数：主箱 {{ sales.paper_price_factor ?? quote.referenceSnapshot.paper_price_factor ?? 2.75 }}；内箱 {{ sales.inner_paper_price_factor ?? sales.paper_price_factor ?? 2.75 }}；平卡 {{ sales.flat_card_price_factor ?? sales.paper_price_factor ?? 2.75 }}。各箱、平卡选择纸材后采用目录中对应系数。</p>
      <InternalQuotePaperPriceEditor v-if="editing" v-model="paperDraft" :disabled="busy" />
      <div v-else class="basis-scroll"><table><thead><tr><th>纸材</th><th>系数 HKD</th><th>来源／适用说明</th></tr></thead><tbody><tr v-for="p in papers" :key="p.key"><td>{{ p.name }}</td><td>{{ p.price_factor_hkd }}</td><td>{{ p.remark || '未填写' }}</td></tr><tr v-if="!papers.length"><td colspan="3">尚未配置纸材目录，请按本厂已确认的报价维护。</td></tr></tbody></table></div>
      <p v-if="hasUnsavedChanges && canEdit" class="basis-warning">请先保存页面上的报价修改，再维护纸材价目。</p>
      <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
      <div v-if="canEdit" class="basis-actions"><template v-if="editing"><button type="button" :disabled="busy" @click="cancel">取消</button><button type="button" :disabled="busy || hasUnsavedChanges" @click="save">{{ busy ? '保存重算中…' : '保存本款纸材并重算' }}</button></template><button v-else type="button" :disabled="hasUnsavedChanges" @click="start">维护本报价纸材</button></div>
    </section>
  </details>
</template>
<style scoped>
.quote-price-basis { padding:16px; border:1px solid var(--border); border-radius:14px; background:var(--card); margin:12px 0; }
summary { cursor:pointer; color:var(--primary); font-weight:700; } summary small { margin-left:10px; font-weight:400; }
p { margin:10px 0; color:var(--muted-foreground); font-size:13px; } .basis-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; } h3 { font-size:14px; font-weight:700; margin:12px 0; }
.basis-scroll { max-height:300px; overflow:auto; } table { width:100%; border-collapse:collapse; } th,td { padding:8px 10px; border-bottom:1px solid var(--border); text-align:left; font-size:13px; } th { position:sticky; top:0; background:var(--secondary); }
.basis-actions { display:flex; gap:8px; margin-top:12px; } button { border:1px solid var(--border); border-radius:7px; padding:8px 12px; color:var(--primary); } button:disabled { opacity:.5; } [role=alert] { color:var(--destructive); }
@media(max-width:768px) { .basis-grid { grid-template-columns:1fr; } }
</style>
