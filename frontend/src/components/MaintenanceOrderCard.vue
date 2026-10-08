<script setup>
import StatusBadge from './StatusBadge.vue'

defineProps({
  order: { type: Object, required: true },
  scheduledLabel: { type: String, required: true },
})
const emit = defineEmits(['open'])
const terminalStatuses = ['COMPLETED', 'CANCELLED']
</script>

<template>
  <article class="maintenance-order-card">
    <header><span class="eyebrow">{{ order.number }} · {{ order.priority }}</span><StatusBadge :value="order.status" :label="order.status_label" /></header>
    <h3>{{ order.equipment_name }}</h3>
    <p class="maintenance-order-kind">{{ order.maintenance_type_label }}<span v-if="order.plan_name"> · {{ order.plan_name }}</span><span v-if="order.rental_quote_number"> · Reserva {{ order.rental_quote_number }}</span></p>
    <p class="maintenance-order-symptoms">{{ order.symptoms }}</p>
    <div class="maintenance-order-meta"><span><strong>Técnico</strong>{{ order.technician_name || 'A definir' }}</span><span><strong>Agendamento</strong>{{ scheduledLabel }}</span></div>
    <p v-if="order.status === 'ABANDONED'" class="abandoned-callout"><strong>Motivo do abandono</strong>{{ order.abandoned_reason }}</p>
    <footer><button class="btn secondary" @click="emit('open')">{{ terminalStatuses.includes(order.status) ? 'Ver OS' : 'Abrir OS' }}</button></footer>
  </article>
</template>
