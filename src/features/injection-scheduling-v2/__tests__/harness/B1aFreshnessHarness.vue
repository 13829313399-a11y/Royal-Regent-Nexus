<script setup lang="ts">
import { computed, ref } from 'vue'
import SchedulingCommandBar from '../../components/SchedulingCommandBar.vue'
import SchedulingFreshnessBanner from '../../components/SchedulingFreshnessBanner.vue'
import type { SchedulingSyncHealth } from '../../types'

const states: SchedulingSyncHealth[] = ['live', 'refreshing', 'stale', 'demo-readonly', 'error']
const syncHealth = ref<SchedulingSyncHealth>('stale')
const sourceMode = computed<'live' | 'fallback'>(() => syncHealth.value === 'demo-readonly' ? 'fallback' : 'live')
const refreshing = computed(() => syncHealth.value === 'refreshing')
const sourceMessage = computed(() => ({
  live: '正式数据库',
  refreshing: '正在从正式数据库重新取得排产快照',
  stale: '数据同步暂时中断：B1a 去敏网络故障',
  'demo-readonly': '后端暂不可用，当前显示只读演示数据 · B1a 去敏网络故障',
  error: '当前账号无权读取该厂区排产数据：B1a 去敏权限响应',
})[syncHealth.value])
function retry() { syncHealth.value = 'refreshing' }
</script>

<template>
  <div>
    <div class="b1a-controls">
      <strong>B1a 去敏验收夹具 · 不含生产数据</strong>
      <button v-for="state in states" :key="state" type="button" :class="{ active: syncHealth === state }" :data-state="state" @click="syncHealth = state">{{ state }}</button>
    </div>
    <section class="b1a-stage injection-scheduling-v2">
      <SchedulingCommandBar
        factory-id="huaxing"
        factory-name="去敏测试厂区"
        :source-mode="sourceMode"
        :source-message="sourceMessage"
        :sync-health="syncHealth"
        :refreshing="refreshing"
        search=""
        last-synced-at="16:42"
        plan-status="DRAFT"
        :pending-count="0"
        :saving="false"
        :can-save="false"
        :can-import="false"
        :can-export="false"
        :has-planning-draft="true"
        :can-publish="false"
        :publishing-plan="false"
        publish-disabled-reason="B1a 验收夹具禁用业务操作"
        save-message=""
      />
      <main>
        <SchedulingFreshnessBanner
          :sync-health="syncHealth"
          :source-mode="sourceMode"
          :source-message="sourceMessage"
          last-synced-at="16:42"
          :refreshing="refreshing"
          @retry="retry"
        />
        <div class="b1a-note">这里只验证数据来源、新鲜度、最近成功同步时间和重试入口；正式排产资料未载入。</div>
      </main>
    </section>
  </div>
</template>
