<script setup lang="ts">
import {
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  Download,
  FileCheck2,
  FileSpreadsheet,
  Files,
  History,
  LockKeyhole,
  ShieldCheck,
} from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'

const route = useRoute()
const quoteStore = useInternalQuoteDeskStore()
const authStore = useAuthStore()
const quoteId = computed(() => String(route.params.quoteId ?? ''))
const quote = computed(() => quoteStore.getQuoteById(quoteId.value) ?? quoteStore.placeholderQuote)
const selectedTemplate = ref('internal-quote-p4-v2')
const confirmChecked = ref(false)
const message = ref('')
const errorMessage = ref('')
const totalHkd = computed(() => quote.value.factoryPriceHkd)
const participatingSections = computed(() => quote.value.sections.filter((section) => section.isRequired))
const eligible = computed(() => ['released', 'exported'].includes(quote.value.status))
const canExport = computed(() => authStore.can('internal_quote:export', quote.value.factoryId, 'sales-business'))
const componentLabels: Record<string, string> = { molding_hkd: '啤机', painting_hkd: '喷油', electronic_hkd: '电子', hardware_hkd: '五金', auxiliary_hkd: '辅料', packaging_material_hkd: '包装材料', assembly_hkd: '组装人工', packing_labor_hkd: '包装人工', indonesia_freight_hkd: '印尼运费', slush_hkd: '搪胶', sewing_hkd: '车缝', carton_hkd: '纸箱' }
const visibleComponents = computed(() => Object.entries(quote.value.summaryComponents).map(([key, amount]) => ({ key, label: componentLabels[key] ?? key, amount })).filter((item) => item.amount !== 0).slice(0, 3))
const workbookSheets = ['报价明细', '电子明细', '车缝明细', '装配明细', '审批与版本']

async function confirmExport() {
  message.value = ''
  errorMessage.value = ''
  try {
    if (!canExport.value) throw new Error('当前账号没有受控导出权限。')
    if (!confirmChecked.value) throw new Error('请先确认导出 revision 与最终放行版本一致。')
    const created = await quoteStore.createExport(quote.value.id)
    message.value = `受控文件已生成或复用：${(created as { file_name?: string }).file_name ?? '当前放行版本'}。`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出确认失败。'
  }
}

async function downloadRecord(id: string, fileName: string) {
  errorMessage.value = ''
  try { await quoteStore.downloadExport(quote.value.id, id, fileName) }
  catch (error) { errorMessage.value = error instanceof Error ? error.message : '下载失败。' }
}

function loadQuote() {
  void quoteStore.loadQuote(quoteId.value)
}

onMounted(loadQuote)
watch(quoteId, loadQuote)
</script>

