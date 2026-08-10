<script setup lang="ts">
import { AlertTriangle, CheckCircle2, LoaderCircle, Send, X } from '@lucide/vue'
import type { SchedulingPlanRecord } from '../types'

defineProps<{
  open: boolean
  plan: SchedulingPlanRecord | null
  taskCount: number
  canPublish: boolean
  publishing: boolean
  error: string
}>()

const emit = defineEmits<{ close: []; confirm: [] }>()
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" @mousedown.self="!publishing && emit('close')">
      <section class="phase2-dialog publish-plan-dialog" role="dialog" aria-modal="true" aria-labelledby="publish-plan-title">
        <header>
          <div><span class="eyebrow">计划发布</span><strong id="publish-plan-title">发布正式执行计划</strong></div>
          <button type="button" aria-label="关闭发布确认" :disabled="publishing" @click="emit('close')"><X :size="17" /></button>
        </header>

        <div class="publish-plan-body">
          <div class="publish-plan-icon"><Send :size="22" /></div>
          <div>
            <strong>确认发布规划草案 r{{ plan?.revision ?? '—' }}？</strong>
            <p>发布后，这 {{ taskCount }} 条任务将成为正式执行队列；如已有执行计划，旧计划会归档。</p>
          </div>
          <ul>
            <li><CheckCircle2 :size="15" />服务端按模具编号自动绑定默认实体模具，并校验占用时间。</li>
            <li><CheckCircle2 :size="15" />发布成功后自动切换到“执行 PUBLISHED”视图。</li>
            <li><AlertTriangle :size="15" />发布后的计划不能直接改排；重大调整需回滚生成新草案。</li>
          </ul>
          <p v-if="!canPublish" class="publish-plan-warning"><AlertTriangle :size="15" />当前账号没有排产编辑或发布权限。</p>
          <p v-if="!taskCount" class="publish-plan-warning"><AlertTriangle :size="15" />空计划不能发布。</p>
          <p v-if="error" class="publish-plan-error"><AlertTriangle :size="15" />{{ error }}</p>
        </div>

        <footer>
          <button type="button" :disabled="publishing" @click="emit('close')">取消</button>
          <button type="button" class="primary" :disabled="!canPublish || !taskCount || publishing" @click="emit('confirm')">
            <LoaderCircle v-if="publishing" :size="15" class="spinning" />
            <Send v-else :size="15" />
            {{ publishing ? '正在发布…' : `确认发布 r${plan?.revision ?? ''}` }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
