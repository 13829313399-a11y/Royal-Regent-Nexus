<script setup lang="ts">
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Download,
  FileClock,
  FileSpreadsheet,
  LockKeyhole,
  Rocket,
  Ship,
} from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { ApiInternalQuoteVersionComparison } from '@/api/internalQuote'
import { useAuthStore } from '@/stores/auth'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuoteSectionStatus } from '@/types/internalQuoteDesk'

const route = useRoute()
const router = useRouter()
const quoteStore = useInternalQuoteDeskStore()
const authStore = useAuthStore()
const message = ref('')
const errorMessage = ref('')
const finalRejectOpen = ref(false)
const finalReason = ref('')
const versionBaseId = ref('')
const comparison = ref<ApiInternalQuoteVersionComparison>()
const quoteId = computed(() => String(route.params.quoteId ?? ''))
const quote = computed(() => quoteStore.getQuoteById(quoteId.value) ?? quoteStore.placeholderQuote)
const totalHkd = computed(() => quote.value.factoryPriceHkd)
const missingSections = computed(() => quote.value.sections.filter((section) => !['approved', 'not_applicable'].includes(section.status)))
const allSectionsReady = computed(() => missingSections.value.length === 0)
const canOpenExport = computed(() => ['released', 'exported'].includes(quote.value.status))
const canFinalSubmit = computed(() => authStore.can('internal_quote:final_submit', quote.value.factoryId, 'sales-business'))
const canFinalApprove = computed(() => authStore.can('internal_quote:final_approve', quote.value.factoryId, 'sales-business'))
const versionCandidates = computed(() => quoteStore.versionCandidates[quote.value.id] ?? [])
const componentLabels: Record<string, string> = {
  molding_hkd: '啤机', painting_hkd: '喷油', electronic_hkd: '电子', hardware_hkd: '五金', auxiliary_hkd: '辅料',
  packaging_material_hkd: '包装材料', assembly_hkd: '组装人工', packing_labor_hkd: '包装人工', indonesia_freight_hkd: '印尼运费',
  slush_hkd: '搪胶', sewing_hkd: '车缝', carton_hkd: '纸箱',
}
const componentEntries = computed(() => Object.entries(quote.value.summaryComponents).map(([key, amount]) => ({ key, label: componentLabels[key] ?? key, amount })).filter((item) => item.amount !== 0))

const statusMeta: Record<InternalQuoteSectionStatus, { label: string; tone: string }> = {
  draft: { label: '草稿', tone: 'slate' },
  pending_review: { label: '待审核', tone: 'amber' },
  approved: { label: '已通过', tone: 'green' },
  rejected: { label: '已退回', tone: 'red' },
  na_pending: { label: '不适用待审', tone: 'amber' },
  not_applicable: { label: '不适用', tone: 'slate' },
}

async function runFinalAction() {
  message.value = ''
  errorMessage.value = ''
  try {
    if (canOpenExport.value) {
      void router.push(`/modules/sales-business/internal-quote-desk/${quote.value.id}/export`)
      return
    }
    if (quote.value.status === 'fully_approved') {
      if (!canFinalSubmit.value) throw new Error('当前账号没有最终提交权限。')
      await quoteStore.submitFinal(quote.value.id, quote.value.headerRevision)
      message.value = '已由业务经办提交最终放行，等待另一名业务主管复核。'
      return
    }
    if (quote.value.status === 'final_pending') {
      if (!canFinalApprove.value) throw new Error('当前账号没有最终放行审核权限。')
      await quoteStore.reviewFinal(quote.value.id, quote.value.headerRevision, 'approve')
      message.value = '最终放行已通过，P4 受控文件和客价交接 artifact 已由服务端生成。'
      return
    }
    throw new Error('当前报价尚未满足最终放行条件。')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败。'
  }
}

async function rejectFinal() {
  if (!finalReason.value.trim()) return
  message.value = ''
  errorMessage.value = ''
  try {
    await quoteStore.reviewFinal(quote.value.id, quote.value.headerRevision, 'reject', finalReason.value.trim())
    message.value = '最终放行已退回并留存原因。'
    finalRejectOpen.value = false
    finalReason.value = ''
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : '最终放行退回失败。' }
}

