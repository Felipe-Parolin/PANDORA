<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, onUpdated, ref, useAttrs, useId, watch } from 'vue'
import { Check, ChevronDown, Search } from 'lucide-vue-next'
import { matchesSearch } from '../services/listFilters'

defineOptions({ inheritAttrs: false })
const props = defineProps({ modelValue: { default: '' }, disabled: Boolean, required: Boolean, id: String, searchable: { type: Boolean, default: false }, modelModifiers: { default: () => ({}) } })
const emit = defineEmits(['update:modelValue', 'change'])
const attrs = useAttrs(), uid = useId()
const root = ref(null), native = ref(null), trigger = ref(null), panel = ref(null), searchInput = ref(null)
const open = ref(false), options = ref([]), search = ref(''), active = ref(-1), position = ref({}), invalid = ref(false), label = ref('')
const listId = `select-${uid}`, controlId = computed(() => props.id || `${listId}-control`)
const sameValue = (a, b) => a === b || String(a) === String(b)
const selected = computed(() => options.value.find(option => sameValue(option.value, props.modelValue)))
const matching = computed(() => options.value.filter(option => !props.searchable || matchesSearch(search.value, option.label)))
// Listas de cadastros podem crescer sem criar centenas de botões no painel.
const filtered = computed(() => {
  const visible = matching.value.slice(0, 50)
  if (!search.value && selected.value && !visible.includes(selected.value)) visible[49] = selected.value
  return visible
})
let observer, signature = ''
function syncOptions() {
  if (!native.value) return
  const result = Array.from(native.value.options).map((option, index) => ({
    index, value: '_value' in option ? option._value : option.value,
    label: option.label, disabled: option.disabled || Boolean(option.closest('optgroup')?.disabled),
  }))
  const current = JSON.stringify(result)
  if (signature !== current) { signature = current; options.value = result }
  native.value.selectedIndex = result.findIndex(option => sameValue(option.value, props.modelValue))
}
function updatePosition() {
  if (!trigger.value || !open.value) return
  const rect = trigger.value.getBoundingClientRect()
  const width = Math.min(Math.max(rect.width, 210), window.innerWidth - 24)
  const below = window.innerHeight - rect.bottom - 12, above = rect.top - 12
  const upwards = below < 240 && above > below
  position.value = {
    width: `${width}px`, left: `${Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))}px`,
    maxHeight: `${Math.min(360, Math.max(100, upwards ? above : below))}px`,
    ...(upwards ? { bottom: `${window.innerHeight - rect.top + 6}px` } : { top: `${rect.bottom + 6}px` }),
  }
}
function close(focus = false) { open.value = false; if (focus) trigger.value?.focus() }
async function show() {
  if (props.disabled) return
  syncOptions(); search.value = ''; open.value = true
  active.value = filtered.value.findIndex(option => sameValue(option.value, props.modelValue) && !option.disabled)
  updatePosition()
  await nextTick()
  if (props.searchable) searchInput.value?.focus()
}
function choose(option) {
  if (props.disabled || option.disabled) return
  let value = option.value
  if (props.modelModifiers.number && value !== '' && !Number.isNaN(Number(value))) value = Number(value)
  native.value.selectedIndex = option.index
  emit('update:modelValue', value)
  emit('change', { target: native.value, currentTarget: native.value })
  invalid.value = false; close(true)
}
function keyboard(event) {
  if (event.key === 'Escape' && open.value) { event.preventDefault(); event.stopPropagation(); close(true); return }
  if (event.key === 'Tab') { close(true); return }
  if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
    event.preventDefault()
    if (!open.value) { show(); return }
    const allowed = filtered.value.map((option, index) => option.disabled ? -1 : index).filter(index => index >= 0)
    if (!allowed.length) return
    const index = allowed.indexOf(active.value)
    if (event.key === 'Home') active.value = allowed[0]
    else if (event.key === 'End') active.value = allowed.at(-1)
    else if (index < 0) active.value = event.key === 'ArrowDown' ? allowed[0] : allowed.at(-1)
    else active.value = allowed[(index + (event.key === 'ArrowDown' ? 1 : -1) + allowed.length) % allowed.length]
    nextTick(() => document.getElementById(`${listId}-${active.value}`)?.scrollIntoView({ block: 'nearest' }))
  } else if (event.key === 'Enter' && open.value) {
    event.preventDefault()
    if (filtered.value[active.value]) choose(filtered.value[active.value])
  } else if (event.key === ' ' && event.target === trigger.value) {
    event.preventDefault(); open.value ? close() : show()
  }
}
function outside(event) { if (!root.value?.contains(event.target) && !panel.value?.contains(event.target)) close() }
function requiredInvalid(event) { event.preventDefault(); invalid.value = true; show(); trigger.value?.focus() }
function stopListening() { document.removeEventListener('pointerdown', outside); window.removeEventListener('resize', updatePosition); window.removeEventListener('scroll', updatePosition, true) }
watch(open, value => {
  stopListening()
  if (value) { document.addEventListener('pointerdown', outside); window.addEventListener('resize', updatePosition); window.addEventListener('scroll', updatePosition, true) }
})
watch(search, () => { active.value = filtered.value.findIndex(option => !option.disabled) }, { flush: 'sync' })
watch(() => props.modelValue, () => { syncOptions(); invalid.value = false })
watch(() => props.disabled, value => { if (value) close() })
onMounted(() => {
  syncOptions()
  const parentLabel = root.value.closest('label')
  const wrappingText = parentLabel ? Array.from(parentLabel.childNodes).filter(node => node.nodeType === 3).map(node => node.textContent).join(' ').trim() : ''
  label.value = wrappingText || root.value.closest('.form-field, .field, .list-control')?.querySelector('label, span')?.textContent?.trim() || ''
  label.value = label.value.replace(/\s*\*$/, '')
  observer = new MutationObserver(syncOptions)
  observer.observe(native.value, { childList: true, subtree: true, attributes: true, characterData: true })
})
onUpdated(syncOptions)
onBeforeUnmount(() => { observer?.disconnect(); stopListening() })
</script>

