<script setup lang="ts">
import { ArrowUpRight, ChevronRight, Pin, PinOff } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import type { EnterpriseModule } from '@/data/enterpriseMock'
import StatusPill from '@/components/common/StatusPill.vue'
defineProps<{ module: EnterpriseModule | null; pinned: boolean; searching?: boolean }>()
defineEmits<{ unpin: [] }>()
const isExternalLink = (href: string) => /^https?:\/\//i.test(href)
</script>
<template>
  <section class="home-preview" aria-label="模块聚焦" :data-pinned="pinned">
    <header class="home-preview__heading"><h2>模块聚焦</h2><span v-if="pinned"><Pin :size="13" aria-hidden="true" />已固定预览</span><span v-else>模块介绍</span></header>
    <div v-if="module" :key="module.id" class="home-preview__body">
      <div class="home-preview__identity"><span class="home-preview__icon"><component :is="module.icon" :size="28" aria-hidden="true" /></span><StatusPill :label="module.status" :tone="module.statusTone" compact /></div>
      <h3>{{ module.title }}</h3><p class="home-preview__owner">{{ module.owner }}</p>
      <p class="home-preview__summary">{{ module.summary }}</p>
      <dl v-if="module.statusMetrics.length" class="home-preview__metrics"><div v-for="metric in module.statusMetrics" :key="metric.label"><dt>{{ metric.label }}</dt><dd>{{ metric.value }}</dd></div></dl>
      <div v-if="module.children.length" class="home-preview__tags"><span v-for="child in module.children" :key="child.label">{{ child.label }}</span></div>
      <div v-if="module.todos.length" class="home-preview__todos"><h4>目录待办 · 示例</h4><ul><li v-for="todo in module.todos" :key="todo">{{ todo }}</li></ul></div>
      <div class="home-preview__actions">
        <RouterLink v-if="module.route" :to="module.route" class="portal-action portal-action--primary">查看模块<ChevronRight :size="16" aria-hidden="true" /></RouterLink>
        <RouterLink v-if="module.href && !isExternalLink(module.href)" :to="module.href" class="portal-action portal-action--secondary">打开系统<ArrowUpRight :size="16" aria-hidden="true" /></RouterLink>
        <a v-else-if="module.href" :href="module.href" target="_blank" rel="noreferrer" class="portal-action portal-action--secondary">打开系统<ArrowUpRight :size="16" aria-hidden="true" /></a>
        <button v-if="pinned" type="button" class="home-unpin" @click="$emit('unpin')"><PinOff :size="15" aria-hidden="true" />取消固定</button>
      </div>
    </div>
    <p v-else class="home-empty">{{ searching ? '没有匹配的入口，清除搜索后继续浏览。' : '当前厂区没有可显示的模块。' }}</p>
  </section>
</template>
