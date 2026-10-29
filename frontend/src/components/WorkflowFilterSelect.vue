<script setup>
defineProps({
  modelValue: { type: String, required: true },
  options: { type: Array, required: true },
  label: { type: String, default: 'Etapa' },
})
const emit = defineEmits(['update:modelValue'])
</script>

<template>
  <label class="workflow-filter"><span>{{ label }}</span><select :value="modelValue" @change="emit('update:modelValue', $event.target.value)"><option v-for="item in options" :key="item.key" :value="item.key">{{ item.label }} ({{ item.count }})</option></select></label>
</template>
