<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ACCEPTANCE_GROUPS, acceptancePermissionLabels, acceptanceSamples } from './acceptanceSamples'
const props = defineProps<{ showSamples?: boolean; permissions?: string[] }>()
const release = import.meta.env.VITE_CUTTING_ACCEPTANCE_RELEASE?.trim()
const links = ref<ReturnType<typeof acceptanceSamples>>([]), error = ref(''), busy = ref(false)
let controller: AbortController | undefined, generation = 0
let timeout: ReturnType<typeof setTimeout> | undefined
const groups = computed(() => ACCEPTANCE_GROUPS.map(title => ({ title, links: links.value.filter(link => link.group === title) })).filter(group => group.links.length))
const canOpen = (link: ReturnType<typeof acceptanceSamples>[number]) => link.required.every(p => props.permissions?.includes(p))
const missingPermissions = (link: ReturnType<typeof acceptanceSamples>[number]) => link.required.filter(p => !props.permissions?.includes(p)).map(p => acceptancePermissionLabels[p]).join('、')
async function load() {
  const ticket = ++generation
  clearTimeout(timeout)
  controller?.abort(); links.value = []; error.value = ''; busy.value = false
  if (!release || !props.showSamples) return
  controller = new AbortController(); busy.value = true
  const current = controller
  const deadline = setTimeout(() => {
    if (ticket !== generation) return
    generation++; current.abort(); busy.value = false; error.value = '样本导航读取超时，请重新读取。'
  }, 15000)
  timeout = deadline
  try {
    const response = await fetch('/cutting-acceptance-samples.json', { cache: 'no-store', credentials: 'omit', signal: controller.signal })
    if (!response.ok) throw new Error('样本导航暂时无法读取')
    const value = acceptanceSamples(await response.json(), release)
    if (ticket === generation) links.value = value
  } catch { if (ticket === generation) error.value = '样本导航暂时无法读取或与发布版本不一致，请重新读取。' }
  finally { clearTimeout(deadline); if (timeout === deadline) timeout = undefined; if (ticket === generation) busy.value = false }
}
watch(() => props.showSamples, () => void load(), { immediate: true })
onBeforeUnmount(() => { generation++; clearTimeout(timeout); controller?.abort() })
</script>
<template>
  <aside v-if="release" class="cutting-acceptance-notice" aria-label="独立验收环境标识" role="note">
    <strong>独立验收环境 · 数据库副本</strong>
    <span>合成业务样本仅供验收，不代表真实订单或正式岗位验收。</span>
    <small>发布版本 {{ release }}</small>
    <details v-if="showSamples"><summary>验收样本导航</summary>
      <p>样本采用固定业务日期。默认页面仍显示当天；入口按样本日期定位，不提交未查询的筛选。若已有筛选遮住样本，可在任务列表点击“清空筛选”。</p>
      <p>具备查看条件不代表可以办理。参考岗位和办理分工不提供授权；登记、验收、复核及冲销仍按各自权限执行。</p>
      <p v-if="busy" role="status">正在读取样本导航…</p>
      <p v-if="error" role="alert">{{ error }} <button type="button" @click="load">重新读取样本导航</button></p>
      <nav v-if="links.length" aria-label="合成验收样本" tabindex="0">
        <section v-for="group in groups" :key="group.title"><h3>{{ group.title }}</h3><ul>
          <li v-for="link in group.links" :key="JSON.stringify(link.to)">
            <RouterLink v-if="canOpen(link)" :to="link.to">{{ link.label }}</RouterLink>
            <span v-else class="sample-restricted">{{ link.label }} · 暂无查询权限</span>
            <p>查看条件：{{ link.required.map(p => acceptancePermissionLabels[p]).join('、') }}。{{canOpen(link)?'当前账号具备所列查询权限，目标页仍需核验。':`当前账号缺少：${missingPermissions(link)}。`}}</p>
            <p>核对参考岗位：{{ link.roles.join('、') }}</p><p>负责办理：{{link.handling}}</p><p>预期：{{ link.expected }}</p>
          </li>
        </ul></section>
      </nav>
    </details>
  </aside>
</template>
<style scoped>
.cutting-acceptance-notice{flex:1 0 100%;min-width:0;display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;margin-bottom:12px;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--accent);color:var(--foreground);font-size:13px;line-height:1.6;overflow-wrap:anywhere}
strong,a,button{color:var(--primary)}small{color:var(--muted-foreground);font-size:12px}details{flex-basis:100%;min-width:0}summary{cursor:pointer}nav{display:grid;gap:12px;margin-top:8px;max-height:min(40dvh,360px);overflow:auto;padding:2px}h3{font-size:13px;font-weight:600;margin-bottom:6px}ul{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:8px;list-style:none;padding:0;margin:0}li{min-width:0;background:var(--card);border-radius:6px;padding:8px 10px}li p{color:var(--muted-foreground);font-size:12px}.sample-restricted{display:block;min-height:32px;font-weight:600;color:var(--muted-foreground)}a,button{text-decoration:underline;text-underline-offset:3px;min-height:32px;display:inline-flex;align-items:center}
</style>
