<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { CalendarClock, CheckCircle2, MapPin, Pencil, PlayCircle, Plus, RefreshCw, Search, Trash2, Truck } from 'lucide-vue-next'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import WorkflowFilterSelect from '../components/WorkflowFilterSelect.vue'
import TransportTripCard from '../components/TransportTripCard.vue'
import { api, apiError, can, money, rows, shortDate } from '../services/api'
import { localDateTimeInput, tripDay, tripPending } from '../services/logistics'

const route = useRoute()
const tab = ref('trips')
const queue = ref('PENDING')
const period = ref('ALL')
const loading = ref(false)
const search = ref('')
const trips = ref([])
const vehicles = ref([])
const employees = ref([])
const editingTrip = ref(null)
const editingVehicle = ref(null)
const deletingVehicle = ref(null)
const modal = ref(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const tripForm = reactive({ vehicle: '', driver: '', scheduled_at: '', notes: '' })
const vehicleForm = reactive({ plate: '', brand: '', model: '', vehicle_type: 'PICKUP', capacity_kg: '', status: 'AVAILABLE', notes: '' })
const today = () => localDateTimeInput(new Date()).slice(0, 10)
const inQueue = (trip, key) => key === 'ALL' || (key === 'PENDING' ? tripPending(trip) : key === 'COMPLETED' ? trip.status === 'COMPLETED' && !tripPending(trip) : trip.status === key)
const queues = computed(() => [
  { key: 'PENDING', label: 'A fazer' }, { key: 'IN_TRANSIT', label: 'Em viagem' },
  { key: 'COMPLETED', label: 'Concluídas' }, { key: 'ALL', label: 'Todas, incluindo canceladas' },
].map(item => ({ ...item, count: trips.value.filter(trip => inQueue(trip, item.key)).length })))
const visibleTrips = computed(() => trips.value.filter(trip => inQueue(trip, queue.value)).filter(trip => {
  const term = search.value.trim().toLocaleLowerCase('pt-BR')
  const day = tripDay(trip)
  const matchesPeriod = period.value === 'ALL' || period.value === 'TODAY' && day === today()
    || period.value === 'OVERDUE' && tripPending(trip) && day && day < today()
  return matchesPeriod && (!term || [trip.quote_number, trip.customer_name, trip.vehicle_plate, trip.driver_name, trip.address, ...trip.equipment.map(item => item.name)].some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(term)))
}))
const tripGroups = computed(() => {
  const keyFor = trip => trip.workflow?.code === 'CONFIRM' ? 'confirm' : trip.status === 'IN_TRANSIT' ? 'transit'
    : ['COMPLETED', 'CANCELLED'].includes(trip.status) ? 'history' : !trip.scheduled_at ? 'planning'
      : tripDay(trip) < today() ? 'overdue' : tripDay(trip) === today() ? 'today' : 'upcoming'
  return [
    { key: 'confirm', title: 'Falta confirmar na locação', hint: 'Viagens antigas já concluídas que ainda precisam atualizar a entrega ou devolução.' },
    { key: 'overdue', title: 'Em atraso', hint: 'Programações que passaram do dia previsto.' },
    { key: 'today', title: 'Hoje', hint: 'Entregas e coletas programadas para o dia.' },
    { key: 'transit', title: 'Em viagem', hint: 'Acompanhe a entrega ou aguarde o retorno ao depósito.' },
    { key: 'planning', title: 'A programar', hint: 'Defina veículo, motorista e horário. O bloqueio da manutenção não impede o planejamento.' },
    { key: 'upcoming', title: 'Próximas viagens', hint: 'Programação dos próximos dias.' },
    { key: 'history', title: 'Histórico', hint: 'Entregas e coletas encerradas.' },
  ].map(group => ({ ...group, trips: visibleTrips.value.filter(trip => keyFor(trip) === group.key).sort((a, b) => (a.scheduled_at || tripDay(a) || '').localeCompare(b.scheduled_at || tripDay(b) || '')) })).filter(group => group.trips.length)
})
const tripEditable = computed(() => can('logistics.manage') && editingTrip.value?.status === 'PLANNED')
const tripDirty = computed(() => editingTrip.value && [
  [tripForm.vehicle, editingTrip.value.vehicle || ''], [tripForm.driver, editingTrip.value.driver || ''],
  [tripForm.scheduled_at, localDateTimeInput(editingTrip.value.scheduled_at)], [tripForm.notes, editingTrip.value.notes || ''],
].some(([current, saved]) => String(current) !== String(saved)))
const canConfirmRental = trip => can(trip.leg === 'DELIVERY' ? 'rentals.dispatch' : 'rentals.return')