async function compareSelectedVersion() {
  if (!versionBaseId.value) return
  errorMessage.value = ''
  try { comparison.value = await quoteStore.compareVersion(quote.value.id, versionBaseId.value) }
  catch (error) { errorMessage.value = error instanceof Error ? error.message : '版本对比失败。' }
}

function finalActionLabel() {
  if (quote.value.status === 'fully_approved') return canFinalSubmit.value ? '业务提交最终放行' : '无最终提交权限'
  if (quote.value.status === 'final_pending') return canFinalApprove.value ? '另一名业务主管批准放行' : '无最终审核权限'
  if (canOpenExport.value) return '进入导出汇总'
  return '尚未满足放行条件'
}

async function loadQuote() {
  await quoteStore.loadQuote(quoteId.value)
  await quoteStore.loadVersionCandidates(quoteId.value).catch(() => [])
}

onMounted(loadQuote)
watch(quoteId, loadQuote)
</script>

<template>
  <div class="quote-summary-page">
    <nav class="quote-breadcrumb" aria-label="内部报价导航">
      <RouterLink to="/modules/sales-business/internal-quote-desk"><ArrowLeft aria-hidden="true" />报价首页</RouterLink>
      <ChevronRight aria-hidden="true" />
      <RouterLink :to="`/modules/sales-business/internal-quote-desk/${quote.id}/collaboration`">{{ quote.quoteNo }} · 协作</RouterLink>
      <ChevronRight aria-hidden="true" /><strong>汇总与放行</strong>
    </nav>

    <header class="quote-summary-head">
      <div><span class="quote-eyebrow">内部成本汇总</span><h1>汇总与最终放行</h1><p>{{ quote.quoteNo }} · {{ quote.productName }} · {{ quote.customer }} · {{ quote.versionLabel }}</p></div>
      <div class="quote-total-card"><span>整单工厂成本</span><strong>HKD {{ totalHkd.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</strong><small>RMB {{ (totalHkd * quote.fxRmbHkd).toFixed(2) }} · USD {{ (totalHkd / quote.fxHkdUsd).toFixed(2) }}</small></div>
    </header>

    <p v-if="message" class="quote-page-message success">{{ message }}</p>
    <p v-if="errorMessage" class="quote-page-message error">{{ errorMessage }}</p>
    <p v-if="quoteStore.errorMessage" class="quote-page-message error">{{ quoteStore.errorMessage }}</p>

    <section class="quote-summary-grid">
      <article class="quote-cost-table-panel">
        <header><div><CircleDollarSign aria-hidden="true" /><span><strong>责任分段成本汇总</strong><small>草稿金额可预览；最终放行只读取 approved / not_applicable revision</small></span></div><span>{{ quote.formulaVersion }}</span></header>
        <div class="quote-summary-table-scroll">
          <table>
            <thead><tr><th>责任分段</th><th>权威分段合计 HKD</th><th>计算状态</th><th>依赖状态</th><th>审批状态</th><th>revision</th></tr></thead>
            <tbody><tr v-for="section in quote.sections" :key="section.code"><td><strong>{{ section.label }}</strong><span>{{ section.owner }}</span></td><td class="money">{{ section.totalHkd.toFixed(4) }}</td><td>{{ section.calculationStatus }}</td><td>{{ section.dependencyStatus }}</td><td><span class="section-status" :class="`tone-${statusMeta[section.status].tone}`"><i />{{ statusMeta[section.status].label }}</span></td><td>r{{ section.revision }}</td></tr></tbody>
            <tfoot><tr><td>整单工厂成本</td><td class="money">{{ totalHkd.toFixed(4) }}</td><td colspan="4">参考快照已冻结</td></tr></tfoot>
          </table>
        </div>
      </article>

      <aside class="quote-distribution-panel">
        <header><strong>权威成本组件</strong><span>服务端汇总</span></header>
        <div class="quote-donut-wrap"><div class="quote-donut"><span><b>HKD</b>{{ totalHkd.toFixed(0) }}</span></div></div>
        <dl><div v-for="item in componentEntries" :key="item.key"><dt><i class="material" />{{ item.label }}</dt><dd>{{ item.amount.toFixed(4) }}</dd></div><div v-if="!componentEntries.length"><dt>尚无有效成本组件</dt><dd>0.0000</dd></div></dl>
        <section><LockKeyhole aria-hidden="true" /><div><strong>完整性基线</strong><span>{{ quote.referenceSnapshotId }}</span></div></section>
      </aside>
    </section>

    <section class="quote-logistics-panel">
      <header><div><Ship aria-hidden="true" /><span><strong>出货场景</strong><small>运费、纸箱分摊、CUFT 与减税分类按快照汇总</small></span></div><em>出货数量 {{ quote.quantity.toLocaleString('zh-CN') }} PCS</em></header>
      <div v-if="quote.shippingScenarios.length" class="quote-logistics-grid"><article v-for="scenario in quote.shippingScenarios" :key="scenario.name" class="tone-teal"><Ship aria-hidden="true" /><div><strong>{{ scenario.name }}</strong><span>{{ scenario.totalCartons.toFixed(0) }} 箱 · 运费与吊柜费按快照分摊</span></div><dl><dt>运费 + 吊柜费</dt><dd>HKD {{ (scenario.freightHkd + scenario.liftHkd).toFixed(4) }}</dd><dt>找数后成本</dt><dd>HKD {{ scenario.afterSettlementHkd.toFixed(4) }}</dd><dt>含模费总价</dt><dd>USD {{ scenario.totalUsd.toFixed(4) }}</dd></dl></article></div><p v-else class="quote-logistics-empty">业务部分段尚未保存有效出货场景。</p>
    </section>

    <section v-if="versionCandidates.length" class="quote-version-panel"><header><div><FileClock aria-hidden="true" /><span><strong>报价版本对比</strong><small>仅允许同报价或复制版本链，金额差异由服务端计算</small></span></div><div><select v-model="versionBaseId"><option value="">选择基准版本</option><option v-for="candidate in versionCandidates" :key="candidate.id" :value="candidate.id">{{ candidate.quote_no }} · {{ candidate.version_label }} · {{ candidate.updated_at }}</option></select><button type="button" :disabled="!versionBaseId" @click="compareSelectedVersion">开始对比</button></div></header><div v-if="comparison" class="quote-comparison"><article><span>基准成本</span><strong>HKD {{ Number(comparison.total_before_hkd).toFixed(4) }}</strong></article><article><span>当前成本</span><strong>HKD {{ Number(comparison.total_after_hkd).toFixed(4) }}</strong></article><article><span>金额差异</span><strong>HKD {{ Number(comparison.total_delta_hkd).toFixed(4) }}</strong></article><div><p v-for="section in comparison.sections" :key="section.section_code"><span>{{ section.section_name }} · r{{ section.before_revision }} → r{{ section.after_revision }}</span><b>{{ Number(section.delta_hkd).toFixed(4) }}</b></p></div></div></section>

    <section class="quote-release-status">
      <header><div><CheckCircle2 aria-hidden="true" /><span><strong>分段放行状态</strong><small>{{ allSectionsReady ? '八个责任分段已完成' : `还有 ${missingSections.length} 个分段未完成` }}</small></span></div><RouterLink :to="`/modules/sales-business/internal-quote-desk/${quote.id}/collaboration`">返回协作页</RouterLink></header>
      <div class="quote-release-grid"><article v-for="section in quote.sections" :key="section.code" :class="section.status"><span><Check v-if="['approved','not_applicable'].includes(section.status)" aria-hidden="true" /><AlertTriangle v-else aria-hidden="true" /></span><div><strong>{{ section.label }}</strong><small>{{ statusMeta[section.status].label }} · {{ section.reviewer ?? section.submittedBy ?? '尚未提交' }}</small></div><em>r{{ section.revision }}</em></article></div>
      <div v-if="missingSections.length" class="quote-release-warning"><AlertTriangle aria-hidden="true" /><span><strong>暂不可最终放行或导出</strong>{{ missingSections.map((section) => `${section.label}（${statusMeta[section.status].label}）`).join('、') }}</span></div>
    </section>

    <section class="quote-final-grid">
      <article class="quote-export-history"><header><FileClock aria-hidden="true" /><span><strong>受控导出记录</strong><small>重开后旧文件保留但标记已取代</small></span></header><div v-if="quote.exports.length"><p v-for="record in quote.exports" :key="record.id"><FileSpreadsheet aria-hidden="true" /><span><strong>{{ record.fileName }}</strong><small>{{ record.exportedBy }} · {{ record.exportedAt }}</small></span><em :class="record.status">{{ record.status === 'current' ? '当前版本' : '已取代' }}</em></p></div><div v-else class="empty">最终放行后才可生成受控 XLSX。</div></article>
      <article class="quote-final-release" :class="{ ready: allSectionsReady }"><Rocket aria-hidden="true" /><div><span>业务部最终放行</span><h2>{{ allSectionsReady ? (quote.status === 'final_pending' ? '等待第二名业务主管复核' : canOpenExport ? '已放行，可查看受控导出' : '整单已准备就绪') : '等待全部责任分段完成' }}</h2><p>最终提交人与最终放行人不得相同；提交和审核均携带报价头 revision，服务端冻结完整放行清单。</p><div v-if="quote.finalReleaseStatus === 'rejected'" class="final-rejected">上一轮最终放行已退回，可修正后重新提交。</div></div><div class="final-buttons"><button v-if="quote.status === 'final_pending' && canFinalApprove" type="button" class="reject" @click="finalRejectOpen = !finalRejectOpen">退回最终放行</button><button type="button" :disabled="!allSectionsReady || (quote.status === 'fully_approved' && !canFinalSubmit) || (quote.status === 'final_pending' && !canFinalApprove)" @click="runFinalAction"><Download v-if="canOpenExport" aria-hidden="true" /><Rocket v-else aria-hidden="true" />{{ finalActionLabel() }}</button></div></article>
    </section>
    <section v-if="finalRejectOpen" class="quote-final-reason"><div><strong>退回最终放行</strong><span>原因将写入不可变最终审核记录并通知提交人。</span></div><textarea v-model="finalReason" rows="2" placeholder="必须填写退回原因" /><button type="button" @click="finalRejectOpen = false">取消</button><button type="button" class="primary" :disabled="!finalReason.trim() || quoteStore.submitting" @click="rejectFinal">确认退回</button></section>
  </div>
</template>

<style scoped>
.quote-summary-page{display:grid;gap:14px;padding-bottom:32px}.quote-breadcrumb{display:flex;align-items:center;gap:7px;color:#94a3b8;font-size:9px}.quote-breadcrumb a{display:inline-flex;align-items:center;gap:5px;color:#475569;font-weight:800}.quote-breadcrumb a:hover{color:#0f766e}.quote-breadcrumb svg{width:12px}.quote-breadcrumb strong{color:#0f766e}.quote-summary-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px}.quote-eyebrow{color:#0f766e;font-size:10px;font-weight:900;letter-spacing:.08em}.quote-summary-head h1{margin:5px 0 0;color:#0f172a;font-size:30px;font-weight:950;letter-spacing:-.04em}.quote-summary-head p{margin:7px 0 0;color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:10px}.quote-total-card{display:grid;min-width:280px;border:1px solid #99f6e4;border-radius:13px;background:#f0fdfa;padding:13px 16px;text-align:right}.quote-total-card span{color:#0f766e;font-size:9px;font-weight:900}.quote-total-card strong{margin-top:5px;color:#115e59;font-size:21px}.quote-total-card small{margin-top:4px;color:#0f766e;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px}.quote-page-message{margin:0;border-radius:8px;padding:8px 11px;font-size:9px}.quote-page-message.success{border:1px solid #a7f3d0;background:#ecfdf5;color:#047857}.quote-page-message.error{border:1px solid #fecaca;background:#fef2f2;color:#b91c1c}
.quote-summary-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(250px,.7fr);gap:12px}.quote-cost-table-panel,.quote-distribution-panel,.quote-logistics-panel,.quote-release-status,.quote-export-history,.quote-final-release{overflow:hidden;border:1px solid #dbe5ea;border-radius:13px;background:#fff;box-shadow:0 10px 28px rgb(15 23 42/.045)}.quote-cost-table-panel>header,.quote-logistics-panel>header,.quote-release-status>header,.quote-export-history>header{display:flex;align-items:center;justify-content:space-between;gap:10px;border-bottom:1px solid #e2e8f0;padding:13px 15px;background:#f8fafc}.quote-cost-table-panel>header>div,.quote-logistics-panel>header>div,.quote-release-status>header>div,.quote-export-history>header{display:flex;align-items:center;gap:8px}.quote-cost-table-panel header svg,.quote-logistics-panel header svg,.quote-release-status header svg,.quote-export-history header svg{width:17px;color:#0f766e}.quote-cost-table-panel header span,.quote-logistics-panel header span,.quote-release-status header span,.quote-export-history header span{display:grid}.quote-cost-table-panel header strong,.quote-logistics-panel header strong,.quote-release-status header strong,.quote-export-history header strong{color:#334155;font-size:11px}.quote-cost-table-panel header small,.quote-logistics-panel header small,.quote-release-status header small,.quote-export-history header small{margin-top:2px;color:#94a3b8;font-size:8px}.quote-cost-table-panel>header>span{color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px}.quote-summary-table-scroll{overflow:auto}.quote-cost-table-panel table{width:100%;min-width:750px;border-collapse:collapse}.quote-cost-table-panel th{background:#eef2f6;padding:8px;color:#64748b;font-size:8px;text-align:left}.quote-cost-table-panel td{border-top:1px solid #eef2f6;padding:8px;color:#475569;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px}.quote-cost-table-panel td:first-child strong{display:block;color:#334155;font-family:'Microsoft YaHei','PingFang SC',sans-serif;font-size:9px}.quote-cost-table-panel td:first-child span{display:block;margin-top:2px;color:#94a3b8;font-family:'Microsoft YaHei','PingFang SC',sans-serif;font-size:7px}.quote-cost-table-panel .money{color:#0f172a;font-weight:900;text-align:right}.quote-cost-table-panel tfoot td{background:#f8fafc;color:#0f766e;font-weight:900}.section-status{display:inline-flex;align-items:center;gap:4px;border-radius:999px;background:color-mix(in srgb,var(--tone) 10%,white);padding:4px 6px;color:var(--tone);font-family:'Microsoft YaHei','PingFang SC',sans-serif;font-size:7px;font-weight:900}.section-status i{width:5px;height:5px;border-radius:99px;background:currentColor}.tone-slate{--tone:#64748b}.tone-amber{--tone:#d97706}.tone-green{--tone:#059669}.tone-red{--tone:#dc2626}.tone-blue{--tone:#2563eb}.tone-teal{--tone:#0f766e}
.quote-distribution-panel{padding:15px}.quote-distribution-panel>header{display:flex;justify-content:space-between}.quote-distribution-panel header strong{color:#334155;font-size:11px}.quote-distribution-panel header span{color:#94a3b8;font-size:8px}.quote-donut-wrap{display:grid;place-items:center;padding:18px 0}.quote-donut{display:grid;width:150px;height:150px;place-items:center;border-radius:50%;background:conic-gradient(#0f766e 0 64%,#475569 64% 88%,#cbd5e1 88% 100%);box-shadow:inset 0 0 0 23px #fff}.quote-donut span{display:grid;color:#0f172a;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:14px;font-weight:900;text-align:center}.quote-donut b{color:#94a3b8;font-size:8px}.quote-distribution-panel dl{display:grid;gap:7px;margin:0}.quote-distribution-panel dl div{display:flex;justify-content:space-between;gap:8px}.quote-distribution-panel dt{display:flex;align-items:center;gap:6px;color:#64748b;font-size:8px}.quote-distribution-panel dd{margin:0;color:#334155;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px}.quote-distribution-panel i{width:7px;height:7px;border-radius:99px}.quote-distribution-panel i.material{background:#0f766e}.quote-distribution-panel i.labor{background:#475569}.quote-distribution-panel i.overhead{background:#cbd5e1}.quote-distribution-panel>section{display:flex;align-items:center;gap:8px;margin-top:14px;border-radius:9px;background:#f1f5f9;padding:9px}.quote-distribution-panel section svg{width:16px;color:#64748b}.quote-distribution-panel section div{display:grid;min-width:0}.quote-distribution-panel section strong{color:#475569;font-size:8px}.quote-distribution-panel section span{overflow:hidden;margin-top:2px;color:#94a3b8;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:7px;text-overflow:ellipsis;white-space:nowrap}
.quote-logistics-panel>header em{color:#64748b;font-size:8px;font-style:normal}.quote-logistics-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;padding:12px}.quote-logistics-grid article{display:grid;grid-template-columns:32px 1fr;gap:8px;border:1px solid #e2e8f0;border-left:3px solid var(--tone);border-radius:9px;padding:11px}.quote-logistics-grid article>svg{width:20px;color:var(--tone)}.quote-logistics-grid article>div{display:grid}.quote-logistics-grid article strong{color:#334155;font-size:10px}.quote-logistics-grid article span{margin-top:2px;color:#94a3b8;font-size:7px}.quote-logistics-grid dl{grid-column:1/-1;display:grid;grid-template-columns:1fr auto;gap:5px;margin:4px 0 0;border-top:1px solid #eef2f6;padding-top:8px}.quote-logistics-grid dt{color:#64748b;font-size:8px}.quote-logistics-grid dd{margin:0;color:#334155;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px;font-weight:900}.quote-logistics-empty{margin:0;padding:22px;color:#94a3b8;font-size:11px;text-align:center}.quote-version-panel{overflow:hidden;border:1px solid #dbe5ea;border-radius:13px;background:#fff;box-shadow:0 10px 28px rgb(15 23 42/.045)}.quote-version-panel>header{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #e2e8f0;background:#f8fafc;padding:12px 14px}.quote-version-panel>header>div{display:flex;align-items:center;gap:8px}.quote-version-panel header svg{width:17px;color:#0f766e}.quote-version-panel header span{display:grid}.quote-version-panel header strong{color:#334155;font-size:11px}.quote-version-panel header small{margin-top:2px;color:#94a3b8;font-size:8px}.quote-version-panel select{height:34px;border:1px solid #dbe5ea;border-radius:7px;background:#fff;padding:0 8px;font-size:11px}.quote-version-panel button{height:34px;border:1px solid #0f766e;border-radius:7px;background:#0f766e;padding:0 10px;color:#fff;font-size:11px;font-weight:900}.quote-version-panel button:disabled{opacity:.4}.quote-comparison{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;padding:12px}.quote-comparison>article{display:grid;border:1px solid #e2e8f0;border-radius:8px;padding:10px}.quote-comparison article span{color:#64748b;font-size:10px}.quote-comparison article strong{margin-top:4px;color:#0f172a;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13px}.quote-comparison>div{grid-column:1/-1;display:grid;grid-template-columns:repeat(4,1fr);gap:6px}.quote-comparison p{display:flex;justify-content:space-between;gap:8px;margin:0;border-radius:7px;background:#f8fafc;padding:8px;color:#475569;font-size:10px}.quote-comparison p b{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
.quote-release-status>header a{color:#0f766e;font-size:8px;font-weight:900}.quote-release-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:12px}.quote-release-grid article{display:grid;grid-template-columns:28px 1fr auto;align-items:center;gap:7px;border:1px solid #e2e8f0;border-radius:9px;padding:9px}.quote-release-grid article>span{display:grid;width:26px;height:26px;place-items:center;border-radius:8px;background:#fef3c7;color:#d97706}.quote-release-grid article.approved>span,.quote-release-grid article.not_applicable>span{background:#d1fae5;color:#059669}.quote-release-grid article svg{width:13px}.quote-release-grid article div{display:grid}.quote-release-grid strong{color:#334155;font-size:9px}.quote-release-grid small{margin-top:2px;color:#94a3b8;font-size:7px}.quote-release-grid em{color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px;font-style:normal}.quote-release-warning{display:flex;align-items:flex-start;gap:8px;border-top:1px solid #fed7aa;background:#fff7ed;padding:10px 13px;color:#9a3412}.quote-release-warning svg{width:15px}.quote-release-warning span{display:grid;font-size:8px}.quote-release-warning strong{font-size:9px}
.quote-final-grid{display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.15fr);gap:12px}.quote-export-history>div{padding:12px}.quote-export-history p{display:flex;align-items:center;gap:8px;margin:0 0 7px;border:1px solid #e2e8f0;border-radius:8px;padding:8px}.quote-export-history p>svg{width:16px;color:#0f766e}.quote-export-history p>span{display:grid;min-width:0;flex:1}.quote-export-history p strong{overflow:hidden;color:#334155;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.quote-export-history p small{margin-top:2px;color:#94a3b8;font-size:7px}.quote-export-history p em{border-radius:999px;padding:3px 6px;font-size:7px;font-style:normal;font-weight:900}.quote-export-history p em.current{background:#d1fae5;color:#047857}.quote-export-history p em.superseded{background:#e2e8f0;color:#64748b}.quote-export-history .empty{color:#94a3b8;font-size:9px;text-align:center}.quote-final-release{display:grid;grid-template-columns:44px 1fr auto;align-items:center;gap:13px;border-style:dashed;padding:18px;background:#f8fafc}.quote-final-release.ready{border-color:#2dd4bf;background:#f0fdfa}.quote-final-release>svg{width:40px;color:#94a3b8}.quote-final-release.ready>svg{color:#0f766e}.quote-final-release>div>span{color:#0f766e;font-size:8px;font-weight:900}.quote-final-release h2{margin:4px 0 0;color:#0f172a;font-size:16px}.quote-final-release p{max-width:580px;margin:6px 0 0;color:#64748b;font-size:8px;line-height:1.6}.final-rejected{margin-top:7px;color:#b91c1c;font-size:10px}.final-buttons{display:flex!important;align-items:center;gap:7px}.quote-final-release button{display:inline-flex;min-height:38px;align-items:center;gap:6px;border:1px solid #0f766e;border-radius:9px;background:#0f766e;padding:0 13px;color:#fff;font-size:9px;font-weight:900}.quote-final-release button.reject{border-color:#fecaca;background:#fff;color:#dc2626}.quote-final-release button:disabled{cursor:not-allowed;border-color:#cbd5e1;background:#e2e8f0;color:#94a3b8}.quote-final-release button svg{width:14px}.quote-final-reason{display:grid;grid-template-columns:minmax(180px,1fr) minmax(260px,2fr) auto auto;align-items:center;gap:9px;border:1px solid #fecaca;border-radius:11px;background:#fef2f2;padding:11px 13px}.quote-final-reason>div{display:grid}.quote-final-reason strong{color:#991b1b;font-size:12px}.quote-final-reason span{margin-top:2px;color:#b91c1c;font-size:10px}.quote-final-reason textarea{border:1px solid #fca5a5;border-radius:7px;padding:7px 9px;font-size:13px;resize:none}.quote-final-reason button{height:33px;border:1px solid #fca5a5;border-radius:7px;background:#fff;padding:0 10px;color:#991b1b;font-size:11px;font-weight:900}.quote-final-reason button.primary{border-color:#b91c1c;background:#b91c1c;color:#fff}
@media(max-width:1000px){.quote-summary-grid,.quote-final-grid{grid-template-columns:1fr}.quote-logistics-grid{grid-template-columns:1fr}.quote-release-grid{grid-template-columns:repeat(2,1fr)}.quote-comparison>div{grid-template-columns:1fr 1fr}.quote-final-reason{grid-template-columns:1fr}}
@media(max-width:700px){.quote-summary-head,.quote-final-release{align-items:stretch;grid-template-columns:1fr}.quote-summary-head{flex-direction:column}.quote-total-card{min-width:0;text-align:left}.quote-release-grid{grid-template-columns:1fr}.quote-final-release>svg{width:32px}}
</style>
