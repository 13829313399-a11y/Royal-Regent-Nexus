<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { assistantApi } from './api'
import type { Capabilities } from './types'
const props = defineProps<{ capabilities: Capabilities | null }>()
const details = ref<Record<string, unknown> | null>(null), error = ref(''), loading = ref(false)
let generation = 0
watch(() => props.capabilities, () => { generation++; details.value = null; error.value = ''; loading.value = false })
const combinations = computed(() => props.capabilities?.search?.verified_combinations.map(c =>
  `${c.input === 'text' ? '文本' : '图片与文本'} · ${{auto:'自动思考',on:'深度思考',off:'直接回答'}[c.thinking]}`).join('、') || '暂无')
const time = (value?: string | null) => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '暂无本人的执行记录'
async function inspect() {
  if (loading.value) return
  const g = ++generation
  loading.value = true; error.value = ''
  try { const value = await assistantApi.diagnostics(); if (g === generation) details.value = value }
  catch (e) { if (g === generation) error.value = e instanceof Error ? e.message : '诊断暂不可用' }
  finally { if (g === generation) loading.value = false }
}
</script>

<template>
  <section class="yl-connection-details" aria-label="连接与能力状态">
    <p>{{ capabilities?.status_label || '正在读取连接状态…' }}</p>
    <p>{{ capabilities?.search?.status_label || '联网状态尚未取得。' }}</p>
    <dl>
      <dt>可用联网组合</dt><dd>{{ combinations }}</dd>
      <dt>联网历史验证（北京时间）</dt><dd>{{ capabilities?.search?.verified_at ? time(capabilities.search.verified_at) : '未验证' }}</dd>
      <dt>本人最近取得来源</dt><dd>{{ time(capabilities?.search?.last_success?.at) }}</dd>
      <dt>本人最近未完成查证</dt><dd>{{ time(capabilities?.search?.last_failure?.at) }}<template v-if="capabilities?.search?.last_failure?.code"> · {{ capabilities.search.last_failure.code }}</template></dd>
    </dl>
    <p class="yl-muted">历史验证不代表实时健康；搜索次数不等于有效来源数。只显示当前任职周期的本人记录，最近检查范围为 30 次运行。</p>
    <button v-if="capabilities?.diagnostics_available" type="button" :aria-disabled="loading" :aria-busy="loading" @click="inspect">{{ loading ? '读取诊断中…' : '管理员连接诊断' }}</button>
    <p v-if="error" role="alert">{{ error }}</p>
    <pre v-if="details" tabindex="0" aria-label="脱敏连接诊断">{{ JSON.stringify(details, null, 2) }}</pre>
  </section>
</template>

<style scoped>
.yl-connection-details { display: block; min-width: 0; flex-shrink: 0; }
.yl-connection-details p { line-height: 1.6; }
.yl-connection-details dl { display: grid; grid-template-columns: minmax(0, 1fr); gap: 6px; }
.yl-connection-details dt { font-weight: 600; margin-top: 6px; }
.yl-connection-details dd { margin: 0; overflow-wrap: anywhere; }
.yl-connection-details button { min-height: 40px; padding: 8px 12px; background: var(--muted); }
.yl-connection-details pre { max-height: 260px; overflow: auto; padding: 12px; background: var(--muted); font-size: 12px; }
</style>
