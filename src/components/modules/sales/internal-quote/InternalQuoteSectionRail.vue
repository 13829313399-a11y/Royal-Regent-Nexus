<script setup lang="ts">
import { Check, Circle, Clock3, LockKeyhole, TriangleAlert } from '@lucide/vue'
import type { InternalQuoteSection, InternalQuoteSectionCode, InternalQuoteSectionStatus } from '@/types/internalQuoteDesk'

defineProps<{
  sections: InternalQuoteSection[]
  activeCode: InternalQuoteSectionCode
}>()

const emit = defineEmits<{
  select: [code: InternalQuoteSectionCode]
}>()

const statusLabel: Record<InternalQuoteSectionStatus, string> = {
  draft: '草稿',
  pending_review: '待审核',
  approved: '已通过',
  rejected: '已退回',
  na_pending: '不适用待审',
  not_applicable: '不适用',
}

function statusIcon(status: InternalQuoteSectionStatus) {
  if (status === 'approved' || status === 'not_applicable') return Check
  if (status === 'pending_review' || status === 'na_pending') return Clock3
  if (status === 'rejected') return TriangleAlert
  return Circle
}
</script>

<template>
  <aside class="quote-section-rail" aria-label="责任分段">
    <header>
      <div><strong>责任分段</strong><span>八部门协作进度</span></div>
      <span class="quote-rail-count">{{ sections.filter((section) => ['approved', 'not_applicable'].includes(section.status)).length }}/{{ sections.length }}</span>
    </header>
    <nav>
      <button
        v-for="section in sections"
        :key="section.code"
        type="button"
        :class="[section.status, { active: section.code === activeCode }]"
        @click="emit('select', section.code)"
      >
        <span class="quote-section-index">{{ String(sections.indexOf(section) + 1).padStart(2, '0') }}</span>
        <span class="quote-section-name"><strong>{{ section.label }}</strong><small>{{ statusLabel[section.status] }} · r{{ section.revision }}</small></span>
        <component :is="statusIcon(section.status)" class="quote-section-status-icon" aria-hidden="true" />
        <LockKeyhole v-if="['pending_review', 'approved', 'na_pending', 'not_applicable'].includes(section.status)" class="quote-section-lock" aria-hidden="true" />
      </button>
    </nav>
    <footer>
      <span><i class="approved" />已通过</span>
      <span><i class="pending" />待审核</span>
      <span><i class="rejected" />已退回</span>
    </footer>
  </aside>
</template>

<style scoped>
.quote-section-rail{position:sticky;top:82px;align-self:start;overflow:hidden;border:1px solid #dbe5ea;border-radius:13px;background:#f8fafc;box-shadow:0 12px 28px rgb(15 23 42/.05)}.quote-section-rail>header{display:flex;align-items:center;justify-content:space-between;gap:10px;border-bottom:1px solid #e2e8f0;padding:14px}.quote-section-rail>header div{display:grid}.quote-section-rail>header strong{color:#0f172a;font-size:13px}.quote-section-rail>header span:not(.quote-rail-count){margin-top:3px;color:#94a3b8;font-size:9px}.quote-rail-count{display:grid;width:34px;height:34px;place-items:center;border-radius:9px;background:#ccfbf1;color:#0f766e;font-size:10px;font-weight:900}
.quote-section-rail nav{display:grid;padding:7px}.quote-section-rail nav button{position:relative;display:grid;grid-template-columns:27px 1fr 18px;align-items:center;gap:8px;border:0;border-radius:9px;background:transparent;padding:9px;color:#64748b;text-align:left;transition:.15s}.quote-section-rail nav button:hover{background:#fff}.quote-section-rail nav button.active{background:#fff;color:#0f766e;box-shadow:0 3px 12px rgb(15 23 42/.06)}.quote-section-rail nav button.active::before{position:absolute;inset:8px auto 8px 0;width:3px;border-radius:0 3px 3px 0;background:#0d9488;content:''}.quote-section-index{display:grid;width:24px;height:24px;place-items:center;border-radius:7px;background:#e2e8f0;color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:9px;font-weight:900}.active .quote-section-index{background:#ccfbf1;color:#0f766e}.quote-section-name{display:grid;min-width:0}.quote-section-name strong{color:#334155;font-size:11px}.active .quote-section-name strong{color:#0f766e}.quote-section-name small{margin-top:2px;color:#94a3b8;font-size:9px}.quote-section-status-icon{width:15px;height:15px}.approved .quote-section-status-icon,.not_applicable .quote-section-status-icon{color:#059669}.pending_review .quote-section-status-icon,.na_pending .quote-section-status-icon{color:#d97706}.rejected .quote-section-status-icon{color:#dc2626}.quote-section-lock{position:absolute;right:7px;bottom:5px;width:9px;height:9px;color:#94a3b8}
.quote-section-rail>footer{display:flex;flex-wrap:wrap;gap:9px;border-top:1px solid #e2e8f0;padding:10px 12px;color:#94a3b8;font-size:8px}.quote-section-rail>footer span{display:flex;align-items:center;gap:4px}.quote-section-rail>footer i{width:6px;height:6px;border-radius:99px}.quote-section-rail>footer i.approved{background:#059669}.quote-section-rail>footer i.pending{background:#d97706}.quote-section-rail>footer i.rejected{background:#dc2626}
@media(max-width:980px){.quote-section-rail{position:static;overflow:auto}.quote-section-rail>header,.quote-section-rail>footer{display:none}.quote-section-rail nav{display:flex;min-width:max-content}.quote-section-rail nav button{min-width:145px}}
</style>
