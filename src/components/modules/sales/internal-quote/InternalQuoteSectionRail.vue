<script setup lang="ts">
import { Check, Circle, Clock3, LockKeyhole, TriangleAlert } from '@lucide/vue'
import { getInternalQuoteFormBlocks, internalQuoteBlockRequirementLabels, internalQuoteBlockStatusLabels, type InternalQuoteFormBlock } from '@/lib/internalQuoteBlockProgress'
import { normalizeInternalQuotePayload } from '@/lib/internalQuoteSectionPayload'
import type { InternalQuoteSection, InternalQuoteSectionCode, InternalQuoteSectionStatus } from '@/types/internalQuoteDesk'

const props = withDefaults(defineProps<{
  sections: InternalQuoteSection[]
  activeCode: InternalQuoteSectionCode
  wholeQuoteReview?: boolean
  blockProgress?: Partial<Record<InternalQuoteSectionCode, InternalQuoteFormBlock[]>>
  differentSectionCodes?: InternalQuoteSectionCode[]
}>(), {
  wholeQuoteReview: false,
  differentSectionCodes: () => [],
})

const emit = defineEmits<{
  select: [code: InternalQuoteSectionCode]
  'select-page': [anchor: 'overview' | 'actions']
}>()

const statusLabel: Record<InternalQuoteSectionStatus, string> = {
  draft: '草稿',
  pending_review: '待审核',
  approved: '已通过',
  rejected: '已退回',
  na_pending: '不适用待审',
  not_applicable: '不适用',
}

type SectionProgressState = 'empty' | 'in_progress' | 'completed' | 'issue'

function sectionProgress(section: InternalQuoteSection): SectionProgressState {
  if (section.status === 'rejected' || section.dependencyStatus === 'stale' || section.warnings.length) return 'issue'
  if (section.filledAt && section.calculationStatus === 'valid' && section.dependencyStatus === 'current') return 'completed'
  if (section.filledAt || Object.keys(section.payload).length) return 'in_progress'
  return 'empty'
}

function sectionProgressLabel(section: InternalQuoteSection) {
  return {
    empty: '未填写',
    in_progress: '填写中',
    completed: '已完成',
    issue: '需处理',
  }[sectionProgress(section)]
}

function statusIcon(section: InternalQuoteSection) {
  if (props.wholeQuoteReview) {
    const progress = sectionProgress(section)
    if (progress === 'completed') return Check
    if (progress === 'in_progress') return Clock3
    if (progress === 'issue') return TriangleAlert
    return Circle
  }
  const status = section.status
  if (status === 'approved' || status === 'not_applicable') return Check
  if (status === 'pending_review' || status === 'na_pending') return Clock3
  if (status === 'rejected') return TriangleAlert
  return Circle
}

function sectionBlocks(section: InternalQuoteSection) {
  return props.blockProgress?.[section.code]
    ?? getInternalQuoteFormBlocks(section.code, normalizeInternalQuotePayload(section.code, section.payload))
}

function blockIsReady(block: InternalQuoteFormBlock) {
  return ['complete', 'automatic', 'optional'].includes(block.status)
}

function readyBlockCount(section: InternalQuoteSection) {
  return sectionBlocks(section).filter(blockIsReady).length
}
</script>

