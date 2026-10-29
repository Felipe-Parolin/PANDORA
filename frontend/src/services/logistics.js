export const localDateTimeInput = value => {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
export const tripDay = trip => trip.scheduled_at ? localDateTimeInput(trip.scheduled_at).slice(0, 10)
  : trip.leg === 'DELIVERY' ? trip.rental_start_date : trip.rental_end_date
export const tripPending = trip => trip.status === 'PLANNED' || trip.workflow?.code === 'CONFIRM'
export const tripActionLabel = trip => trip.workflow?.code === 'CONFIRM' ? 'Confirmar na locação'
  : trip.status === 'IN_TRANSIT' ? trip.leg === 'DELIVERY' ? 'Registrar entrega' : 'Receber coleta'
    : trip.status === 'PLANNED' ? trip.workflow?.can_start ? 'Preparar saída' : 'Organizar viagem' : 'Ver detalhes'
