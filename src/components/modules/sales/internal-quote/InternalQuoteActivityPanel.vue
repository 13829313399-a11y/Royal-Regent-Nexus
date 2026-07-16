<script setup lang="ts">
import { Activity, Calculator, Clock3, Eye, MessageSquare, Send, ShieldCheck, UserRound } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuote } from '@/types/internalQuoteDesk'

const props = defineProps<{ quote: InternalQuote; readOnly?: boolean }>()
const quoteStore = useInternalQuoteDeskStore()
const activeTab = ref<'summary' | 'activity' | 'views'>('summary')
const commentText = ref('')
const totalHkd = computed(() => props.quote.factoryPriceHkd)
const totalRmb = computed(() => totalHkd.value * props.quote.fxRmbHkd)
const totalUsd = computed(() => totalHkd.value / props.quote.fxHkdUsd)

function addComment() {
  if (props.readOnly) return
  quoteStore.addComment(props.quote.id, commentText.value)
  commentText.value = ''
}
</script>

<template>
  <aside class="quote-activity-panel">
    <nav class="quote-activity-tabs" aria-label="报价侧栏信息">
      <button type="button" :class="{ active: activeTab === 'summary' }" @click="activeTab = 'summary'"><Calculator aria-hidden="true" />成本</button>
      <button type="button" :class="{ active: activeTab === 'activity' }" @click="activeTab = 'activity'"><Activity aria-hidden="true" />协作</button>
      <button type="button" :class="{ active: activeTab === 'views' }" @click="activeTab = 'views'"><Eye aria-hidden="true" />浏览记录</button>
    </nav>

    <div v-if="activeTab === 'summary'" class="quote-activity-body">
      <section class="quote-live-cost">
        <span>整单成本预览</span>
        <strong>HKD {{ totalHkd.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</strong>
        <div><span>RMB {{ totalRmb.toFixed(2) }}</span><span>USD {{ totalUsd.toFixed(2) }}</span></div>
      </section>
      <section class="quote-side-section">
        <h3><ShieldCheck aria-hidden="true" />冻结参考快照</h3>
        <dl>
          <div><dt>公式版本</dt><dd>{{ quote.formulaVersion }}</dd></div>
          <div><dt>RMB → HKD</dt><dd>{{ quote.fxRmbHkd }}</dd></div>
          <div><dt>HKD → USD</dt><dd>{{ quote.fxHkdUsd }}</dd></div>
          <div><dt>快照编号</dt><dd class="hash">{{ quote.referenceSnapshotId }}</dd></div>
        </dl>
      </section>
      <section class="quote-side-section">
        <h3><Clock3 aria-hidden="true" />最近业务操作</h3>
        <ol class="quote-mini-timeline">
          <li v-for="activity in quote.activities.slice(0, 4)" :key="activity.id">
            <i /><div><strong>{{ activity.title }}</strong><span>{{ activity.actor }} · {{ activity.createdAt }}</span></div>
          </li>
        </ol>
      </section>
    </div>

    <div v-else-if="activeTab === 'activity'" class="quote-activity-body">
      <section class="quote-side-section quote-collaboration">
        <h3><MessageSquare aria-hidden="true" />协作评论</h3>
        <div class="quote-comment-list">
          <article v-for="comment in quote.comments" :key="comment.id">
            <span>{{ comment.author.slice(0, 1) }}</span>
            <div><header><strong>{{ comment.author }}</strong><small>{{ comment.department }} · {{ comment.createdAt }}</small></header><p>{{ comment.content }}</p></div>
          </article>
        </div>
        <p v-if="readOnly" class="quote-side-hint">评论接口尚未实施；请使用保存原因、退回原因和审核意见形成服务端留痕。</p>
        <form v-else class="quote-comment-form" @submit.prevent="addComment">
          <input v-model="commentText" type="text" placeholder="补充协作评论…" aria-label="协作评论">
          <button type="submit" :disabled="!commentText.trim()" aria-label="发送评论"><Send aria-hidden="true" /></button>
        </form>
      </section>
      <section class="quote-side-section">
        <h3><Activity aria-hidden="true" />业务操作时间线</h3>
        <ol class="quote-full-timeline">
          <li v-for="activity in quote.activities" :key="activity.id">
            <i /><div><strong>{{ activity.title }}</strong><p>{{ activity.detail }}</p><span>{{ activity.department }} · {{ activity.actor }} · {{ activity.createdAt }}</span></div>
          </li>
        </ol>
      </section>
    </div>

    <div v-else class="quote-activity-body">
      <section class="quote-side-section quote-view-records">
        <h3><Eye aria-hidden="true" />浏览记录</h3>
        <p class="quote-side-hint">同一用户短时间刷新会去重；浏览记录与业务操作时间线分开展示。</p>
        <article v-for="record in quote.viewRecords" :key="record.id">
          <span class="quote-view-avatar"><UserRound aria-hidden="true" /></span>
          <div><strong>{{ record.viewer }}</strong><p>{{ record.department }} · {{ record.device }}</p><small>{{ record.viewedAt }} · {{ record.ipAddress }}</small></div>
        </article>
      </section>
    </div>
  </aside>
</template>

<style scoped>
.quote-activity-panel{position:sticky;top:82px;align-self:start;overflow:hidden;border:1px solid #dbe5ea;border-radius:13px;background:#fff;box-shadow:0 12px 28px rgb(15 23 42/.05)}.quote-activity-tabs{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid #e2e8f0;background:#f8fafc;padding:6px}.quote-activity-tabs button{display:flex;align-items:center;justify-content:center;gap:4px;border:0;border-radius:8px;background:transparent;padding:8px 4px;color:#64748b;font-size:9px;font-weight:900}.quote-activity-tabs button.active{background:#fff;color:#0f766e;box-shadow:0 2px 8px rgb(15 23 42/.06)}.quote-activity-tabs svg{width:13px;height:13px}.quote-activity-body{display:grid;max-height:calc(100vh - 132px);overflow:auto}.quote-live-cost{display:grid;gap:5px;padding:18px;background:linear-gradient(145deg,#0f766e,#0d9488);color:#fff}.quote-live-cost>span{font-size:9px;font-weight:900;letter-spacing:.08em}.quote-live-cost>strong{font-size:22px;letter-spacing:-.025em}.quote-live-cost>div{display:flex;gap:12px;color:#ccfbf1;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:9px}.quote-side-section{padding:15px;border-bottom:1px solid #eef2f6}.quote-side-section h3{display:flex;align-items:center;gap:6px;margin:0 0 12px;color:#334155;font-size:10px;font-weight:900;letter-spacing:.05em}.quote-side-section h3 svg{width:14px;color:#0f766e}.quote-side-section dl{display:grid;gap:8px;margin:0}.quote-side-section dl div{display:flex;justify-content:space-between;gap:10px}.quote-side-section dt{color:#94a3b8;font-size:9px}.quote-side-section dd{margin:0;color:#334155;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:9px;text-align:right}.quote-side-section dd.hash{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.quote-mini-timeline,.quote-full-timeline{display:grid;gap:0;margin:0;padding:0;list-style:none}.quote-mini-timeline li,.quote-full-timeline li{position:relative;display:grid;grid-template-columns:12px 1fr;gap:8px;padding-bottom:13px}.quote-mini-timeline li:not(:last-child)::before,.quote-full-timeline li:not(:last-child)::before{position:absolute;top:8px;bottom:-1px;left:4px;width:1px;background:#cbd5e1;content:''}.quote-mini-timeline i,.quote-full-timeline i{z-index:1;width:9px;height:9px;margin-top:2px;border:2px solid #fff;border-radius:99px;background:#0d9488;box-shadow:0 0 0 1px #99f6e4}.quote-mini-timeline div,.quote-full-timeline div{display:grid}.quote-mini-timeline strong,.quote-full-timeline strong{color:#334155;font-size:9px}.quote-mini-timeline span,.quote-full-timeline span{margin-top:3px;color:#94a3b8;font-size:8px}.quote-full-timeline p{margin:4px 0 0;color:#64748b;font-size:9px;line-height:1.45}
.quote-comment-list{display:grid;gap:11px}.quote-comment-list article{display:flex;align-items:flex-start;gap:8px}.quote-comment-list article>span{display:grid;width:25px;height:25px;flex:0 0 auto;place-items:center;border-radius:8px;background:#ccfbf1;color:#0f766e;font-size:9px;font-weight:900}.quote-comment-list article>div{min-width:0;flex:1}.quote-comment-list header{display:flex;justify-content:space-between;gap:6px}.quote-comment-list strong{color:#334155;font-size:9px}.quote-comment-list small{color:#94a3b8;font-size:8px}.quote-comment-list p{margin:4px 0 0;border-radius:0 8px 8px 8px;background:#f1f5f9;padding:7px;color:#475569;font-size:9px;line-height:1.5}.quote-comment-form{display:flex;gap:6px;margin-top:12px}.quote-comment-form input{min-width:0;flex:1;border:1px solid #dbe5ea;border-radius:8px;padding:7px 8px;font-size:9px}.quote-comment-form button{display:grid;width:31px;height:31px;place-items:center;border:0;border-radius:8px;background:#0f766e;color:#fff}.quote-comment-form button:disabled{cursor:not-allowed;opacity:.4}.quote-comment-form svg{width:13px}.quote-side-hint{margin:-4px 0 12px;color:#94a3b8;font-size:8px;line-height:1.5}.quote-view-records article{display:flex;gap:9px;border-top:1px solid #f1f5f9;padding:11px 0}.quote-view-avatar{display:grid;width:30px;height:30px;flex:0 0 auto;place-items:center;border-radius:9px;background:#f1f5f9;color:#64748b}.quote-view-avatar svg{width:14px}.quote-view-records article div{min-width:0}.quote-view-records article strong{color:#334155;font-size:10px}.quote-view-records article p{margin:3px 0;color:#64748b;font-size:8px}.quote-view-records article small{color:#94a3b8;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px}
@media(max-width:1280px){.quote-activity-panel{position:static}.quote-activity-body{max-height:none}}
</style>
