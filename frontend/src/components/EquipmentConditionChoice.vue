<script setup>
import { CheckCircle2, Wrench } from 'lucide-vue-next'

defineProps({
  modelValue: { type: String, default: '' },
  disabled: Boolean,
  operatingHint: { type: String, default: 'Funcionamento verificado e sem impedimentos.' },
  brokenHint: { type: String, default: 'Permanece bloqueado até o reparo e nova avaliação.' },
})
const emit = defineEmits(['update:modelValue'])
</script>

<template>
  <fieldset class="inspection-decision" :disabled="disabled"><legend>O equipamento está em condições de uso?</legend><div class="inspection-decision-options"><button type="button" :aria-pressed="modelValue === 'OPERATING'" :class="{ selected: modelValue === 'OPERATING' }" @click="emit('update:modelValue', 'OPERATING')"><CheckCircle2 :size="22" /><strong>Operante</strong><small>{{ operatingHint }}</small></button><button type="button" class="broken" :aria-pressed="modelValue === 'BROKEN'" :class="{ selected: modelValue === 'BROKEN' }" @click="emit('update:modelValue', 'BROKEN')"><Wrench :size="22" /><strong>Inoperante</strong><small>{{ brokenHint }}</small></button></div></fieldset>
</template>