<template>
  <div ref="root" class="app-select" :class="attrs.class" :style="attrs.style">
    <select ref="native" class="app-select-native" tabindex="-1" aria-hidden="true" :name="attrs.name" :disabled="disabled" :required="required" @invalid="requiredInvalid"><slot /></select>
    <button :id="controlId" ref="trigger" type="button" class="app-select-trigger" :class="{ expanded: open, invalid }" :disabled="disabled" role="combobox" aria-haspopup="listbox" :aria-label="attrs['aria-label'] || label || 'Selecionar opção'" :aria-describedby="attrs['aria-describedby']" :aria-expanded="open" :aria-controls="listId" :aria-required="required" :aria-invalid="invalid || undefined" :aria-activedescendant="open && active >= 0 ? `${listId}-${active}` : undefined" @click="open ? close() : show()" @keydown="keyboard"><span>{{ selected?.label || 'Selecione uma opção' }}</span><ChevronDown :size="16" /></button>
    <Teleport to="body">
      <!-- O painel usa Teleport: a seleção continua pertencendo ao popover que abriu o campo. -->
      <div v-if="open" ref="panel" class="app-select-panel" :style="position" @pointerdown.stop @keydown="keyboard">
        <label v-if="searchable" class="app-select-search"><Search :size="15" /><input ref="searchInput" v-model="search" type="search" placeholder="Digite para buscar..." :aria-label="`Buscar ${attrs['aria-label'] || label || 'opção'}`" :aria-controls="listId" :aria-activedescendant="active >= 0 ? `${listId}-${active}` : undefined" /></label>
        <p v-if="matching.length > filtered.length" class="app-select-limit" role="status">{{ matching.length }} opções. Digite para refinar a busca; exibindo até 50.</p>
        <div :id="listId" class="app-select-options" role="listbox" :aria-label="attrs['aria-label'] || label || 'Opções'">
          <button v-for="(option, index) in filtered" :id="`${listId}-${index}`" :key="option.index" type="button" role="option" tabindex="-1" :aria-selected="sameValue(option.value, modelValue)" :disabled="option.disabled" :class="{ selected: sameValue(option.value, modelValue), focused: active === index }" @pointermove="active = index" @click="choose(option)"><span>{{ option.label }}</span><Check v-if="sameValue(option.value, modelValue)" :size="16" /></button>
          <p v-if="!filtered.length" class="app-select-empty">Nenhuma opção encontrada.</p>
        </div>
      </div>
    </Teleport>
  </div>
</template>