<template>
  <aside class="quote-section-rail" :class="{ 'whole-review': wholeQuoteReview }" :aria-label="wholeQuoteReview ? '报价页面导航' : '责任分段'">
    <header>
      <div><strong>{{ wholeQuoteReview ? '页面导航' : '责任分段' }}</strong><span>{{ wholeQuoteReview ? '悬停部门查看填写状态' : '已参与部门协作进度' }}</span></div>
      <span class="quote-rail-count">{{ wholeQuoteReview ? sections.filter((section) => sectionProgress(section) === 'completed').length : sections.filter((section) => ['approved', 'not_applicable'].includes(section.status)).length }}/{{ sections.length }}</span>
    </header>
    <nav>
      <button v-if="wholeQuoteReview" type="button" class="quote-page-anchor-button" @click="emit('select-page', 'overview')">
        <span class="quote-section-index quote-page-anchor-index">顶</span>
        <span class="quote-section-name"><strong>报价概览</strong><small>产品资料与整单进度</small></span>
        <Circle class="quote-section-status-icon" aria-hidden="true" />
      </button>
      <div
        v-for="section in sections"
        :key="section.code"
        class="quote-section-entry"
      >
        <button
          type="button"
          :class="[wholeQuoteReview ? sectionProgress(section) : section.status, { active: section.code === activeCode, 'baseline-different': differentSectionCodes.includes(section.code) }]"
          @click="emit('select', section.code)"
        >
          <span class="quote-section-index">{{ String(sections.indexOf(section) + 1).padStart(2, '0') }}</span>
          <span class="quote-section-name"><strong>{{ section.label }}<em v-if="differentSectionCodes.includes(section.code)">与基准款不同</em></strong><small>{{ wholeQuoteReview ? sectionProgressLabel(section) : statusLabel[section.status] }} · {{ readyBlockCount(section) }}/{{ sectionBlocks(section).length }} 项就绪 · r{{ section.revision }}</small></span>
          <component :is="statusIcon(section)" class="quote-section-status-icon" aria-hidden="true" />
          <LockKeyhole v-if="!wholeQuoteReview && ['pending_review', 'approved', 'na_pending', 'not_applicable'].includes(section.status)" class="quote-section-lock" aria-hidden="true" />
        </button>
        <div class="quote-section-block-progress" role="status">
          <span class="quote-section-block-progress-title">{{ section.label }}填写状态</span>
          <ul>
            <li v-for="block in sectionBlocks(section)" :key="block.id" :class="`status-${block.status}`" :title="block.criteria">
              <i aria-hidden="true" />
              <strong>{{ block.title }}</strong>
              <em>{{ internalQuoteBlockRequirementLabels[block.requirement] }} · {{ internalQuoteBlockStatusLabels[block.status] }}</em>
            </li>
          </ul>
        </div>
      </div>
      <button v-if="wholeQuoteReview" type="button" class="quote-page-anchor-button" @click="emit('select-page', 'actions')">
        <span class="quote-section-index quote-page-anchor-index">底</span>
        <span class="quote-section-name"><strong>整单操作</strong><small>保存、提交与审核</small></span>
        <Circle class="quote-section-status-icon" aria-hidden="true" />
      </button>
    </nav>
    <footer>
      <template v-if="wholeQuoteReview"><span><i class="approved" />已完成</span><span><i class="pending" />填写中</span><span><i class="rejected" />需处理</span></template>
      <template v-else><span><i class="approved" />已通过</span><span><i class="pending" />待审核</span><span><i class="rejected" />已退回</span></template>
    </footer>
  </aside>
</template>

