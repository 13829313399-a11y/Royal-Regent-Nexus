<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle, CheckCircle2, CircleX, Info } from '@lucide/vue'
import type { EligibilityCheck, MachineRecord, MoldRecord } from '../types'

const props = defineProps<{ machine: MachineRecord | null; mold: MoldRecord | null }>()
const checks = computed<EligibilityCheck[]>(() => {
  if (!props.machine || !props.mold) return []
  const machine = props.machine
  const mold = props.mold
  const make = (key: string, label: string, pass: boolean | null, detail: string): EligibilityCheck => ({ key, label, decision: pass == null ? 'REVIEW_REQUIRED' : pass ? 'PASS' : 'FAIL', detail })
  const specialMatch = !mold.specialMachineType || mold.specialMachineType === machine.specialMachineType
  const processBlocked = mold.processRequirements.some((rule) => machine.processRestrictions.includes(`不可${rule}`) || machine.processRestrictions.includes(rule))
  return [
    make('a-class', '安数', machine.aClass != null && mold.aClass != null ? machine.aClass >= mold.aClass : null, `机台 ${machine.aClass ?? (machine.aClassRaw || '待补充')}A · 模具 ${mold.aClass ?? (mold.aClassRaw || '待补充')}A`),
    make('shot', '射胶量', machine.injectionCapacityG != null && mold.netWeightG != null ? machine.injectionCapacityG >= mold.netWeightG : null, `机台 ${machine.injectionCapacityG ?? '待补充'}g · 整啤净重 ${mold.netWeightG ?? '待补充'}g`),
    make('arm', '机械手', mold.requiredArmType ? machine.armCapabilities.includes(mold.requiredArmType) : null, `需要 ${mold.requiredArmType || '待补充'} · 可用 ${machine.armCapabilities.join(' / ') || '待补充'}`),
    make('fixture', '夹具', mold.requiredFixtureType ? machine.fixtureCapabilities.includes(mold.requiredFixtureType) : null, `需要 ${mold.requiredFixtureType || '待补充'} · 可用 ${machine.fixtureCapabilities.join(' / ') || '待补充'}`),
    make('process', '工艺限制', specialMatch && !processBlocked, processBlocked ? `机台限制：${machine.processRestrictions.join('、')}` : mold.processRequirements.length ? `要求：${mold.processRequirements.join('、')}` : '没有额外结构化工艺要求'),
    make('status', '机台状态', !['maintenance', 'offline'].includes(machine.status), machine.status === 'maintenance' ? '机台维护中' : machine.status === 'offline' ? '机台离线' : '机台可参与排产'),
  ]
})
const overall = computed(() => checks.value.some((item) => item.decision === 'FAIL') ? 'FAIL' : checks.value.some((item) => item.decision === 'REVIEW_REQUIRED') ? 'REVIEW_REQUIRED' : 'PASS')
</script>

<template>
  <div v-if="checks.length" class="eligibility-panel">
    <div class="eligibility-summary" :class="overall.toLowerCase()"><component :is="overall === 'PASS' ? CheckCircle2 : overall === 'FAIL' ? CircleX : AlertTriangle" :size="17" /><div><strong>{{ overall === 'PASS' ? '资格校验通过' : overall === 'FAIL' ? '存在硬约束失败' : '需要人工复核' }}</strong><span>V2 默认资格口径，不包含拉杆、模板与吨位</span></div></div>
    <ul><li v-for="item in checks" :key="item.key"><component :is="item.decision === 'PASS' ? CheckCircle2 : item.decision === 'FAIL' ? CircleX : Info" :size="15" :class="item.decision.toLowerCase()" /><div><strong>{{ item.label }}</strong><span>{{ item.detail }}</span></div><em :class="item.decision.toLowerCase()">{{ item.decision === 'PASS' ? '通过' : item.decision === 'FAIL' ? '失败' : '复核' }}</em></li></ul>
  </div>
  <div v-else class="inspector-empty"><Info :size="18" /><span>选择一条计划任务后查看资格校验。</span></div>
</template>
