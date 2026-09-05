<script setup lang="ts">
import { provide } from "vue";
import { useOperations } from "../composables/useOperations";
import { operationsKey } from "../operationsContext";
import OperationsResources from "../components/operations/OperationsResources.vue";
import OperationsInsights from "../components/operations/OperationsInsights.vue";
import OperationsReconciliation from "../components/operations/OperationsReconciliation.vue";
provide(operationsKey, useOperations());
</script>
<template>
  <section class="space-y-5">
    <OperationsResources /><OperationsInsights /><OperationsReconciliation />
  </section>
</template>