<style scoped>
.quote-section-rail{position:sticky;top:82px;align-self:start;overflow:hidden;border:1px solid #dbe5ea;border-radius:13px;background:#f8fafc;box-shadow:0 12px 28px rgb(15 23 42/.05)}.quote-section-rail>header{display:flex;align-items:center;justify-content:space-between;gap:10px;border-bottom:1px solid #e2e8f0;padding:14px}.quote-section-rail>header div{display:grid}.quote-section-rail>header strong{color:#0f172a;font-size:13px}.quote-section-rail>header span:not(.quote-rail-count){margin-top:3px;color:#94a3b8;font-size:9px}.quote-rail-count{display:grid;width:34px;height:34px;place-items:center;border-radius:9px;background:#ccfbf1;color:#0f766e;font-size:10px;font-weight:900}
.quote-section-rail nav{display:grid;padding:7px}.quote-section-rail nav button{position:relative;display:grid;grid-template-columns:27px 1fr 18px;align-items:center;gap:8px;border:0;border-radius:9px;background:transparent;padding:9px;color:#64748b;text-align:left;transition:.15s}.quote-section-rail nav button:hover{background:#fff}.quote-section-rail nav button.active{background:#fff;color:#0f766e;box-shadow:0 3px 12px rgb(15 23 42/.06)}.quote-section-rail nav button.active::before{position:absolute;inset:8px auto 8px 0;width:3px;border-radius:0 3px 3px 0;background:#0d9488;content:''}.quote-section-index{display:grid;width:24px;height:24px;place-items:center;border-radius:7px;background:#e2e8f0;color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:9px;font-weight:900}.active .quote-section-index{background:#ccfbf1;color:#0f766e}.quote-section-name{display:grid;min-width:0}.quote-section-name strong{color:#334155;font-size:11px}.active .quote-section-name strong{color:#0f766e}.quote-section-name small{margin-top:2px;color:#94a3b8;font-size:9px}.quote-section-status-icon{width:15px;height:15px}.approved .quote-section-status-icon,.not_applicable .quote-section-status-icon{color:#059669}.pending_review .quote-section-status-icon,.na_pending .quote-section-status-icon{color:#d97706}.rejected .quote-section-status-icon{color:#dc2626}.quote-section-lock{position:absolute;right:7px;bottom:5px;width:9px;height:9px;color:#94a3b8}
.quote-section-entry{display:grid}.quote-section-block-progress{display:grid;max-height:0;overflow:hidden;border-radius:8px;background:#fff;opacity:0;transition:max-height .2s ease,margin .2s ease,padding .2s ease,opacity .16s ease}.quote-section-entry:hover .quote-section-block-progress,.quote-section-entry:focus-within .quote-section-block-progress{max-height:320px;margin:3px 2px 7px;padding:8px;opacity:1;box-shadow:inset 0 0 0 1px #dbe5ea}.quote-section-block-progress-title{color:#0f766e;font-size:9px;font-weight:950}.quote-section-block-progress ul{display:grid;gap:5px;margin:6px 0 0;padding:0;list-style:none}.quote-section-block-progress li{display:grid;grid-template-columns:7px minmax(0,1fr);gap:1px 6px;align-items:center}.quote-section-block-progress li i{grid-row:1/span 2;width:7px;height:7px;border-radius:999px;background:#ef4444}.quote-section-block-progress li strong{overflow:hidden;color:#334155;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.quote-section-block-progress li em{color:#94a3b8;font-size:8px;font-style:normal}.quote-section-block-progress li.status-complete i,.quote-section-block-progress li.status-automatic i{background:#10b981}.quote-section-block-progress li.status-optional i{background:#94a3b8}.quote-section-block-progress li.status-partial i{background:#f59e0b}
.quote-section-rail nav .quote-page-anchor-button{background:#ecfeff;color:#0f766e}.quote-section-rail nav .quote-page-anchor-button:hover,.quote-section-rail nav .quote-page-anchor-button:focus-visible{background:#ccfbf1;outline:none}.quote-page-anchor-index{background:#0f766e;color:#fff}.quote-page-anchor-button .quote-section-status-icon{color:#2dd4bf}
.quote-section-rail>footer{display:flex;flex-wrap:wrap;gap:9px;border-top:1px solid #e2e8f0;padding:10px 12px;color:#94a3b8;font-size:8px}.quote-section-rail>footer span{display:flex;align-items:center;gap:4px}.quote-section-rail>footer i{width:6px;height:6px;border-radius:99px}.quote-section-rail>footer i.approved{background:#059669}.quote-section-rail>footer i.pending{background:#d97706}.quote-section-rail>footer i.rejected{background:#dc2626}
.quote-section-rail.whole-review .quote-section-index{border-radius:999px}.quote-section-rail.whole-review nav button.completed .quote-section-index{background:#d1fae5;color:#047857}.quote-section-rail.whole-review nav button.in_progress .quote-section-index{background:#fef3c7;color:#b45309}.quote-section-rail.whole-review nav button.issue .quote-section-index{background:#fee2e2;color:#b91c1c}.quote-section-rail.whole-review .completed .quote-section-status-icon{color:#059669}.quote-section-rail.whole-review .in_progress .quote-section-status-icon{color:#d97706}.quote-section-rail.whole-review .issue .quote-section-status-icon{color:#dc2626}
.quote-section-rail nav button.baseline-different{box-shadow:inset 0 0 0 1px #fdba74}.quote-section-rail nav button.baseline-different .quote-section-index{background:#ffedd5;color:#c2410c}.quote-section-name strong em{display:inline-flex;margin-left:5px;border-radius:999px;background:#ffedd5;padding:2px 5px;color:#c2410c;font-size:7px;font-style:normal;vertical-align:middle}
@media(max-width:980px){.quote-section-rail{position:static;overflow:auto}.quote-section-rail>header,.quote-section-rail>footer{display:none}.quote-section-rail nav{display:flex;min-width:max-content}.quote-section-rail nav button{min-width:145px}}
</style>
