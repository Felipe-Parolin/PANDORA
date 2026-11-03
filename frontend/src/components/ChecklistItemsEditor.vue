<script setup>
import { nextTick, ref, useId } from 'vue'
import { Plus, Trash2 } from 'lucide-vue-next'

const props = defineProps({ modelValue: { type: Array, default: () => [] }, title: String })
const emit = defineEmits(['update:modelValue'])
const root = ref(null), uid = useId()
const label = item => typeof item === 'string' ? item : item.label || ''
function update(index, value) {
  const items = [...props.modelValue]
  items[index] = typeof items[index] === 'string' ? value : { ...items[index], label: value }
  emit('update:modelValue', items)
}
async function add() {
  emit('update:modelValue', [...props.modelValue, ''])
  await nextTick()
  root.value?.querySelector('li:last-child input')?.focus()
}
function remove(index) { emit('update:modelValue', props.modelValue.filter((_, position) => position !== index)) }
</script>

<template>
  <section ref="root" class="checklist-items-editor">
    <header><h3>{{ title }}</h3><span>{{ modelValue.length }} ponto(s)</span></header>
    <ol v-if="modelValue.length"><li v-for="(item, index) in modelValue" :key="index"><label :for="`${uid}-${index}`">{{ index + 1 }}</label><input :id="`${uid}-${index}`" :value="label(item)" :aria-label="`${title}: ponto ${index + 1}`" placeholder="Ex.: Conferir cabo elétrico" maxlength="300" @input="update(index, $event.target.value)" /><button type="button" class="icon-btn danger-icon" :aria-label="`Remover ponto ${index + 1} de ${title}`" @click="remove(index)"><Trash2 :size="16" /></button></li></ol>
    <p v-else>Nenhum ponto cadastrado. Adicione os critérios que a equipe deve conferir.</p>
    <button type="button" class="btn secondary" @click="add"><Plus :size="16" />Adicionar ponto</button>
  </section>
</template>

<style scoped>
.checklist-items-editor { min-width: 0; padding: 16px; border: 1px solid var(--line); border-radius: 10px; background: #fafafa; }.checklist-items-editor header { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 14px; }.checklist-items-editor h3 { font-size: 13px; margin: 0; }.checklist-items-editor header span, .checklist-items-editor p { font-size: 11px; color: var(--muted); }.checklist-items-editor ol { list-style: none; margin: 0 0 12px; padding: 0; display: grid; gap: 9px; }.checklist-items-editor li { display: flex; align-items: center; gap: 8px; }.checklist-items-editor li label { flex-shrink: 0; font-size: 11px; font-weight: 700; color: var(--muted); }.checklist-items-editor input { width: 100%; min-width: 0; padding: 10px; border: 1px solid var(--line); border-radius: 7px; background: white; }.checklist-items-editor .icon-btn { flex-shrink: 0; }
</style>
