<script setup lang="ts">
import { RouterLink } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import { Button } from '@/components/ui/button'
import CuttingTaskBoard from './CuttingTaskBoard.vue'
import { CUTTING_BASE, CUTTING_FACTORY } from './navigation'
</script>
<template>
  <section class="cutting-page cutting-review-page">
    <PageHeader title="生产看板" description="按业务日期核对计划、合格完成、交接及异常任务。">
      <template #actions>
        <Button as-child><RouterLink :to="{path:`${CUTTING_BASE}/reporting`,query:{factory:CUTTING_FACTORY}}">进入每日记录</RouterLink></Button>
      </template>
    </PageHeader>
    <CuttingTaskBoard />
  </section>
</template>
