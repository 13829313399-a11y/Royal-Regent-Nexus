<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { RefreshCw } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { factoryContexts } from '@/data/enterpriseMock'
import { identityKey } from './context'
import { assistantApi, AssistantApiError } from './api'
import type { ModuleCoverage, ModuleCoverageState, PageContext } from './types'

const props = defineProps<{ page: PageContext | null }>()
const auth = useAuthStore(), app = useAppStore()
const factory = computed(() => props.page?.factory_id || app.activeFactoryId)
const factoryLabel = computed(() => factoryContexts.find(f => f.id === factory.value)?.name || (factory.value === 'authorized' ? '本人授权范围' : '当前范围'))
const result = ref<ModuleCoverage | null>(null), busy = ref(false), error = ref('')
const root = ref<HTMLElement>(), refreshButton = ref<HTMLButtonElement>()
const labels: Record<ModuleCoverageState, string> = { business_read: '可只读查询', guide_only: '仅操作说明', disabled: '未启用', not_connected: '未接入', forbidden: '无权限' }
let generation = 0, controller: AbortController | undefined
async function refresh() {
  const current = ++generation
  const focused = document.activeElement
  const ownedFocus = !!focused && !!root.value?.contains(focused)
  // Keep Escape/Tab inside the panel while the initiating button is removed
  // or disabled, including a request that remains pending for a long time.
  if (ownedFocus) root.value?.focus()
  controller?.abort(); controller = new AbortController()
  result.value = null; error.value = ''; busy.value = true
  try {
    const value = await assistantApi.coverage(factory.value, props.page?.module_id, controller.signal)
    if (current === generation) result.value = value
  } catch (e) {
    if (current === generation) error.value = e instanceof AssistantApiError ? e.message : '暂时无法连接，请检查网络后重试。'
  } finally {
    if (current === generation) {
      busy.value = false
      await nextTick()
      // The retry button disappears on success. Keep keyboard users inside the
      // layer without taking focus back from a control they chose meanwhile.
      if (current === generation && ownedFocus && [document.body, root.value].includes(document.activeElement as HTMLElement)) refreshButton.value?.focus()
    }
  }
}
watch([factory, () => props.page?.module_id, () => identityKey(auth.currentUser), () => auth.authorizationVersion,
  () => JSON.stringify([auth.effectiveAccess, auth.permissions, auth.grants, auth.authzMode])], refresh, {immediate: true, flush: 'sync'})
onUnmounted(() => { ++generation; controller?.abort() })
</script>

<template>
  <section ref="root" class="yl-coverage" tabindex="-1" aria-label="当前范围的模块覆盖" :aria-busy="busy">
    <div class="yl-coverage-scope"><strong>{{ factoryLabel }}</strong><button ref="refreshButton" :disabled="busy" @click="refresh"><RefreshCw :size="15"/>刷新覆盖状态</button></div>
    <p>按当前登录账号与厂区检查。查询时仍会重新鉴权；可读取范围由各模块决定。</p>
    <p class="yl-muted">这里列出已登记的业务入口和说明；未列出的模块尚未登记。此检查不生成回答，也不读取业务记录。</p>
    <p v-if="busy" role="status">正在核对当前范围…</p>
    <div v-else-if="error" role="status"><p>{{ error }}</p><button @click="refresh">重试检查</button></div>
    <template v-else-if="result">
      <p class="yl-coverage-time">检查时间：{{ new Date(result.checked_at).toLocaleString('zh-CN') }}</p>
      <p v-if="!result.items.length" role="status">当前没有已登记模块。</p>
      <ul v-else class="yl-coverage-list">
        <li v-for="item in result.items" :key="item.module_id" :data-state="item.state">
          <div class="yl-coverage-heading"><h3>{{ item.label }}</h3><span class="yl-coverage-badge">{{ labels[item.state] }}</span></div>
          <p>{{ item.reason }}</p>
          <small v-if="item.verification === 'implemented_unverified'">读取入口已实现 · 完整验收待完成</small>
          <small v-else-if="item.verification === 'connected'">接入验收已通过</small>
          <small v-if="item.guide_count">{{ item.guide_count }} 条当前范围操作说明</small>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.yl-coverage{min-width:0;overflow-wrap:anywhere}
.yl-coverage-scope{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.yl-coverage button{padding:7px 10px;border:1px solid var(--yl-line);background:var(--yl-panel);color:var(--yl-deep)}
.yl-coverage-time,.yl-coverage small{font-size:12px;color:var(--yl-muted)}
.yl-coverage-list{list-style:none;padding:0;margin:0;display:grid;gap:12px}
.yl-coverage-list li{padding:14px;border:1px solid var(--yl-line);border-radius:12px;background:var(--yl-paper)}
.yl-coverage-heading{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:8px;justify-content:space-between}
.yl-coverage-heading h3{font-size:14px;font-weight:650;margin:0}
.yl-coverage-badge{font-size:12px;padding:2px 8px;border-radius:6px;color:var(--yl-muted);background:var(--yl-panel);white-space:nowrap}
[data-state=business_read] .yl-coverage-badge{color:var(--yl-deep);border:1px solid var(--yl-line)}
.yl-coverage-list p{font-size:13px;margin-bottom:8px}
.yl-coverage small{display:block}
</style>
