<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useAttrs, useId, watch } from 'vue'
import { CalendarDays, ChevronLeft, ChevronRight, Clock3 } from 'lucide-vue-next'
import { calendarDays, displayDate, localDate, parseDate, withinRange } from '../services/calendar'

defineOptions({ inheritAttrs: false })
const props = defineProps({ modelValue: { type: String, default: '' }, type: { type: String, default: 'date' }, id: String, min: String, max: String, required: Boolean, disabled: Boolean, readonly: Boolean })
const emit = defineEmits(['update:modelValue', 'input', 'change'])
const attrs = useAttrs(), uid = useId(), root = ref(null), trigger = ref(null), native = ref(null), panel = ref(null)
const open = ref(false), invalid = ref(false), position = ref({}), label = ref(''), year = ref(new Date().getFullYear()), month = ref(new Date().getMonth())
const draft = ref(''), hour = ref('09'), minute = ref('00'), focusDay = ref(''), error = ref('')
const months = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
const controlId = computed(() => props.id || `date-${uid}`), panelId = `calendar-${uid}`
const days = computed(() => calendarDays(Math.max(1, Math.min(9999, Number(year.value) || new Date().getFullYear())), Number(month.value)))
const display = computed(() => displayDate(props.modelValue, props.type))
const candidate = computed(() => props.type === 'date' ? draft.value : `${props.type === 'time' ? '' : `${draft.value}T`}${String(hour.value).padStart(2,'0')}:${String(minute.value).padStart(2,'0')}`)
const validTime = computed(() => /^\d{1,2}$/.test(String(hour.value)) && /^\d{1,2}$/.test(String(minute.value)) && Number(hour.value) <= 23 && Number(minute.value) <= 59)
function allowedDay(value) { return Boolean(parseDate(value)) && withinRange(value, props.min?.slice(0,10), props.max?.slice(0,10)) }
function close(focus = false) { open.value = false; if (focus) trigger.value?.focus() }
function updatePosition() {
  if (!open.value || !trigger.value) return
  const rect = trigger.value.getBoundingClientRect(), width = Math.min(332, window.innerWidth-24)
  const below = window.innerHeight-rect.bottom-12, above = rect.top-12, upwards = below < 390 && above > below
  position.value = { width: `${width}px`, left: `${Math.max(12, Math.min(rect.left, window.innerWidth-width-12))}px`, maxHeight: `${Math.max(120, Math.min(520, upwards ? above : below))}px`, ...(upwards ? { bottom: `${window.innerHeight-rect.top+6}px` } : { top: `${rect.bottom+6}px` }) }
}
async function show() {
  if (props.disabled || props.readonly) return
  const today = localDate(new Date())
  draft.value = props.modelValue?.slice(0,10) || (allowedDay(today) ? today : props.min?.slice(0,10) || props.max?.slice(0,10) || today)
  const date = parseDate(draft.value) || new Date()
  year.value = date.getFullYear(); month.value = date.getMonth(); focusDay.value = localDate(date)
  const time = props.type === 'time' ? props.modelValue : props.modelValue?.slice(11)
  ;[hour.value, minute.value] = (time || '09:00').split(':')
  error.value = ''; open.value = true; updatePosition()
  await nextTick()
  panel.value?.querySelector(props.type === 'time' ? '.calendar-time input' : '[tabindex="0"]')?.focus()
}
function commit(value) {
  if (props.disabled || props.readonly) return
  emit('update:modelValue', value)
  if (native.value) native.value.value = value
  emit('input', { target: native.value }); emit('change', { target: native.value })
  invalid.value = false; close(true)
}
function choose(value) {
  if (!allowedDay(value)) return
  draft.value = value; focusDay.value = value
  const date = parseDate(value); year.value = date.getFullYear(); month.value = date.getMonth()
  if (props.type === 'date') commit(value)
}
function apply() {
  error.value = ''
  if (props.type !== 'time' && !parseDate(draft.value) || props.type !== 'date' && !validTime.value || !withinRange(candidate.value, props.min, props.max)) {
    error.value = 'Escolha uma data e um horário dentro do período permitido.'; return
  }
  commit(candidate.value)
}
function shiftMonth(offset) {
  const next = new Date()
  next.setHours(12, 0, 0, 0)
  next.setFullYear(Number(year.value) || new Date().getFullYear(), Number(month.value)+offset, 1)
  if (next.getFullYear() < 1 || next.getFullYear() > 9999) return
  year.value = next.getFullYear(); month.value = next.getMonth()
}
function keyboard(event) {
  if (event.key === 'Escape' && open.value) { event.preventDefault(); event.stopPropagation(); close(true) }
  if (event.key === 'Tab' && open.value && panel.value?.contains(event.target)) {
    const items = [...panel.value.querySelectorAll('button:not(:disabled), input:not(:disabled)')].filter(item => item.tabIndex >= 0)
    if (event.shiftKey && event.target === items[0]) { event.preventDefault(); items.at(-1)?.focus() }
    else if (!event.shiftKey && event.target === items.at(-1)) { event.preventDefault(); items[0]?.focus() }
  }
}
async function moveDay(event, value) {
  const offsets = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }
  if (!(event.key in offsets)) return
  event.preventDefault()
  const date = parseDate(value); date.setDate(date.getDate()+offsets[event.key])
  const next = localDate(date)
  if (!allowedDay(next)) return
  year.value = date.getFullYear(); month.value = date.getMonth(); focusDay.value = next
  await nextTick(); panel.value?.querySelector(`[data-day="${next}"]`)?.focus()
}
function outside(event) { if (!root.value?.contains(event.target) && !panel.value?.contains(event.target)) close() }
function listen(value) {
  document.removeEventListener('pointerdown', outside); window.removeEventListener('resize', updatePosition); window.removeEventListener('scroll', updatePosition, true)
  if (value) { document.addEventListener('pointerdown', outside); window.addEventListener('resize', updatePosition); window.addEventListener('scroll', updatePosition, true) }
}
watch(open, listen)
watch(() => props.disabled, value => { if (value) close() })
watch(() => props.modelValue, () => { invalid.value = false })
onMounted(() => { label.value = (root.value.closest('.form-field, .list-control, label')?.querySelector('label, span')?.textContent?.trim() || root.value.closest('label')?.childNodes[0]?.textContent?.trim() || '').replace(/\s*\*$/, '') })
onBeforeUnmount(() => listen(false))
</script>

