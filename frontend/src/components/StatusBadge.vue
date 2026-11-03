<script setup>
const props = defineProps({ value: String, label: String })
const labels = {
  AVAILABLE:'Disponível', RESERVED:'Reservado', RENTED:'Locado', MAINTENANCE:'Em manutenção',
  INSPECTION:'Em inspeção', INACTIVE:'Inativo', ACTIVE:'Ativo', DRAFT:'Rascunho', SENT:'Enviado',
  APPROVED:'Aprovado', APPROVED_WITH_NOTES:'Aprovado com ressalvas', COMPLETED:'Concluído',
  RETURNED:'Devolvido', CANCELLED:'Cancelado', EXPIRED:'Expirado', PLANNED:'Planejado',
  IN_TRANSIT:'Em transporte', SCHEDULED:'Agendado', PENDING:'Pendente', OPEN:'Em aberto',
  IN_PROGRESS:'Em execução', WAITING_PARTS:'Aguardando peças', ABANDONED:'Abandonado',
  BLOCKED:'Impedido', CRITICAL:'Crítico', OVERDUE:'Vencido', UPCOMING:'Próximo do vencimento', OK:'Em dia',
}
const tone = () => {
  const value = props.value || ''
  if (['AVAILABLE', 'APPROVED', 'APPROVED_WITH_NOTES', 'COMPLETED', 'OK', 'ACTIVE'].includes(value)) return 'success'
  if (['MAINTENANCE', 'CRITICAL', 'OVERDUE', 'CANCELLED', 'INACTIVE', 'ABANDONED', 'BLOCKED'].includes(value)) return 'danger'
  if (['SENT', 'SCHEDULED', 'UPCOMING', 'RESERVED', 'RETURNED', 'PENDING', 'INSPECTION', 'PLANNED', 'IN_TRANSIT', 'IN_PROGRESS', 'WAITING_PARTS'].includes(value)) return 'warning'
  return 'neutral'
}
</script>
<template><span class="status-badge" :class="tone()"><i />{{ label || labels[value] || value }}</span></template>
