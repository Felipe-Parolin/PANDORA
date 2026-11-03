<script setup>
import { watch, onBeforeUnmount } from 'vue'
import { showNotice, dismissNotice } from '../services/notices'
const props = defineProps({ message: { type: String, required: true } })
const emit = defineEmits(['close'])
let current
watch(() => props.message, value => {
  if (current) dismissNotice(current,false)
  if (value) current = showNotice(value,'error',{onClose:() => emit('close')})
}, {immediate:true})
onBeforeUnmount(() => dismissNotice(current,false))
</script>

<template>
  <span v-if="false" />
</template>
