<script setup>
const props = defineProps({ value: String, label: String })
const tone = () => {
  const value = props.value || ''
  if (['AVAILABLE', 'APPROVED', 'COMPLETED', 'OK', 'ACTIVE'].includes(value)) return 'success'
  if (['MAINTENANCE', 'CRITICAL', 'OVERDUE', 'CANCELLED', 'INACTIVE', 'ABANDONED'].includes(value)) return 'danger'
  if (['SENT', 'SCHEDULED', 'UPCOMING', 'RESERVED'].includes(value)) return 'warning'
  return 'neutral'
}
</script>
<template><span class="status-badge" :class="tone()"><i />{{ label || value }}</span></template>
