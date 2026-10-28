<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { matchedRouteKey, onBeforeRouteLeave } from 'vue-router'
import { Database, FileInput, FileSpreadsheet, LayoutDashboard, PackageCheck, RefreshCw } from '@lucide/vue'
import MaterialsHeader from '@/features/indonesia-materials/MaterialsHeader.vue'
import MaterialsPanel from '@/features/indonesia-materials/MaterialsPanel.vue'
import BoardWorkspace from '@/features/indonesia-materials/BoardWorkspace.vue'
import ImportWorkspace from '@/features/indonesia-materials/ImportWorkspace.vue'
import SupplyWorkspace from '@/features/indonesia-materials/SupplyWorkspace.vue'
import MasterWorkspace from '@/features/indonesia-materials/MasterWorkspace.vue'
import { createMaterialsWorkspace, provideMaterials } from '@/features/indonesia-materials/workspace'
import { draftKind, draftKinds, draftLabel } from '@/features/indonesia-materials/draftPersistence'
import '@/features/indonesia-materials/materials.css'
const ws = createMaterialsWorkspace()
provideMaterials(ws)
if (inject(matchedRouteKey, null)) onBeforeRouteLeave(to => ['login', 'forbidden', 'change-password'].includes(String(to.name)) || ws.permitLeave())
const active = ref('board')
const search = ref('')
const draftsOpen = ref(false)
const tabs = [
  { id: 'board', label: '合同计划', component: BoardWorkspace, icon: LayoutDashboard, description: '按客户 PO 和货号跟进，河源物料齐套即完成合同备料。' },
  { id: 'import', label: '统一排期导入', component: ImportWorkspace, icon: FileInput, description: '先核对排期，再生成合同需求与回料期限。' },
  { id: 'supply', label: '回料出货', component: SupplyWorkspace, icon: PackageCheck, description: '收到回料采购单后导入明细，点选抵扣合同／PO，再补装箱并导出本次出货 Excel。' },
  { id: 'master', label: '基础资料库', component: MasterWorkspace, icon: Database, description: '按厂区维护固定客人、客人货号及物料用量，统一日产能、计费和倒排参数。' },
]
const mainTabs = tabs.filter(tab => tab.id !== 'import')
const current = computed(() => tabs.find(tab => tab.id === active.value) ?? tabs[0]!)
function navigate(id: string) {
  if (id === 'demand') { active.value = 'board'; ws.boardStage = 'demand' }
  else if (id === 'shipment') { active.value = 'supply'; ws.supplyStage = 'shipment' }
  else if (tabs.some(tab => tab.id === id)) { active.value = id; if (id === 'board') ws.boardStage = 'board' }
}
function searchContracts(value: string) { search.value = value; active.value = 'board' }
watch(() => ws.scopeEpoch, () => { search.value = '' })
watch(() => ws.restoreTarget, id => { const kind = id ? draftKind(id) : undefined; if (kind) active.value = draftKinds[kind].area })
watch(() => ws.shipmentTarget, id => { if (id) { active.value = 'supply'; ws.supplyStage = 'shipment' } })
watch(() => ws.followupTarget, target => {
  if (!target) return
  navigate(target.kind === 'master' ? 'master' : target.kind === 'reply' ? 'supply' : target.kind === 'recalculate' ? 'demand' : 'board')
})
const savedDrafts = computed(() => Object.values(ws.localDrafts.bucket.drafts).filter(draft => !!draft))
const savedTime = (value: string) => new Date(value).toLocaleString('zh-CN', { hour12: false })
function tabKey(event: KeyboardEvent, index: number) {
  const next = event.key === 'ArrowRight' ? (index + 1) % mainTabs.length
    : event.key === 'ArrowLeft' ? (index + mainTabs.length - 1) % mainTabs.length
      : event.key === 'Home' ? 0 : event.key === 'End' ? mainTabs.length - 1 : -1
  if (next < 0) return
  event.preventDefault()
  active.value = mainTabs[next]!.id
  document.getElementById(`im-tab-${active.value}`)?.focus()
}
</script>
<template>
  <div class="im-workspace">
    <a class="im-skip" href="#im-main">跳到主要内容</a>
    <MaterialsHeader :search="search" :disabled="ws.busy || !!ws.pending" @search="searchContracts">
      <nav v-if="ws.permissions.length" class="im-main-tabs" aria-label="送印尼物料工作区" role="tablist"><button v-for="(tab, index) in mainTabs" :id="`im-tab-${tab.id}`" :key="tab.id" type="button" role="tab" :tabindex="active === tab.id || active === 'import' && tab.id === 'board' ? 0 : -1" :aria-selected="active === tab.id || active === 'import' && tab.id === 'board'" :aria-controls="`im-panel-${tab.id}`" @click="navigate(tab.id)" @keydown="tabKey($event, index)"><component :is="tab.icon" :size="16" aria-hidden="true" />{{ tab.label }}</button></nav>
    </MaterialsHeader>
    <main id="im-main" class="im-main">
      <section class="im-page-bar"><div class="im-page-title"><span class="im-soft-icon"><component :is="current.icon" :size="18" /></span><div><div class="im-inline"><h1>{{ current.label }}</h1><span v-if="ws.permissions.length" class="im-tag" :class="ws.loadError ? 'im-tag-amber' : ''">{{ ws.loadError ? '更新失败 · 上次读取' : ws.loading ? '正在刷新' : '正式台账' }}</span></div></div></div><div class="im-toolbar"><button v-if="active === 'import'" type="button" @click="navigate('board')">返回合同计划</button><button type="button" :aria-expanded="draftsOpen" aria-controls="im-draft-list" @click="draftsOpen = !draftsOpen">草稿 {{ savedDrafts.length }}{{ ws.localDrafts.error ? ' · 保存异常' : '' }}</button><button v-if="active === 'board' && ws.permissions.length" type="button" @click="navigate('shipment')"><FileSpreadsheet :size="15" />出货明细</button><button type="button" :disabled="!ws.factory || ws.loading || ws.busy || !!ws.pending" @click="ws.reload"><RefreshCw :size="15" :class="{ 'im-spinning': ws.loading }" />{{ ws.loading ? '正在刷新…' : '刷新工作区' }}</button></div></section>
    <MaterialsPanel v-if="!ws.factory" title="请选择厂区"><p class="im-empty">请通过顶部厂区选择器选择实际河源厂区，再查看和维护该厂区的送印尼物料。</p></MaterialsPanel>
    <template v-else>

      <p v-if="ws.loadError" role="alert" class="im-error">{{ ws.loadError }}</p>
      <div v-if="ws.error || ws.pending" role="alert" class="im-error"><p>{{ ws.error || '上次提交尚未核对，请重试原操作。' }}</p><button v-if="ws.pending" type="button" class="mt-3" :disabled="ws.busy" @click="ws.retry">重试原操作</button></div>
      <p v-if="ws.notice" role="status" class="im-message">{{ ws.notice }}</p>
      <p v-if="ws.loading && !ws.permissions.length" role="status" class="im-message">正在读取当前厂区工作区…</p>
      <p v-if="ws.permissions.length && !ws.canWrite" class="im-message">当前账号为业务只读模式。{{ ws.has('receipt_confirm') ? '您仍可按船务权限确认回料入库。' : '编辑与业务确认需相应权限。' }}</p>
      <section v-if="ws.permissions.length" v-show="draftsOpen || !!ws.localDrafts.error" id="im-draft-list" class="im-draft-center" aria-label="本机填写草稿">
        <div class="im-draft-heading"><div><strong>本机填写草稿</strong><p>每张单独立保存到本浏览器，刷新后可继续填写。</p></div><span role="status" :class="{ 'im-draft-warning': !!ws.localDrafts.error || ws.hasUnstoredDrafts }">{{ ws.localDrafts.error ? '自动保存异常' : !ws.localDrafts.ready ? '正在读取草稿…' : ws.localDrafts.saving ? '正在自动保存…' : ws.pending ? '提交结果待核对' : ws.hasUnstoredDrafts ? '当前输入尚未保存' : savedDrafts.length ? '已保存到本机' : '自动保存已开启' }}</span></div>
        <div v-if="ws.localDrafts.error" class="im-error" role="alert"><p>{{ ws.localDrafts.error }}</p><button type="button" :disabled="ws.busy || !!ws.localDrafts.saving" @click="ws.reloadDrafts">重新读取草稿</button></div>
        <ul v-if="savedDrafts.length" class="im-draft-list"><li v-for="draft in savedDrafts" :key="draft.id" :data-draft-id="draft.id"><div><strong>{{ draftLabel(draft) }}</strong><small>{{ savedTime(draft.savedAt) }}</small></div><div class="im-actions"><button type="button" :disabled="ws.busy || !!ws.localDrafts.saving" @click="ws.restoreDraft(draft.id)">继续填写</button><button type="button" :disabled="ws.busy || !!ws.pending || !!ws.localDrafts.saving" @click="ws.deleteDraft(draft.id)">删除草稿</button></div></li></ul>
      </section>
      <div v-if="ws.permissions.length" :key="ws.scopeEpoch">
        <div v-for="tab in tabs" v-show="active === tab.id" :id="`im-panel-${tab.id}`" :key="tab.id" role="tabpanel" :aria-labelledby="`im-tab-${tab.id === 'import' ? 'board' : tab.id}`"><component :is="tab.component" v-bind="tab.id === 'board' ? { search } : {}" @navigate="navigate" @search="tab.id === 'board' && typeof $event === 'string' && (search = $event)" /></div>
      </div>
      <p v-else-if="!ws.loading && !ws.loadError" class="im-message">当前账号暂无此厂区的送印尼物料查看权限。</p>
    </template>
    <footer class="im-footer"><span><i></i>业务部 / 船务部协同</span><span>河源发出 → 印尼工厂 · 齐料与出货分别跟进</span></footer>
    </main>
  </div>
</template>
