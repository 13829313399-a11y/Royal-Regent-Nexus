<script setup lang="ts">
import PageHeader from '@/components/common/PageHeader.vue'
import CuttingTaskBoard from './CuttingTaskBoard.vue'
</script>
<template><section class="cutting-page"><PageHeader title="生产看板" description="查看当日生产任务、合格完成与异常，直接进入对应订单办理。" /><CuttingTaskBoard /></section></template>
