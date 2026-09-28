<script setup lang="ts">
import PageHeader from '@/components/common/PageHeader.vue'
import PortalMotif from '@/components/portal/PortalMotif.vue'
import type { PortalMotifKind } from '@/components/portal/portalPresentation'

/**
 * 门户身份区：在现有 `PageHeader` 外层提供深翡翠承载面与部门纹样。
 *
 * 不复制公共组件的标题逻辑，`title` / `description` / `eyebrow` 仍由 `PageHeader`
 * 契约承载，actions 插槽原样透传。
 */
withDefaults(defineProps<{
  title: string
  description?: string
  eyebrow?: string
  motif: PortalMotifKind
  /** 该入口当前是否有真实接入的动作；未接入时用于页头的小型状态说明。 */
  pendingNote?: string
}>(), {
  description: '',
  eyebrow: '',
  pendingNote: '新增系统模块暂未接入',
})
</script>

<template>
  <div class="portal-hero">
    <slot name="artwork">
    <div class="portal-hero__motif" aria-hidden="true">
      <PortalMotif :motif="motif" />
    </div>
    </slot>

    <PageHeader
      class="portal-hero__header page-header"
      :eyebrow="eyebrow"
      :title="title"
      :description="description"
    >
      <template #actions>
        <div class="portal-hero__actions">
          <p v-if="pendingNote" class="portal-hero__pending">{{ pendingNote }}</p>
          <slot name="actions" />
        </div>
      </template>
    </PageHeader>
  </div>
</template>
