<script setup lang="ts">
import type { WorkCalendarData } from './api'
const calendar = defineModel<WorkCalendarData | null>({ required: true })
const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
function clear() { if (window.confirm('清除此资源日历？将使用默认周一至周六工作周，预计交期预排、实际领料后核定；既有计划保留原日历并须复核。')) calendar.value = null }
</script>
<template>
  <section class="calendar-editor">
    <h3>执行方工作日历</h3>
    <p>本厂与外发分别设置；供数准备周期默认建议 3 个工作日，可在任务中调整。大于 0 时就绪当天不计。</p>
    <template v-if="calendar">
      <div class="calendar-week"><label v-for="(day, i) in days" :key="day"><input v-model="calendar.weekdays" type="checkbox" :value="i+1" />{{ day }}</label></div>
      <label>日历依据 <input v-model="calendar.basis" required maxlength="500" placeholder="负责人确认的工作周与节假日安排" /></label>
      <div v-for="(exception, i) in calendar.exceptions" :key="i" class="calendar-exception"><label>例外日期 <input v-model="exception.day" type="date" required /></label><label>安排 <select v-model="exception.working"><option :value="true">工作／加班</option><option :value="false">休息／放假</option></select></label><label>原因 <input v-model="exception.reason" required maxlength="200" /></label><button type="button" @click="calendar.exceptions.splice(i, 1)">移除例外</button></div>
      <button type="button" @click="calendar.exceptions.push({ day: '', working: false, reason: '' })">增加休息／调休／加班日期</button>
      <button type="button" @click="clear">清除资源日历</button>
    </template>
    <template v-else><p>尚未配置：按预计交期提前预排，实际领料后再核定，默认周一至周六工作、周日休息。涉及节假日或调休，请配置后再排期。</p><button type="button" @click="calendar = { weekdays: [1,2,3,4,5,6], exceptions: [], basis: '' }">配置该执行方日历</button></template>
  </section>
</template>
<style scoped>.calendar-editor { display: grid; gap: .75rem; border: 1px solid #cbd5e1; padding: 1rem; border-radius: 8px; }.calendar-week,.calendar-exception { display: flex; flex-wrap: wrap; gap: .75rem; }.calendar-editor input,.calendar-editor select { border: 1px solid #cbd5e1; padding: .4rem; max-width: 100%; }.calendar-editor label { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; }</style>