<template>
  <div ref="root" class="app-date" :class="attrs.class" :style="attrs.style">
    <input ref="native" class="app-date-native" type="text" :name="attrs.name" :value="modelValue" :required="required" :disabled="disabled" tabindex="-1" aria-hidden="true" @invalid.prevent="invalid = true; show()" />
    <button :id="controlId" ref="trigger" type="button" class="app-date-trigger" :class="{ invalid, placeholder: !display }" :disabled="disabled" :aria-label="attrs['aria-label'] || label || (type === 'date' ? 'Selecionar data' : 'Selecionar data e horário')" :aria-describedby="attrs['aria-describedby']" :aria-expanded="open" :aria-controls="panelId" aria-haspopup="dialog" :aria-required="required" :aria-invalid="invalid || undefined" @click="open ? close() : show()" @keydown="keyboard"><span>{{ display || attrs.placeholder || (type === 'date' ? 'Selecionar data' : type === 'time' ? 'Selecionar horário' : 'Data e horário') }}</span><component :is="type === 'time' ? Clock3 : CalendarDays" :size="17" /></button>
    <Teleport to="body">
      <section v-if="open" :id="panelId" ref="panel" class="calendar-panel" role="dialog" :aria-label="`Escolher ${label || 'data e horário'}`" :style="position" @pointerdown.stop @keydown="keyboard">
        <template v-if="type !== 'time'">
          <header class="calendar-heading"><button type="button" class="icon-btn" aria-label="Mês anterior" @click="shiftMonth(-1)"><ChevronLeft :size="18" /></button><strong>{{ months[month] }}</strong><input v-model="year" type="number" min="1" max="9999" aria-label="Ano" @change="year = Math.max(1, Math.min(9999, Number(year) || new Date().getFullYear()))" /><button type="button" class="icon-btn" aria-label="Próximo mês" @click="shiftMonth(1)"><ChevronRight :size="18" /></button></header>
          <div class="calendar-weekdays" aria-hidden="true"><span v-for="(weekday, index) in ['S','T','Q','Q','S','S','D']" :key="index">{{ weekday }}</span></div>
          <div class="calendar-grid" role="group" aria-label="Dias do mês"><button v-for="day in days" :key="day.value" type="button" :data-day="day.value" :class="{ outside: day.outside, selected: day.value === draft, today: day.value === localDate(new Date()) }" :disabled="!allowedDay(day.value)" :aria-label="displayDate(day.value)" :aria-pressed="day.value === draft" :tabindex="day.value === focusDay ? 0 : -1" @click="choose(day.value)" @keydown="moveDay($event, day.value)">{{ day.day }}</button></div>
        </template>
        <div v-if="type !== 'date'" class="calendar-time"><Clock3 :size="17" /><span>Horário</span><label><span class="sr-only">Hora</span><input v-model="hour" type="number" min="0" max="23" inputmode="numeric" aria-label="Hora" /></label><b>:</b><label><span class="sr-only">Minuto</span><input v-model="minute" type="number" min="0" max="59" inputmode="numeric" aria-label="Minuto" /></label></div>
        <p v-if="error" class="calendar-error" role="alert">{{ error }}</p>
        <footer class="calendar-actions"><button v-if="!required" type="button" @click="commit('')">Limpar</button><button v-if="type !== 'time' && allowedDay(localDate(new Date()))" type="button" @click="choose(localDate(new Date()))">Hoje</button><span class="spacer" /><button v-if="type !== 'date'" type="button" class="btn primary" @click="apply">Aplicar</button></footer>
      </section>
    </Teleport>
  </div>
</template>
