<script setup>
import { computed, onMounted, ref, useAttrs, watch } from 'vue'
import { canonicalMask, displayMask, maskError } from '../services/inputMasks'
defineOptions({ inheritAttrs: false })
const props = defineProps({ modelValue: { type: [String, Number], default: '' }, mask: { type: String, required: true }, precision: { type: [String, Number], default: 2 }, required: Boolean, disabled: Boolean, modelModifiers: { default: () => ({}) } })
const emit = defineEmits(['update:modelValue', 'input', 'change', 'blur'])
const attrs = useAttrs(), input = ref(null), focused = ref(false)
const draft = ref(displayMask(props.modelValue, props.mask, Number(props.precision)))
const forwarded = computed(() => Object.fromEntries(Object.entries(attrs).filter(([key]) => !['type', 'maxlength'].includes(key))))
const numeric = computed(() => ['money','decimal','percent'].includes(props.mask))
function validate(value = String(props.modelValue ?? '')) {
  input.value?.setCustomValidity(maskError(value, props.mask, { min: attrs.min, max: attrs.max, step: attrs.step, precision: Number(props.precision) }))
}
function edit(event) {
  const element = event.target, raw = canonicalMask(element.value, props.mask)
  let value = raw
  if (props.modelModifiers.number && raw !== '' && Number.isFinite(Number(raw))) value = Number(raw)
  emit('update:modelValue', value)
  if (numeric.value) draft.value = element.value
  else {
    const position = element.selectionStart ?? element.value.length
    const count = element.value.slice(0,position).replace(/[^A-Z0-9+]/gi,'').length
    draft.value = displayMask(raw, props.mask)
    element.value = draft.value
    let cursor = 0, found = 0
    while (cursor < draft.value.length && found < count) { if (/[A-Z0-9+]/i.test(draft.value[cursor])) found++; cursor++ }
    element.setSelectionRange(cursor,cursor)
  }
  validate(raw)
  emit('input', { target: { value, name: attrs.name } })
}
function blur(event) {
  focused.value = false
  draft.value = displayMask(props.modelValue, props.mask, Number(props.precision))
  validate()
  emit('change', { target: { value: props.modelValue, name: attrs.name } }); emit('blur',event)
}
watch(() => props.modelValue, value => { if (!focused.value) draft.value = displayMask(value,props.mask,Number(props.precision)); validate(String(value ?? '')) })
onMounted(() => validate())
</script>
<template>
  <input ref="input" v-bind="forwarded" :value="draft" type="text" :inputmode="numeric ? 'decimal' : mask === 'phone' ? 'tel' : mask === 'cep' ? 'numeric' : 'text'" :required="required" :disabled="disabled" @focus="focused = true" @input="edit" @blur="blur" />
</template>
