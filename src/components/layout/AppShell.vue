<script setup lang="ts">
import { RouterView } from 'vue-router'
import SidebarNav from '@/components/layout/SidebarNav.vue'
import TopBar from '@/components/layout/TopBar.vue'
</script>

<template>
  <div class="min-h-screen bg-slate-100 text-slate-950">
    <TopBar />
    <div class="flex">
      <SidebarNav />
      <main class="min-w-0 flex-1 px-4 py-6 sm:px-6 xl:px-10">
        <RouterView />
      </main>
    </div>
  </div>
</template>
