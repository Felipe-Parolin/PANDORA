<script setup>
import { CalendarClock, MapPin, Truck } from 'lucide-vue-next'
import { shortDate } from '../services/api'
import { tripActionLabel } from '../services/logistics'
defineProps({ trip: { type: Object, required: true }, canManage: Boolean })
defineEmits(['open'])
const schedule = value => new Date(value).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
</script>

<template>
  <article class="dispatch-card">
    <header><span class="dispatch-leg" :class="{ collection: trip.leg === 'RETURN' }">{{ trip.leg === 'DELIVERY' ? 'Entrega' : 'Coleta' }}</span><span class="dispatch-status" :class="trip.workflow?.code?.toLowerCase()">{{ trip.workflow?.label || trip.status_label }}</span></header>
    <h3>{{ trip.customer_name }}</h3><p class="dispatch-reference">{{ trip.quote_number }} · {{ trip.equipment.length }} equipamento(s)</p>
    <div class="dispatch-route"><MapPin :size="17" /><div><small>{{ trip.leg === 'DELIVERY' ? 'Depósito → cliente' : 'Cliente → depósito' }}</small><strong>{{ trip.address }}</strong><span v-if="trip.complement">{{ trip.complement }}</span></div></div>
    <p class="dispatch-equipment">{{ trip.equipment.map(item => item.name).join(' · ') }}</p>
    <div class="dispatch-assignment"><span><CalendarClock :size="16" /><span>{{ trip.scheduled_at ? schedule(trip.scheduled_at) : `Programar para ${shortDate(trip.leg === 'DELIVERY' ? trip.rental_start_date : trip.rental_end_date)}` }}</span></span><span><Truck :size="16" /><span>{{ trip.vehicle_plate || 'Veículo a definir' }}<small>{{ trip.driver_name || 'Motorista a definir' }}</small></span></span></div>
    <footer><p>{{ trip.workflow?.detail }}</p><button class="btn secondary" @click="$emit('open', trip)">{{ canManage ? tripActionLabel(trip) : 'Ver detalhes' }}</button></footer>
  </article>
</template>
