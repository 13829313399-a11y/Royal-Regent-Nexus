<script setup lang="ts">
import { computed, watch } from 'vue'
import { createMaterialsWorkspace, provideMaterials, useMaterials } from './workspace'
import { draftKind, draftLabel, newDraftId } from './draftPersistence'
import OptionsWorkspace from './OptionsWorkspace.vue'
const parent = useMaterials()
const ws = createMaterialsWorkspace(true)
provideMaterials(ws)
const drafts = computed(() => Object.values(ws.localDrafts.bucket.drafts).filter(item => !!item))
const legacyDrafts = computed(() => Object.values(parent.localDrafts.bucket.drafts).filter(item => item && draftKind(item.id) === 'options'))
async function copyLegacy(item: NonNullable<typeof legacyDrafts.value[number]>) {
  if (ws.locked || parent.pending || !ws.canWrite) return
  const id = newDraftId('options')
  ws.localDrafts.adopt(id)
  if (await ws.localDrafts.save(id, { ...item.state, editing: null, named: false, label: `从旧厂区复制 · ${item.state.form?.value || '新选项'}` })) await ws.restoreDraft(id)
}
watch(() => ws.notice, value => { if (value.startsWith('已保存')) void parent.reload() })
defineExpose({ permitDiscard: ws.permitLeave })
</script>
<template>
  <section class="im-shared-options" aria-label="全厂共用基础选项">
    <div class="im-message"><strong>全部河源厂区共用</strong><p>普通业务新增维护；业务主管／管理员负责启停、删除、恢复及换算规则。共用选项不会开放其他厂区的客人、货号、物料或单据。</p></div>
    <p v-if="ws.loadError" role="alert" class="im-error">{{ ws.loadError }}</p>
    <div v-if="ws.error || ws.pending" role="alert" class="im-error"><p>{{ ws.error }}</p><button v-if="ws.pending" type="button" :disabled="ws.busy" @click="ws.retry">重试原操作</button></div>
    <p v-if="ws.notice" role="status" class="im-message">{{ ws.notice }}</p>
    <div class="im-draft-center" aria-label="共用选项本机草稿"><div class="im-draft-heading"><strong>共用选项草稿 · 当前账号跨厂区继续填写</strong><span role="status">{{ ws.localDrafts.error || (ws.localDrafts.saving || ws.hasUnstoredDrafts ? '正在自动保存…' : '已保存到本机') }}</span><button type="button" :disabled="ws.busy || !!ws.pending || ws.loading" @click="ws.reload">刷新共用选项</button></div><button v-if="ws.localDrafts.error" type="button" :disabled="ws.busy" @click="ws.reloadDrafts">重新读取共用草稿</button><ul class="im-draft-list"><li v-for="item in drafts" :key="item.id" :data-draft-id="item.id"><strong>{{ draftLabel(item) }}</strong><div class="im-actions"><button type="button" :disabled="ws.busy || !!ws.localDrafts.saving" @click="ws.restoreDraft(item.id)">继续填写</button><button type="button" :disabled="ws.locked || !!ws.localDrafts.saving" @click="ws.deleteDraft(item.id)">删除草稿</button></div></li></ul></div>
    <OptionsWorkspace v-if="ws.permissions.length" />
    <details v-if="legacyDrafts.length" class="im-deleted-list"><summary>旧厂区选项草稿（仅本账号当前厂区）</summary><p class="im-note">旧草稿不会自动变成全厂修改。可明确复制为一份共用新建草稿，核对后保存；原草稿保留，有未决提交时先核对原操作。</p><div v-for="item in legacyDrafts" :key="item!.id"><strong>{{ item!.state.form?.value }}</strong><p>原状态：{{ item!.state.form?.status }}；原计价：{{ item!.state.form?.billing_basis }}；每单位千克数：{{ item!.state.form?.kg_per_unit }}</p><button type="button" :disabled="ws.locked || !!parent.pending || !ws.canWrite" @click="copyLegacy(item!)">复制到共用新建草稿</button></div></details>
    <p v-if="!ws.permissions.length" class="im-note">{{ ws.loading ? '正在读取共用资料…' : '没有共用资料查看权限，请核对本模块岗位授权。' }}</p>
  </section>
</template>
