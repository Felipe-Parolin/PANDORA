<script setup>
defineProps({ modelValue: String, options: { type: Array, required: true }, label: { type: String, default: 'Ordenar por' } })
defineEmits(['update:modelValue'])
</script>

<template>
  <label class="list-control list-ordering"><span>{{ label }}</span><AppSelect :model-value="modelValue" searchable :aria-label="label" @update:model-value="$emit('update:modelValue', $event)"><option v-for="option in options" :key="option[0]" :value="option[0]">{{ option[1] }}</option></AppSelect></label>
</template>