async function allRows(path) {
  const result = []
  for (let page = 1; ; page++) {
    const { data } = await api.get(path, { params: { page } })
    result.push(...rows(data))
    if (!data.next) return result
  }
}

async function load() {
  loading.value = true
  try {
    const [tripData, vehicleData, driverData] = await Promise.all([
      allRows('/transport-tasks/'), allRows('/vehicles/'),
      can('logistics.manage') ? api.get('/transport-tasks/drivers/').then(response => response.data) : [],
    ])
    trips.value = tripData
    vehicles.value = vehicleData
    employees.value = driverData
  } finally { loading.value = false }
}
async function refresh() { try { await load() } catch (event) { error.value = apiError(event) } }
const refreshOnFocus = () => { if (!modal.value && !busy.value && !loading.value) refresh() }

function openTrip(trip) {
  editingTrip.value = trip
  error.value = ''
  modal.value = 'trip'
  Object.assign(tripForm, {
    vehicle: trip.vehicle || '', driver: trip.driver || '',
    scheduled_at: localDateTimeInput(trip.scheduled_at), notes: trip.notes || '',
  })
}

function openVehicle(vehicle = null) {
  editingVehicle.value = vehicle
  error.value = ''
  modal.value = 'vehicle'
  Object.assign(vehicleForm, vehicle ? {
    plate: vehicle.plate, brand: vehicle.brand, model: vehicle.model,
    vehicle_type: vehicle.vehicle_type, capacity_kg: vehicle.capacity_kg ?? '',
    status: vehicle.status, notes: vehicle.notes || '',
  } : { plate: '', brand: '', model: '', vehicle_type: 'PICKUP', capacity_kg: '', status: 'AVAILABLE', notes: '' })
}

