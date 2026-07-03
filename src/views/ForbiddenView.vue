<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <main class="flex min-h-screen items-center justify-center bg-slate-100 px-6 text-slate-950">
    <section class="w-full max-w-md rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <p class="text-sm font-semibold text-red-600">403</p>
      <h1 class="mt-2 text-2xl font-black">无权限访问</h1>
      <p class="mt-3 text-sm leading-6 text-slate-600">当前账号没有进入该页面所需的权限。</p>
      <button
        class="mt-6 rounded-md bg-slate-950 px-4 py-2 text-sm font-bold text-white transition hover:bg-slate-800"
        type="button"
        @click="router.replace('/')"
      >
        返回首页
      </button>
    </section>
  </main>
</template>
