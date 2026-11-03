<template>
      <ExportRecords :feed_id="feed_id" />
</template>

<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import { ref } from 'vue'
import { computed } from 'vue'
import ExportRecords from '@/components/ExportRecords.vue'
const feed_id = ref('')
</script>

<style scoped>
</style>