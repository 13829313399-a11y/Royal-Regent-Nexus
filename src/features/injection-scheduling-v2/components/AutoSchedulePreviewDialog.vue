<script setup lang="ts">
import { Bot, CheckCircle2, LockKeyhole, Sparkles, X } from '@lucide/vue'
defineProps<{ open: boolean; backlogCount: number; machineCount: number }>()
const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <div v-if="open" class="modal-layer" role="dialog" aria-modal="true" aria-labelledby="auto-schedule-title" @click.self="emit('close')"><section class="auto-schedule-dialog"><header><div><span class="modal-icon"><Bot :size="20" /></span><div><span class="eyebrow">AUTO SCHEDULING</span><strong id="auto-schedule-title">自动排期预览</strong></div></div><button aria-label="关闭" @click="emit('close')"><X :size="18" /></button></header><div class="phase-notice"><LockKeyhole :size="18" /><div><strong>自动求解将在 Phase 3 开放</strong><p>Phase 2 已支持人工编辑、回报和资格校验移动；全局求解与应用草案当前不会向后端提交任何变更。</p></div></div><div class="solver-overview"><article><span>输入订单</span><strong>{{ backlogCount }} 条待排</strong></article><article><span>候选机台</span><strong>{{ machineCount }} 台</strong></article><article><span>资格口径</span><strong>V2 六项</strong></article></div><div class="solver-flow"><span><CheckCircle2 :size="14" />读取计划快照</span><i></i><span><CheckCircle2 :size="14" />资格校验</span><i></i><span class="future"><Sparkles :size="14" />全局求解（Phase 3）</span></div><footer><button @click="emit('close')">关闭</button><button class="primary" disabled><Sparkles :size="15" />生成预览方案</button></footer></section></div>
</template>
