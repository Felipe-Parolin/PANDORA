<script setup>
import { computed, ref } from 'vue'
import { CalendarDays, ChevronLeft, ChevronRight, Clock3 } from 'lucide-vue-next'
import StatusBadge from './StatusBadge.vue'

const props = defineProps({ orders: { type: Array, default: () => [] }, plans: { type: Array, default: () => [] } })
const emit = defineEmits(['open-order', 'open-plan'])

const dateKey = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
const localKey = value => value ? dateKey(new Date(value)) : ''
const capitalize = value => value.charAt(0).toUpperCase() + value.slice(1)
const today = dateKey(new Date())
const selected = ref(today)
const month = ref(new Date(new Date().getFullYear(), new Date().getMonth(), 1))
const weekdays = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
const monthLabel = computed(() => capitalize(new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(month.value)))
const selectedLabel = computed(() => capitalize(new Intl.DateTimeFormat('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date(`${selected.value}T12:00:00`))))
const dayLabel = key => new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(`${key}T12:00:00`))
const countLabel = count => count === 1 ? '1 manutenção' : `${count} manutenções`

const events = computed(() => {
  const items = []
  for (const order of props.orders) {
    if (order.status === 'CANCELLED') continue
    const scheduled = Boolean(order.scheduled_at)
    const key = scheduled ? localKey(order.scheduled_at) : localKey(order.opened_at)
    if (!scheduled && (key !== today || order.status === 'COMPLETED')) continue
    if (key) items.push({ key, kind: 'order', item: order, title: order.equipment_name, subtitle: scheduled ? `${order.number} · ${order.maintenance_type_label}` : `${order.number} · aberto hoje, sem horário`, status: order.status, statusLabel: order.status_label, time: scheduled ? new Date(order.scheduled_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '' })
  }
  for (const plan of props.plans) {
    if (plan.active && plan.due_date) items.push({ key: plan.due_date, kind: 'plan', item: plan, title: plan.equipment_name, subtitle: `Plano · ${plan.name}`, status: plan.alert_status, statusLabel: ({ OK: 'Em dia', UPCOMING: 'Próxima', OVERDUE: 'Vencida', CRITICAL: 'Crítica' })[plan.alert_status], time: '' })
  }
  return items.sort((a, b) => a.key.localeCompare(b.key) || a.time.localeCompare(b.time) || a.title.localeCompare(b.title))
})
const eventsByDay = computed(() => {
  const groups = new Map()
  for (const event of events.value) groups.set(event.key, [...(groups.get(event.key) || []), event])
  return groups
})
const dayEvents = computed(() => eventsByDay.value.get(selected.value) || [])
const unscheduled = computed(() => props.orders.filter(order => !order.scheduled_at && !['COMPLETED', 'CANCELLED'].includes(order.status)))
const cells = computed(() => {
  const first = new Date(month.value.getFullYear(), month.value.getMonth(), 1)
  const mondayOffset = (first.getDay() + 6) % 7
  const count = Math.ceil((mondayOffset + new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate()) / 7) * 7
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(first.getFullYear(), first.getMonth(), index - mondayOffset + 1)
    const key = dateKey(date)
    return { key, day: date.getDate(), inMonth: date.getMonth() === first.getMonth(), events: eventsByDay.value.get(key) || [] }
  })
})

function openEvent(event) { emit(event.kind === 'order' ? 'open-order' : 'open-plan', event.item) }
function selectDay(cell) {
  selected.value = cell.key
  if (!cell.inMonth) month.value = new Date(`${cell.key}T12:00:00`)
  if (cell.events.length === 1) openEvent(cell.events[0])
}
function shiftMonth(delta) {
  month.value = new Date(month.value.getFullYear(), month.value.getMonth() + delta, 1)
  selected.value = dateKey(new Date(month.value.getFullYear(), month.value.getMonth(), 1))
}
function goToday() {
  const now = new Date()
  month.value = new Date(now.getFullYear(), now.getMonth(), 1)
  selected.value = today
}
</script>

<template>
  <div class="maintenance-calendar-layout">
    <section class="panel maintenance-calendar-panel">
      <header class="maintenance-calendar-header"><div><span class="eyebrow">AGENDA DE MANUTENÇÃO</span><h2>{{ monthLabel }}</h2><p>OS agendadas e planos com data. Clique no dia ou no evento.</p></div><div class="calendar-navigation"><button class="btn secondary" @click="goToday">Hoje</button><button class="icon-btn table-action" aria-label="Mês anterior" @click="shiftMonth(-1)"><ChevronLeft :size="19" /></button><button class="icon-btn table-action" aria-label="Próximo mês" @click="shiftMonth(1)"><ChevronRight :size="19" /></button></div></header>
      <div class="maintenance-calendar-grid" role="group" aria-label="Calendário de manutenção">
        <div v-for="label in weekdays" :key="label" class="calendar-weekday">{{ label }}</div>
        <button v-for="cell in cells" :key="cell.key" class="maintenance-calendar-day" :class="{ muted: !cell.inMonth, selected: selected === cell.key, today: today === cell.key, busy: cell.events.length }" :aria-label="`${dayLabel(cell.key)}, ${countLabel(cell.events.length)}`" @click="selectDay(cell)"><span class="calendar-day-number">{{ cell.day }}</span><span v-if="cell.events.length" class="calendar-day-count">{{ cell.events.length }} <span>evento{{ cell.events.length > 1 ? 's' : '' }}</span></span><span class="calendar-day-preview">{{ cell.events[0]?.title }}</span></button>
      </div>
    </section>
    <aside class="maintenance-day-panel"><section class="panel maintenance-day-agenda"><header><span class="eyebrow">DIA SELECIONADO</span><h2>{{ selectedLabel }}</h2><small>{{ countLabel(dayEvents.length) }}</small></header><div v-if="dayEvents.length" class="maintenance-day-events"><button v-for="(event, index) in dayEvents" :key="`${event.kind}-${event.item.id}-${index}`" @click="openEvent(event)"><span class="calendar-event-mark" :class="event.kind" /><span class="calendar-event-copy"><strong>{{ event.title }}</strong><small>{{ event.time ? `${event.time} · ` : '' }}{{ event.subtitle }}</small></span><StatusBadge :value="event.status" :label="event.statusLabel" /></button></div><div v-else class="maintenance-day-empty"><CalendarDays :size="25" /><strong>Nada agendado neste dia</strong><span>Escolha outra data ou agende uma preventiva.</span></div></section><section v-if="unscheduled.length" class="panel maintenance-triage"><header><Clock3 :size="17" /><strong>Sem data agendada</strong><b>{{ unscheduled.length }}</b></header><button v-for="order in unscheduled.slice(0, 4)" :key="order.id" @click="emit('open-order', order)"><strong>{{ order.equipment_name }}</strong><small>{{ order.number }} · {{ order.status_label }}</small></button><small v-if="unscheduled.length > 4">Mais {{ unscheduled.length - 4 }} chamado(s) nas abas.</small></section></aside>
  </div>
</template>
