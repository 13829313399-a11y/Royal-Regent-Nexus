<script setup lang="ts">
defineProps<{ id: string; label: string; error?: string; hint?: string; required?: boolean }>()
</script>
<template>
  <div class="ng-field" :data-invalid="Boolean(error)">
    <label :for="id">{{ label }}<span v-if="required" class="auth-required" aria-hidden="true"> *</span></label>
    <slot :describedby="error ? `${id}-error` : hint ? `${id}-hint` : undefined" :invalid="Boolean(error)" />
    <p v-if="error" :id="`${id}-error`" class="ng-field-error">{{ error }}</p>
    <p v-else-if="hint" :id="`${id}-hint`" class="auth-hint">{{ hint }}</p>
  </div>
</template>
