<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { acceptanceSamples } from './acceptanceSamples'
const props = defineProps<{ showSamples?: boolean }>()
const release = import.meta.env.VITE_CUTTING_ACCEPTANCE_RELEASE?.trim()
const links = ref<ReturnType<typeof acceptanceSamples>>([]), error = ref(''), busy = ref(false)
let controller: AbortController | undefined, generation = 0
async function load() {
  const ticket = ++generation
  controller?.abort(); links.value = []; error.value = ''; busy.value = false
  if (!release || !props.showSamples) return
  controller = new AbortController(); busy.value = true
  try {
    const response = await fetch('/cutting-acceptance-samples.json', { cache: 'no-store', credentials: 'omit', signal: controller.signal })
    if (!response.ok) throw new Error('样本导航暂时无法读取')
    const value = acceptanceSamples(await response.json(), release)
    if (ticket === generation) links.value = value
  } catch { if (ticket === generation) error.value = '样本导航暂时无法读取或与发布版本不一致，请重新读取。' }
  finally { if (ticket === generation) busy.value = false }
}
watch(() => props.showSamples, () => void load(), { immediate: true })
onBeforeUnmount(() => { generation++; controller?.abort() })
</script>
<template>
  <aside v-if="release" class="cutting-acceptance-notice" aria-label="独立验收环境标识" role="note">
    <strong>独立验收环境 · 数据库副本</strong>
    <span>合成业务样本仅供验收，不代表真实订单或正式岗位验收。</span>
    <small>发布版本 {{ release }}</small>
    <details v-if="showSamples"><summary>验收样本导航</summary>
      <p>样本采用固定业务日期。默认页面仍显示当天；下方入口按样本日期定位，操作权限以当前账号为准。</p>
      <p v-if="busy" role="status">正在读取样本导航…</p>
      <p v-if="error" role="alert">{{ error }} <button type="button" @click="load">重新读取样本导航</button></p>
      <nav v-if="links.length" aria-label="合成验收样本"><RouterLink v-for="link in links" :key="JSON.stringify(link.to)" :to="link.to">{{ link.label }}</RouterLink></nav>
    </details>
  </aside>
</template>
<style scoped>
.cutting-acceptance-notice{flex:1 0 100%;min-width:0;display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;margin-bottom:12px;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--accent);color:var(--foreground);font-size:13px;line-height:1.6;overflow-wrap:anywhere}
strong,a,button{color:var(--primary)}small{color:var(--muted-foreground);font-size:12px}details{flex-basis:100%;min-width:0}summary{cursor:pointer}nav{display:flex;flex-wrap:wrap;gap:8px 16px;margin-top:8px}a,button{text-decoration:underline;text-underline-offset:3px;min-height:32px;display:inline-flex;align-items:center}
</style>