async function saveTrip() {
  busy.value = true
  error.value = ''
  try {
    await api.patch(`/transport-tasks/${editingTrip.value.id}/`, {
      vehicle: tripForm.vehicle || null, driver: tripForm.driver || null,
      scheduled_at: tripForm.scheduled_at || null, notes: tripForm.notes,
    })
    notice.value = 'Viagem planejada.'
    await load()
    openTrip(trips.value.find(trip => trip.id === editingTrip.value.id))
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}

async function saveVehicle() {
  busy.value = true
  error.value = ''
  try {
    const payload = { ...vehicleForm, capacity_kg: vehicleForm.capacity_kg || null }
    editingVehicle.value
      ? await api.patch(`/vehicles/${editingVehicle.value.id}/`, payload)
      : await api.post('/vehicles/', payload)
    modal.value = null
    notice.value = 'Veículo salvo.'
    await load()
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}

async function transition(trip, action) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const advance = action === 'complete' && canConfirmRental(trip)
    await api.post(`/transport-tasks/${trip.id}/${action}/`, { advance_rental: advance })
    notice.value = action === 'start' ? 'Saída registrada. A viagem está em andamento.' : advance
      ? trip.leg === 'DELIVERY' ? 'Entrega confirmada e locação iniciada. Se contratada, a coleta já aparece na fila.' : 'Retorno confirmado e devolução registrada. A inspeção final foi aberta na Manutenção.'
      : 'Viagem concluída. Um usuário autorizado deve confirmar a entrega ou devolução na locação.'
    modal.value = null
    queue.value = action === 'start' ? 'IN_TRANSIT' : 'PENDING'
    await load()
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}

async function confirmRental(trip) {
  busy.value = true
  error.value = ''
  try {
    await api.post(`/rental-quotes/${trip.quote}/${trip.leg === 'DELIVERY' ? 'deliver' : 'return'}/`)
    modal.value = null
    notice.value = trip.leg === 'DELIVERY' ? 'Entrega confirmada na locação.' : 'Devolução registrada e inspeção final aberta na Manutenção.'
    await load()
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}

async function removeVehicle() {
  busy.value = true
  error.value = ''
  try {
    await api.delete(`/vehicles/${deletingVehicle.value.id}/`)
    deletingVehicle.value = null
    notice.value = 'Veículo excluído.'
    await load()
  } catch (event) { error.value = apiError(event); deletingVehicle.value = null }
  finally { busy.value = false }
}

onMounted(async () => {
  window.addEventListener('focus', refreshOnFocus)
  try {
    await load()
    if (route.query.quote) { search.value = String(route.query.quote); queue.value = 'ALL' }
  } catch (event) { error.value = apiError(event) }
})
onBeforeUnmount(() => window.removeEventListener('focus', refreshOnFocus))
</script>

<template>
  <div class="page">
    <header class="page-heading compact"><div><span class="eyebrow">ENTREGAS E COLETAS</span><h1>Transporte</h1><p>Organize a saída, confirme a entrega e acompanhe o retorno ao depósito.</p></div><button v-if="tab === 'trips'" class="btn secondary" :disabled="loading" @click="refresh"><RefreshCw :size="17" />{{ loading ? 'Atualizando...' : 'Atualizar' }}</button><button v-else-if="can('logistics.manage')" class="btn primary" @click="openVehicle()"><Plus :size="18" />Cadastrar veículo</button></header>
    <div v-if="notice" class="success-strip">{{ notice }}</div>
    <div v-if="error && !modal" class="floating-error">{{ error }}</div>
    <div class="tabs section-tabs"><button :class="{ active: tab === 'trips' }" @click="tab = 'trips'"><MapPin :size="17" />Viagens</button><button :class="{ active: tab === 'vehicles' }" @click="tab = 'vehicles'"><Truck :size="17" />Veículos</button></div>

    <template v-if="tab === 'trips'">
      <section class="panel dispatch-toolbar" aria-label="Filtros de transporte">
        <div class="search-box"><Search :size="17" /><input v-model="search" placeholder="Cliente, locação, endereço ou equipamento" aria-label="Pesquisar viagens" /></div>
        <WorkflowFilterSelect v-model="queue" :options="queues" label="Situação da viagem" />
        <label class="workflow-filter"><span>Período</span><select v-model="period"><option value="ALL">Todos os dias</option><option value="TODAY">Hoje</option><option value="OVERDUE">Em atraso</option></select></label>
      </section>
      <p class="dispatch-results" aria-live="polite">{{ visibleTrips.length }} viagem(ns) · {{ visibleTrips.filter(trip => trip.leg === 'DELIVERY').length }} entrega(s) · {{ visibleTrips.filter(trip => trip.leg === 'RETURN').length }} coleta(s)</p>
      <section v-for="group in tripGroups" :key="group.key" class="dispatch-group"><header><h2>{{ group.title }} <span>{{ group.trips.length }}</span></h2><p>{{ group.hint }}</p></header><div class="dispatch-grid"><TransportTripCard v-for="trip in group.trips" :key="trip.id" :trip="trip" :can-manage="can('logistics.manage')" @open="openTrip" /></div></section>
      <div v-if="!visibleTrips.length" class="panel empty-state compact"><Truck :size="28" /><h2>{{ loading ? 'Carregando viagens...' : 'Nenhuma viagem neste filtro' }}</h2><p v-if="!loading">As entregas aparecem ao aprovar uma locação com transporte. As coletas entram na fila após a entrega ao cliente.</p></div>
    </template>

    <section v-else class="panel list-panel">
      <div class="table-wrap desktop-list"><table><thead><tr><th>Placa</th><th>Veículo</th><th>Capacidade</th><th>Situação</th><th class="right">Ações</th></tr></thead><tbody><tr v-for="vehicle in vehicles" :key="vehicle.id"><td><strong>{{ vehicle.plate }}</strong></td><td><strong>{{ vehicle.brand }} {{ vehicle.model }}</strong><small>{{ vehicle.vehicle_type_label }}</small></td><td>{{ vehicle.capacity_kg ? `${vehicle.capacity_kg} kg` : 'Não informada' }}</td><td><StatusBadge :value="vehicle.in_transit ? 'IN_TRANSIT' : vehicle.status" :label="vehicle.in_transit ? 'Em viagem' : vehicle.status_label" /></td><td class="right"><div class="row-actions"><button v-if="can('logistics.manage')" class="icon-btn table-action" title="Editar veículo" @click="openVehicle(vehicle)"><Pencil :size="17" /></button><button v-if="can('logistics.manage')" class="icon-btn danger-icon" title="Excluir veículo" @click="deletingVehicle = vehicle"><Trash2 :size="17" /></button></div></td></tr><tr v-if="!vehicles.length"><td colspan="5" class="empty-cell">Nenhum veículo cadastrado.</td></tr></tbody></table></div>
      <div class="mobile-card-list"><article v-for="vehicle in vehicles" :key="vehicle.id" class="mobile-record-card"><header><div><span class="eyebrow">{{ vehicle.plate }} · {{ vehicle.vehicle_type_label }}</span><strong>{{ vehicle.brand }} {{ vehicle.model }}</strong></div><StatusBadge :value="vehicle.in_transit ? 'IN_TRANSIT' : vehicle.status" :label="vehicle.in_transit ? 'Em viagem' : vehicle.status_label" /></header><dl><div><dt>Capacidade</dt><dd>{{ vehicle.capacity_kg ? `${vehicle.capacity_kg} kg` : 'Não informada' }}</dd></div></dl><footer><button v-if="can('logistics.manage')" class="btn secondary" @click="openVehicle(vehicle)"><Pencil :size="16" />Editar</button><button v-if="can('logistics.manage')" class="btn secondary" @click="deletingVehicle = vehicle"><Trash2 :size="16" />Excluir</button></footer></article><div v-if="!vehicles.length" class="empty-state compact"><Truck :size="26" /><h2>Nenhum veículo cadastrado</h2></div></div>
    </section>

    <ModalDialog v-if="modal === 'trip'" :title="`${editingTrip.leg === 'DELIVERY' ? 'Entrega' : 'Coleta'} · ${editingTrip.quote_number}`" wide @close="modal = null"><form @submit.prevent="saveTrip">
      <div class="dispatch-detail-heading"><div><span class="eyebrow">{{ editingTrip.leg === 'DELIVERY' ? 'DEPÓSITO → CLIENTE' : 'CLIENTE → DEPÓSITO' }}</span><h3>{{ editingTrip.customer_name }}</h3></div><span class="dispatch-status" :class="editingTrip.workflow.code.toLowerCase()">{{ editingTrip.workflow.label }}</span></div>
      <div class="dispatch-detail-route"><MapPin :size="20" /><div><strong>{{ editingTrip.address }}</strong><p v-if="editingTrip.complement">{{ editingTrip.complement }}</p><small v-if="editingTrip.contact_phone">Contato: {{ editingTrip.contact_phone }}</small></div></div>
      <div class="dispatch-detail-equipment"><span class="eyebrow">EQUIPAMENTOS DA LOCAÇÃO</span><span v-for="item in editingTrip.equipment" :key="item.id">{{ item.code }} · {{ item.name }}</span></div>
      <dl class="inspection-equipment-details"><div><dt>{{ editingTrip.leg === 'DELIVERY' ? 'Entrega prevista na locação' : 'Devolução prevista na locação' }}</dt><dd>{{ shortDate(editingTrip.leg === 'DELIVERY' ? editingTrip.rental_start_date : editingTrip.rental_end_date) }}</dd></div><div><dt>{{ editingTrip.freight_cost == null ? 'Transporte total do orçamento' : 'Custo deste trajeto' }}</dt><dd>{{ money(editingTrip.freight_cost ?? editingTrip.transport_total) }}</dd></div></dl>
      <div class="dispatch-guidance"><strong>{{ editingTrip.workflow.label }}</strong><p>{{ editingTrip.workflow.detail }}</p><RouterLink v-if="editingTrip.workflow.label === 'Aguardando manutenção' && can('maintenance.view')" :to="{ path: '/manutencao', query: { quote: editingTrip.quote_number } }">Acompanhar liberação na manutenção</RouterLink></div>
      <div v-if="tripEditable" class="form-grid transport-form">
        <div class="form-field"><label for="trip-vehicle">Veículo</label><select id="trip-vehicle" v-model="tripForm.vehicle" required><option value="">Selecione o veículo</option><option v-for="vehicle in vehicles" :key="vehicle.id" :value="vehicle.id" :disabled="vehicle.status !== 'AVAILABLE' || vehicle.in_transit">{{ vehicle.plate }} · {{ vehicle.brand }} {{ vehicle.model }}{{ vehicle.in_transit ? ' (em viagem)' : vehicle.status !== 'AVAILABLE' ? ' (indisponível)' : '' }}</option></select></div>
        <div class="form-field"><label for="trip-driver">Motorista</label><select id="trip-driver" v-model="tripForm.driver" required><option value="">Selecione o motorista</option><option v-for="user in employees" :key="user.id" :value="user.id" :disabled="user.in_transit">{{ user.full_name }}{{ user.in_transit ? ' (em viagem)' : '' }}</option><option v-if="editingTrip.driver && !employees.some(user => user.id === editingTrip.driver)" :value="editingTrip.driver" disabled>{{ editingTrip.driver_name }} (indisponível)</option></select></div>
        <div class="form-field span-2"><label for="trip-schedule">Saída programada</label><input id="trip-schedule" v-model="tripForm.scheduled_at" type="datetime-local" required /><small>Horário local. A data da locação aparece acima como referência.</small></div>
        <details class="quote-extra span-2"><summary>Instruções para a viagem (opcional)</summary><div class="form-field"><label for="trip-instructions">Acesso e cuidados com a carga</label><textarea id="trip-instructions" v-model="tripForm.notes" rows="3" placeholder="Portão de acesso, contato no local ou cuidados com o equipamento." /></div></details>
      </div>
      <dl v-else class="inspection-equipment-details"><div><dt>Veículo</dt><dd>{{ editingTrip.vehicle_plate || 'Não atribuído' }}</dd></div><div><dt>Motorista</dt><dd>{{ editingTrip.driver_name || 'Não atribuído' }}</dd></div><div v-if="editingTrip.completed_at"><dt>Concluída em</dt><dd>{{ new Date(editingTrip.completed_at).toLocaleString('pt-BR') }}</dd></div></dl>
      <p v-if="editingTrip.status === 'IN_TRANSIT'" class="dispatch-completion-hint">{{ canConfirmRental(editingTrip) ? editingTrip.leg === 'DELIVERY' ? 'Ao confirmar a entrega ao cliente, a locação será iniciada e a coleta contratada será criada automaticamente.' : 'Confirme somente após receber os equipamentos no depósito. A devolução será registrada e a inspeção final será aberta na Manutenção.' : 'Sua permissão permite concluir a viagem. A confirmação na locação ficará para um usuário autorizado.' }}</p>
      <div v-if="error" class="error-message">{{ error }}</div>
      <div class="modal-actions"><button type="button" class="btn secondary" :disabled="busy" @click="modal = null">Fechar</button><RouterLink v-if="can('rentals.view')" class="text-action" :to="{ path: '/locacoes', query: { quote: editingTrip.quote_number } }">Ver locação</RouterLink><span class="spacer" />
        <button v-if="tripEditable && (!editingTrip.workflow.can_start || tripDirty)" class="btn primary" :disabled="busy"><CalendarClock :size="16" />{{ busy ? 'Salvando...' : 'Salvar planejamento' }}</button>
        <button v-else-if="tripEditable && editingTrip.workflow.can_start" type="button" class="btn primary" :disabled="busy" @click="transition(editingTrip, 'start')"><PlayCircle :size="16" />{{ busy ? 'Registrando...' : 'Iniciar viagem' }}</button>
        <button v-else-if="can('logistics.manage') && editingTrip.status === 'IN_TRANSIT'" type="button" class="btn primary" :disabled="busy" @click="transition(editingTrip, 'complete')"><CheckCircle2 :size="16" />{{ busy ? 'Confirmando...' : canConfirmRental(editingTrip) ? editingTrip.leg === 'DELIVERY' ? 'Confirmar entrega no cliente' : 'Receber no depósito' : 'Concluir somente viagem' }}</button>
        <button v-else-if="editingTrip.workflow.code === 'CONFIRM' && canConfirmRental(editingTrip)" type="button" class="btn primary" :disabled="busy" @click="confirmRental(editingTrip)">{{ busy ? 'Confirmando...' : editingTrip.leg === 'DELIVERY' ? 'Confirmar entrega da locação' : 'Confirmar devolução' }}</button>
      </div>
    </form></ModalDialog>

    <ModalDialog v-if="modal === 'vehicle'" :title="editingVehicle ? 'Editar veículo' : 'Cadastrar veículo'" wide @close="modal = null"><form @submit.prevent="saveVehicle"><div class="form-grid">
      <div class="form-field"><label>Placa</label><input v-model="vehicleForm.plate" required maxlength="8" placeholder="ABC1D23" /></div>
      <div class="form-field"><label>Tipo</label><select v-model="vehicleForm.vehicle_type"><option value="PICKUP">Picape</option><option value="VAN">Van</option><option value="TRUCK">Caminhão</option><option value="OTHER">Outro</option></select></div>
      <div class="form-field"><label>Marca</label><input v-model="vehicleForm.brand" required /></div><div class="form-field"><label>Modelo</label><input v-model="vehicleForm.model" required /></div>
      <div class="form-field"><label>Capacidade (kg)</label><input v-model="vehicleForm.capacity_kg" type="number" min="1" /></div><div class="form-field"><label>Situação</label><select v-model="vehicleForm.status"><option value="AVAILABLE">Disponível</option><option value="MAINTENANCE">Em manutenção</option><option value="INACTIVE">Inativo</option></select></div>
      <div class="form-field span-2"><label>Observações</label><textarea v-model="vehicleForm.notes" rows="3" placeholder="Restrições, documentação ou detalhes úteis para a operação." /></div>
    </div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy">{{ busy ? 'Salvando...' : 'Salvar veículo' }}</button></div></form></ModalDialog>
    <ConfirmDialog v-if="deletingVehicle" title="Excluir veículo" :message="`Excluir ${deletingVehicle.plate}? Veículos com viagens registradas devem ser inativados.`" :busy="busy" @cancel="deletingVehicle = null" @confirm="removeVehicle" />
  </div>
</template>