<template>
  <div class="quote-export-page">
    <nav class="quote-breadcrumb" aria-label="内部报价导航">
      <RouterLink to="/modules/sales-business/internal-quote-desk"><ArrowLeft aria-hidden="true" />报价首页</RouterLink><ChevronRight aria-hidden="true" />
      <RouterLink :to="`/modules/sales-business/internal-quote-desk/${quote.id}/summary`">汇总与放行</RouterLink><ChevronRight aria-hidden="true" /><strong>导出汇总</strong>
    </nav>

    <header class="quote-export-head">
      <div><span>受控 XLSX</span><h1>内部报价导出汇总</h1><p>{{ quote.quoteNo }} · {{ quote.productName }} · {{ quote.customer }} · {{ quote.versionLabel }}</p></div>
      <span class="quote-export-ready" :class="{ blocked: !eligible }"><CheckCircle2 v-if="eligible" aria-hidden="true" /><LockKeyhole v-else aria-hidden="true" />{{ eligible ? '已最终放行，可导出' : '尚未最终放行' }}</span>
    </header>

    <p v-if="message" class="quote-page-message success">{{ message }}</p>
    <p v-if="errorMessage" class="quote-page-message error">{{ errorMessage }}</p>
    <p v-if="quoteStore.errorMessage" class="quote-page-message error">{{ quoteStore.errorMessage }}</p>

    <section class="quote-export-kpis"><article v-for="item in visibleComponents" :key="item.key"><span>{{ item.label }}</span><strong>HKD {{ item.amount.toFixed(4) }}</strong></article><article v-for="index in Math.max(0, 3-visibleComponents.length)" :key="`empty-${index}`"><span>权威成本组件</span><strong>HKD 0.0000</strong></article><article class="primary"><span>最终工厂成本</span><strong>HKD {{ totalHkd.toFixed(4) }}</strong></article></section>

    <section class="quote-export-grid">
      <article class="quote-export-preview">
        <header><div><FileSpreadsheet aria-hidden="true" /><span><strong>工作簿内容预览</strong><small>导出内容严格绑定最终放行时的 revision 集合与参考快照</small></span></div><em>{{ quote.formulaVersion }}</em></header>
        <div class="quote-workbook-card">
          <div class="quote-workbook-title"><span><Files aria-hidden="true" /></span><div><strong>{{ quote.quoteNo }}_{{ quote.versionLabel }}_内部报价.xlsx</strong><small>统一内部格式：Huaxing Demo · {{ selectedTemplate }}</small></div></div>
          <div class="quote-sheet-list"><span v-for="(sheet, index) in workbookSheets" :key="sheet"><b>{{ index + 1 }}</b><strong>{{ sheet }}</strong><CheckCircle2 aria-hidden="true" /></span></div>
        </div>
        <section class="quote-revision-matrix"><h2>审批 revision 矩阵</h2><div><article v-for="section in participatingSections" :key="section.code"><span><strong>{{ section.label }}</strong><small>{{ section.status === 'approved' ? section.reviewer : '不适用已批准' }}</small></span><b>r{{ section.revision }}</b><CheckCircle2 aria-hidden="true" /></article></div></section>
      </article>

      <aside class="quote-export-controls">
        <section class="quote-integrity-card"><ShieldCheck aria-hidden="true" /><div><span>完整性校验</span><strong>{{ eligible ? '放行版本一致' : '未通过' }}</strong><small>{{ quote.referenceSnapshotId }}</small></div></section>
        <label><span>导出模板（服务端固定）</span><select v-model="selectedTemplate" disabled><option value="internal-quote-p4-v2">internal-quote-p4-v2</option></select><small>P4 v2 封装实际参与分段的原始参数供客价转换预检；客户折扣、返点、对客税项仍由客户转换规则处理。</small></label>
        <section class="quote-export-checklist"><h2><FileCheck2 aria-hidden="true" />导出前检查</h2><p><CheckCircle2 aria-hidden="true" />所有参与分段均已审批或获批不适用</p><p><CheckCircle2 aria-hidden="true" />业务最终放行完成</p><p><CheckCircle2 aria-hidden="true" />参考快照与公式版本已锁定</p><p><CheckCircle2 aria-hidden="true" />无阻断级计算警告</p></section>
        <label class="quote-confirm-check"><input v-model="confirmChecked" type="checkbox"><span>确认当前分段 revision 集合与最终放行时一致</span></label>
        <button type="button" class="quote-export-button" :disabled="!eligible || !canExport || quoteStore.submitting" @click="confirmExport"><Download aria-hidden="true" />确认生成受控 XLSX</button>
        <p class="quote-backend-note">生成、复用、SHA-256、放行阶段和历史留存均由后端控制；最终放行版本不会重复产生 artifact。</p>
      </aside>
    </section>

    <section class="quote-export-history">
      <header><History aria-hidden="true" /><div><strong>历史导出文件</strong><span>重开后保留旧文件，并标记为“已取代”</span></div></header>
      <div v-if="quote.exports.length"><article v-for="record in quote.exports" :key="record.id"><FileSpreadsheet aria-hidden="true" /><span><strong>{{ record.fileName }}</strong><small>{{ record.templateName }} · {{ record.exportedBy }} · {{ record.exportedAt }}</small><code>{{ record.sha256 }}</code></span><em :class="record.status">{{ record.status === 'current' ? '当前版本' : '已取代' }}</em><button type="button" @click="downloadRecord(record.id, record.fileName)"><Download />下载</button></article></div><p v-else>尚无历史导出记录。</p>
    </section>
  </div>
</template>

