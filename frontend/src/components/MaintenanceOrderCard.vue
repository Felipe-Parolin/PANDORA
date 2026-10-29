<script setup>
import StatusBadge from './StatusBadge.vue'
import { shortDate } from '../services/api'
import { isOpenServiceOrder, serviceOrderState, serviceOrderStateLabel } from '../services/maintenance'

defineProps({
  order: { type: Object, required: true },
})
const emit = defineEmits(['open'])
</script>

<template>
  <article class="maintenance-order-card">
    <header><span class="eyebrow">{{ order.number }}</span><StatusBadge :value="serviceOrderState(order.status)" :label="serviceOrderStateLabel(order.status)" /></header>
    <h3>{{ order.equipment_name }}</h3>
    <p class="maintenance-order-kind">{{ order.maintenance_type_label }}<span v-if="order.plan_name"> · {{ order.plan_name }}</span><span v-if="order.rental_quote_number"> · Reserva {{ order.rental_quote_number }}</span></p>
    <p class="maintenance-order-symptoms">{{ order.symptoms }}</p>
    <div class="maintenance-order-meta"><span><strong>Técnico</strong>{{ order.technician_name || 'A definir' }}</span><span><strong>{{ order.plan_due_date ? 'Revisão prevista' : 'Abertura' }}</strong>{{ shortDate(order.plan_due_date || order.opened_at?.slice(0, 10)) }}</span></div>
    <footer><button class="btn secondary" @click="emit('open')">{{ isOpenServiceOrder(order.status) ? 'Abrir OS' : 'Ver OS' }}</button></footer>
  </article>
</template>
