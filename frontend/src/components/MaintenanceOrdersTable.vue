<script setup>
import { computed } from 'vue'
import { Eye } from 'lucide-vue-next'
import { usePagination } from '../services/pagination'
import { shortDate } from '../services/api'
import StatusBadge from './StatusBadge.vue'
const props = defineProps({ orders: { type: Array, required: true } })
defineEmits(['open'])
const { page, items } = usePagination(computed(() => props.orders), [() => props.orders])
const scheduledLabel = value => value ? `${shortDate(new Date(value).toLocaleDateString('en-CA'))} · ${new Date(value).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}` : 'A definir'
</script>

<template>
  <div class="maintenance-orders-table"><div class="table-wrap"><table><thead><tr><th>Ordem de serviço</th><th>Equipamento</th><th>Tipo</th><th>Prioridade</th><th>Técnico</th><th>Agendamento</th><th>Situação</th><th class="right">Ações</th></tr></thead><tbody>
    <tr v-for="order in items" :key="order.id"><td><div><strong>{{ order.number }}</strong><small v-if="order.rental_quote_number">{{ order.rental_quote_number }}</small></div></td><td><div><strong>{{ order.equipment_name }}</strong><small>{{ order.symptoms }}</small></div></td><td>{{ order.maintenance_type_label }}</td><td><span class="maintenance-priority" :class="{ critical: order.priority === 'CRÍTICA', high: order.priority === 'ALTA' }">{{ order.priority }}</span></td><td>{{ order.technician_name || 'A definir' }}</td><td>{{ scheduledLabel(order.scheduled_at) }}</td><td><StatusBadge :value="order.status" :label="order.status_label" /></td><td class="right"><button type="button" class="icon-btn" :aria-label="`Abrir OS ${order.number}`" :title="`Abrir OS ${order.number}`" @click="$emit('open', order)"><Eye :size="18" /></button></td></tr>
    <tr v-if="!orders.length"><td colspan="8" class="empty-cell">Nenhuma OS encontrada com estes filtros.</td></tr>
  </tbody></table></div><PaginationBar v-model="page" :total="orders.length" /></div>
</template>
