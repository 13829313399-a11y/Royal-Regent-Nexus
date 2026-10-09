<script setup lang="ts">defineProps<{ active?: boolean }>()</script>
<template>
  <svg class="yl-core" :class="{ 'yl-core-active': active }" viewBox="0 0 80 80" aria-hidden="true" focusable="false">
    <ellipse cx="40" cy="40" rx="32" ry="12" fill="none" stroke="currentColor" stroke-width="1.2" transform="rotate(-32 40 40)" />
    <ellipse cx="40" cy="40" rx="31" ry="13" fill="none" stroke="currentColor" stroke-width=".65" transform="rotate(46 40 40)" />
    <ellipse cx="40" cy="40" rx="30" ry="13" fill="none" stroke="currentColor" stroke-width=".65" transform="rotate(99 40 40)" />
    <path d="m40 18 16 15-5 23-16 8-12-24Z" fill="#7de0c6" opacity=".9" />
    <path d="m40 18 2 25 14-10Z" fill="#eafef4" /><path d="m23 40 19 3-7 21Z" fill="#168e7a" />
    <path d="m42 43 9 13-16 8Z" fill="#9786ce" opacity=".7" /><path d="m40 18 2 25-19-3Z" fill="#40bba5" />
    <circle cx="65" cy="23" r="2.2" fill="#f2ddae" /><circle cx="19" cy="56" r="1.5" fill="#b6f7df" />
  </svg>
</template>
