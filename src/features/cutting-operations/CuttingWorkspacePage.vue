<script setup lang="ts">
import StatusPill from '@/components/common/StatusPill.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { computed, ref } from 'vue'
import { ClipboardList, Info } from '@lucide/vue'
import type { CuttingWorkspace } from './navigation'

const props = defineProps<{ workspace: CuttingWorkspace }>()
const selectedTab = ref(0)
const currentTab = computed(() => props.workspace.tabs[selectedTab.value] ?? props.workspace.tabs[0])
</script>

<template>
  <section class="cutting-page">
    <PageHeader :title="workspace.title" :description="workspace.description" eyebrow="华康 C / 裁床部"><template #actions><StatusPill label="建设中 · 业务待接入" /></template></PageHeader>
    <div class="cutting-notice" role="note"><Info :size="18" aria-hidden="true" /><p>当前开放工作区导航与业务说明，尚不能录入、保存或结算业务数据。</p></div>
    <SectionPanel class="cutting-content-panel" :title="currentTab" subtitle="业务数据待接入" :aria-label="workspace.title">
      <div class="cutting-section-nav" aria-label="业务视图">
        <Button variant="outline" v-for="(tab, index) in workspace.tabs" :key="tab" type="button"
          :aria-pressed="selectedTab === index" @click="selectedTab = index">{{ tab }}</Button>
      </div>

      <div v-if="selectedTab === 0" class="cutting-table-scroll" tabindex="0" role="region" :aria-label="`${currentTab}字段预览，可横向滚动`">
        <table>
          <caption class="sr-only">{{ currentTab }}字段预览，尚未接入业务数据</caption>
          <thead><tr><th v-for="column in workspace.columns" :key="column" scope="col">{{ column }}</th></tr></thead>
          <tbody><tr><td :colspan="workspace.columns.length" class="cutting-no-records">尚未接入数据，不代表业务数量为零</td></tr></tbody>
        </table>
      </div>
      <div class="cutting-empty" role="status">
        <span class="cutting-empty-icon"><ClipboardList :size="28" aria-hidden="true" /></span>
        <h3>{{ selectedTab === 0 ? workspace.empty : `${currentTab}尚未开放` }}</h3>
        <p>{{ workspace.next }}</p>
      </div>
    </SectionPanel>
    <details class="cutting-panel cutting-rules" open>
      <summary>业务口径与办理顺序</summary>
      <ul><li v-for="rule in workspace.rules" :key="rule">{{ rule }}</li></ul>
      <p class="cutting-flow">业务下发订单 → 工程确认 BOM → 采购回复交期 → 裁床排期 → 每日填数 → 物料及费用核对 → 月结</p>
    </details>
  </section>
</template>