<style scoped>
.quote-export-page{display:grid;gap:14px;padding-bottom:32px}.quote-breadcrumb{display:flex;align-items:center;gap:7px;color:#94a3b8;font-size:9px}.quote-breadcrumb a{display:inline-flex;align-items:center;gap:5px;color:#475569;font-weight:800}.quote-breadcrumb a:hover{color:#0f766e}.quote-breadcrumb svg{width:12px}.quote-breadcrumb strong{color:#0f766e}.quote-export-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px}.quote-export-head>div>span{color:#0f766e;font-size:10px;font-weight:900;letter-spacing:.08em}.quote-export-head h1{margin:5px 0 0;color:#0f172a;font-size:30px;font-weight:950;letter-spacing:-.04em}.quote-export-head p{margin:7px 0 0;color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:10px}.quote-export-ready{display:inline-flex;align-items:center;gap:6px;border:1px solid #a7f3d0;border-radius:999px;background:#ecfdf5;padding:8px 11px;color:#047857;font-size:9px;font-weight:900}.quote-export-ready.blocked{border-color:#fed7aa;background:#fff7ed;color:#c2410c}.quote-export-ready svg{width:15px}.quote-page-message{margin:0;border-radius:8px;padding:8px 11px;font-size:9px}.quote-page-message.success{border:1px solid #a7f3d0;background:#ecfdf5;color:#047857}.quote-page-message.error{border:1px solid #fecaca;background:#fef2f2;color:#b91c1c}
.quote-export-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}.quote-export-kpis article{display:grid;gap:5px;border:1px solid #dbe5ea;border-radius:10px;background:#fff;padding:12px}.quote-export-kpis span{color:#64748b;font-size:8px;font-weight:900}.quote-export-kpis strong{color:#334155;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px}.quote-export-kpis article.primary{border-color:#99f6e4;background:#f0fdfa}.quote-export-kpis article.primary span,.quote-export-kpis article.primary strong{color:#0f766e}
.quote-export-grid{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(280px,.65fr);gap:12px}.quote-export-preview,.quote-export-controls,.quote-export-history{overflow:hidden;border:1px solid #dbe5ea;border-radius:13px;background:#fff;box-shadow:0 12px 28px rgb(15 23 42/.05)}.quote-export-preview>header{display:flex;align-items:center;justify-content:space-between;gap:10px;border-bottom:1px solid #e2e8f0;background:#f8fafc;padding:13px 15px}.quote-export-preview>header>div{display:flex;align-items:center;gap:8px}.quote-export-preview>header svg{width:18px;color:#0f766e}.quote-export-preview>header span{display:grid}.quote-export-preview>header strong{color:#334155;font-size:11px}.quote-export-preview>header small{margin-top:2px;color:#94a3b8;font-size:8px}.quote-export-preview>header em{color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px;font-style:normal}.quote-workbook-card{display:grid;gap:14px;margin:15px;border:1px solid #cbd5e1;border-radius:12px;background:linear-gradient(145deg,#fff,#f8fafc);padding:16px}.quote-workbook-title{display:flex;align-items:center;gap:10px}.quote-workbook-title>span{display:grid;width:40px;height:40px;place-items:center;border-radius:11px;background:#dcfce7;color:#15803d}.quote-workbook-title svg{width:21px}.quote-workbook-title>div{display:grid}.quote-workbook-title strong{color:#0f172a;font-size:11px}.quote-workbook-title small{margin-top:3px;color:#64748b;font-size:8px}.quote-sheet-list{display:grid;grid-template-columns:repeat(5,1fr);gap:7px}.quote-sheet-list span{display:grid;grid-template-columns:18px 1fr 13px;align-items:center;gap:5px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;padding:8px}.quote-sheet-list b{display:grid;width:17px;height:17px;place-items:center;border-radius:5px;background:#ccfbf1;color:#0f766e;font-size:7px}.quote-sheet-list strong{color:#475569;font-size:8px}.quote-sheet-list svg{width:12px;color:#059669}.quote-revision-matrix{padding:0 15px 15px}.quote-revision-matrix h2{margin:0 0 9px;color:#334155;font-size:10px}.quote-revision-matrix>div{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}.quote-revision-matrix article{display:grid;grid-template-columns:1fr auto 14px;align-items:center;gap:5px;border:1px solid #e2e8f0;border-radius:8px;padding:8px}.quote-revision-matrix article span{display:grid;min-width:0}.quote-revision-matrix strong{color:#334155;font-size:8px}.quote-revision-matrix small{overflow:hidden;margin-top:2px;color:#94a3b8;font-size:6px;text-overflow:ellipsis;white-space:nowrap}.quote-revision-matrix b{color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px}.quote-revision-matrix svg{width:12px;color:#059669}
.quote-export-controls{display:grid;align-content:start;gap:13px;padding:15px}.quote-integrity-card{display:flex;align-items:center;gap:10px;border:1px solid #a7f3d0;border-radius:10px;background:#ecfdf5;padding:12px}.quote-integrity-card>svg{width:27px;color:#059669}.quote-integrity-card div{display:grid;min-width:0}.quote-integrity-card span{color:#047857;font-size:8px;font-weight:900}.quote-integrity-card strong{margin-top:2px;color:#065f46;font-size:12px}.quote-integrity-card small{overflow:hidden;margin-top:3px;color:#047857;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:6px;text-overflow:ellipsis;white-space:nowrap}.quote-export-controls>label:not(.quote-confirm-check){display:grid;gap:6px}.quote-export-controls label>span{color:#475569;font-size:9px;font-weight:900}.quote-export-controls select{height:36px;border:1px solid #dbe5ea;border-radius:8px;background:#fff;padding:0 9px;color:#334155;font-size:9px}.quote-export-controls label small{color:#94a3b8;font-size:7px;line-height:1.5}.quote-export-checklist{display:grid;gap:7px;border:1px solid #e2e8f0;border-radius:10px;background:#f8fafc;padding:11px}.quote-export-checklist h2{display:flex;align-items:center;gap:5px;margin:0 0 2px;color:#334155;font-size:9px}.quote-export-checklist h2 svg{width:14px;color:#0f766e}.quote-export-checklist p{display:flex;align-items:center;gap:5px;margin:0;color:#64748b;font-size:8px}.quote-export-checklist p svg{width:12px;color:#059669}.quote-confirm-check{display:flex;align-items:flex-start;gap:7px}.quote-confirm-check input{margin-top:2px}.quote-confirm-check span{color:#475569;font-size:8px!important;line-height:1.5}.quote-export-button{display:flex;min-height:40px;align-items:center;justify-content:center;gap:7px;border:1px solid #0f766e;border-radius:9px;background:#0f766e;color:#fff;font-size:9px;font-weight:900}.quote-export-button:disabled{cursor:not-allowed;border-color:#cbd5e1;background:#e2e8f0;color:#94a3b8}.quote-export-button svg{width:15px}.quote-backend-note{margin:0;border-radius:8px;background:#eff6ff;padding:8px;color:#1d4ed8;font-size:7px;line-height:1.55}
.quote-export-history>header{display:flex;align-items:center;gap:8px;border-bottom:1px solid #e2e8f0;background:#f8fafc;padding:12px 14px}.quote-export-history>header svg{width:17px;color:#0f766e}.quote-export-history>header div{display:grid}.quote-export-history>header strong{color:#334155;font-size:10px}.quote-export-history>header span{margin-top:2px;color:#94a3b8;font-size:7px}.quote-export-history>div{display:grid;gap:7px;padding:12px}.quote-export-history article{display:grid;grid-template-columns:26px 1fr auto auto;align-items:center;gap:8px;border:1px solid #e2e8f0;border-radius:8px;padding:9px}.quote-export-history article>svg{width:18px;color:#0f766e}.quote-export-history article>span{display:grid;min-width:0}.quote-export-history article strong{color:#334155;font-size:9px}.quote-export-history article small{margin-top:2px;color:#94a3b8;font-size:7px}.quote-export-history code{overflow:hidden;margin-top:3px;color:#64748b;font-size:6px;text-overflow:ellipsis;white-space:nowrap}.quote-export-history em{border-radius:999px;padding:4px 7px;font-size:7px;font-style:normal;font-weight:900}.quote-export-history em.current{background:#d1fae5;color:#047857}.quote-export-history em.superseded{background:#e2e8f0;color:#64748b}.quote-export-history article>button{display:inline-flex;align-items:center;gap:4px;border:1px solid #99f6e4;border-radius:7px;background:#f0fdfa;padding:6px 8px;color:#0f766e;font-size:10px;font-weight:900}.quote-export-history article>button svg{width:12px}.quote-export-history>p{margin:0;padding:18px;color:#94a3b8;font-size:9px;text-align:center}
@media(max-width:1050px){.quote-export-grid{grid-template-columns:1fr}.quote-sheet-list{grid-template-columns:repeat(3,1fr)}}
@media(max-width:700px){.quote-export-head{align-items:stretch;flex-direction:column}.quote-export-ready{align-self:flex-start}.quote-export-kpis{grid-template-columns:repeat(2,1fr)}.quote-sheet-list,.quote-revision-matrix>div{grid-template-columns:1fr 1fr}}
</style>
