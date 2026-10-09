<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { CalendarClock, CheckCircle2, ClipboardList, MapPin, Pencil, PlayCircle, Plus, Search, Trash2, Truck } from 'lucide-vue-next'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api, apiError, can, rows, shortDate } from '../services/api'

const route = useRoute()
const tab = ref('trips')
const queue = ref('ALL')
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

const tripForm = reactive({ vehicle: '', driver: '', address: '', complement: '', scheduled_at: '', notes: '' })
const vehicleForm = reactive({ plate: '', brand: '', model: '', vehicle_type: 'PICKUP', capacity_kg: '', status: 'AVAILABLE', notes: '' })
const queues = computed(() => [
  { key: 'ALL', label: 'Todas' }, { key: 'PLANNED', label: 'A planejar' },
  { key: 'IN_TRANSIT', label: 'Em transporte' }, { key: 'COMPLETED', label: 'Concluídas' },
  { key: 'CANCELLED', label: 'Canceladas' },
].map(item => ({ ...item, count: trips.value.filter(trip => item.key === 'ALL' || trip.status === item.key).length })))
const visibleTrips = computed(() => trips.value.filter(trip => queue.value === 'ALL' || trip.status === queue.value).filter(trip => {
  const term = search.value.trim().toLocaleLowerCase('pt-BR')
  return !term || [trip.quote_number, trip.customer_name, trip.vehicle_plate, trip.driver_name].some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(term))
}))
const availableVehicles = computed(() => vehicles.value.filter(vehicle => vehicle.status === 'AVAILABLE' && !vehicle.in_transit))

async function load() {
  const [tripResponse, vehicleResponse, userResponse] = await Promise.all([
    api.get('/transport-tasks/'), api.get('/vehicles/'),
    can('accounts.users.view') ? api.get('/users/') : Promise.resolve({ data: [] }),
  ])
  trips.value = rows(tripResponse.data)
  vehicles.value = rows(vehicleResponse.data)
  employees.value = rows(userResponse.data).filter(user => user.is_active)
}

function openTrip(trip) {
  editingTrip.value = trip
  error.value = ''
  modal.value = 'trip'
  Object.assign(tripForm, {
    vehicle: trip.vehicle || '', driver: trip.driver || '', address: trip.address, complement: trip.complement || '',
    scheduled_at: trip.scheduled_at?.slice(0, 16) || '', notes: trip.notes || '',
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
      address: tripForm.address.trim(), complement: tripForm.complement.trim(), scheduled_at: tripForm.scheduled_at || null, notes: tripForm.notes,
    })
    modal.value = null
    notice.value = 'Viagem planejada.'
    await load()
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
    await api.post(`/transport-tasks/${trip.id}/${action}/`)
    notice.value = action === 'start' ? 'Viagem iniciada.' : 'Viagem concluída. A locação pode avançar para a próxima etapa.'
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
  try {
    await load()
    if (route.query.quote) search.value = String(route.query.quote)
  } catch (event) { error.value = apiError(event) }
})
</script>

<template>
  <div class="page">
    <header class="page-heading compact"><div><span class="eyebrow">MOVIMENTAÇÃO DE EQUIPAMENTOS</span><h1>Transporte</h1><p>Planeje entregas e coletas apenas quando a locação precisar de veículo.</p></div><button v-if="tab === 'vehicles' && can('logistics.manage')" class="btn primary" @click="openVehicle()"><Plus :size="18" />Cadastrar veículo</button></header>
    <div v-if="notice" class="success-strip">{{ notice }}</div>
    <div v-if="error && !modal" class="floating-error">{{ error }}</div>
    <section class="transport-flow"><span><ClipboardList :size="17" />Reserva</span><i /><span>Inspeção e manutenção</span><i /><span><Truck :size="17" />Transporte, se necessário</span><i /><span>Entrega / devolução</span></section>
    <div class="tabs section-tabs"><button :class="{ active: tab === 'trips' }" @click="tab = 'trips'"><MapPin :size="17" />Viagens</button><button :class="{ active: tab === 'vehicles' }" @click="tab = 'vehicles'"><Truck :size="17" />Veículos</button></div>

    <template v-if="tab === 'trips'">
      <div class="workflow-tabs" role="tablist" aria-label="Filtrar viagens"><button v-for="item in queues" :key="item.key" :class="{ active: queue === item.key }" @click="queue = item.key"><span>{{ item.label }}</span><b>{{ item.count }}</b></button></div>
      <section class="panel list-panel">
        <header class="list-toolbar"><div class="search-box"><Search :size="17" /><input v-model="search" placeholder="Buscar reserva, cliente ou placa" /></div><span class="result-count">{{ visibleTrips.length }} viagem(ns)</span></header>
        <div class="table-wrap desktop-list"><table><thead><tr><th>Locação</th><th>Trajeto</th><th>Agendamento</th><th>Veículo / motorista</th><th>Status</th><th class="right">Ações</th></tr></thead><tbody>
          <tr v-for="trip in visibleTrips" :key="trip.id"><td><strong>{{ trip.quote_number }}</strong><small>{{ trip.customer_name }}</small></td><td><strong>{{ trip.leg_label }}</strong><small>{{ trip.address }}<template v-if="trip.complement"> · {{ trip.complement }}</template></small></td><td>{{ trip.scheduled_at ? shortDate(trip.scheduled_at.slice(0, 10)) : 'A definir' }}</td><td><strong>{{ trip.vehicle_plate || 'Sem veículo' }}</strong><small>{{ trip.driver_name || 'Sem motorista' }}</small></td><td><StatusBadge :value="trip.status" :label="trip.status_label" /></td><td class="right"><div class="row-actions"><button v-if="can('logistics.manage') && trip.status === 'PLANNED'" class="icon-btn table-action" title="Planejar viagem" @click="openTrip(trip)"><Pencil :size="17" /></button><button v-if="can('logistics.manage') && trip.status === 'PLANNED'" class="icon-btn success-action" title="Iniciar transporte" :disabled="busy" @click="transition(trip, 'start')"><PlayCircle :size="17" /></button><button v-if="can('logistics.manage') && trip.status === 'IN_TRANSIT'" class="icon-btn success-action" title="Concluir transporte" :disabled="busy" @click="transition(trip, 'complete')"><CheckCircle2 :size="17" /></button></div></td></tr>
          <tr v-if="!visibleTrips.length"><td colspan="6" class="empty-cell"><Truck :size="20" />Nenhuma viagem nesta fila.</td></tr>
        </tbody></table></div>
        <div class="mobile-card-list"><article v-for="trip in visibleTrips" :key="trip.id" class="mobile-record-card"><header><div><span class="eyebrow">{{ trip.quote_number }} · {{ trip.leg_label }}</span><strong>{{ trip.customer_name }}</strong></div><StatusBadge :value="trip.status" :label="trip.status_label" /></header><p class="trip-address"><MapPin :size="15" />{{ trip.address }}<template v-if="trip.complement"> · {{ trip.complement }}</template></p><dl><div><dt>Agendamento</dt><dd>{{ trip.scheduled_at ? shortDate(trip.scheduled_at.slice(0, 10)) : 'A definir' }}</dd></div><div><dt>Veículo</dt><dd>{{ trip.vehicle_plate || 'Não atribuído' }}</dd></div><div><dt>Motorista</dt><dd>{{ trip.driver_name || 'Não atribuído' }}</dd></div></dl><footer><button v-if="can('logistics.manage') && trip.status === 'PLANNED'" class="btn secondary" @click="openTrip(trip)"><CalendarClock :size="16" />Planejar</button><button v-if="can('logistics.manage') && trip.status === 'PLANNED'" class="btn primary" :disabled="busy" @click="transition(trip, 'start')"><PlayCircle :size="16" />Iniciar</button><button v-if="can('logistics.manage') && trip.status === 'IN_TRANSIT'" class="btn primary" :disabled="busy" @click="transition(trip, 'complete')"><CheckCircle2 :size="16" />Concluir</button></footer></article><div v-if="!visibleTrips.length" class="empty-state compact"><Truck :size="26" /><h2>Nenhuma viagem nesta fila</h2></div></div>
      </section>
    </template>

    <section v-else class="panel list-panel">
      <div class="table-wrap desktop-list"><table><thead><tr><th>Placa</th><th>Veículo</th><th>Capacidade</th><th>Situação</th><th class="right">Ações</th></tr></thead><tbody><tr v-for="vehicle in vehicles" :key="vehicle.id"><td><strong>{{ vehicle.plate }}</strong></td><td><strong>{{ vehicle.brand }} {{ vehicle.model }}</strong><small>{{ vehicle.vehicle_type_label }}</small></td><td>{{ vehicle.capacity_kg ? `${vehicle.capacity_kg} kg` : 'Não informada' }}</td><td><StatusBadge :value="vehicle.in_transit ? 'IN_TRANSIT' : vehicle.status" :label="vehicle.in_transit ? 'Em viagem' : vehicle.status_label" /></td><td class="right"><div class="row-actions"><button v-if="can('logistics.manage')" class="icon-btn table-action" title="Editar veículo" @click="openVehicle(vehicle)"><Pencil :size="17" /></button><button v-if="can('logistics.manage')" class="icon-btn danger-icon" title="Excluir veículo" @click="deletingVehicle = vehicle"><Trash2 :size="17" /></button></div></td></tr><tr v-if="!vehicles.length"><td colspan="5" class="empty-cell">Nenhum veículo cadastrado.</td></tr></tbody></table></div>
      <div class="mobile-card-list"><article v-for="vehicle in vehicles" :key="vehicle.id" class="mobile-record-card"><header><div><span class="eyebrow">{{ vehicle.plate }} · {{ vehicle.vehicle_type_label }}</span><strong>{{ vehicle.brand }} {{ vehicle.model }}</strong></div><StatusBadge :value="vehicle.in_transit ? 'IN_TRANSIT' : vehicle.status" :label="vehicle.in_transit ? 'Em viagem' : vehicle.status_label" /></header><dl><div><dt>Capacidade</dt><dd>{{ vehicle.capacity_kg ? `${vehicle.capacity_kg} kg` : 'Não informada' }}</dd></div></dl><footer><button v-if="can('logistics.manage')" class="btn secondary" @click="openVehicle(vehicle)"><Pencil :size="16" />Editar</button><button v-if="can('logistics.manage')" class="btn secondary" @click="deletingVehicle = vehicle"><Trash2 :size="16" />Excluir</button></footer></article><div v-if="!vehicles.length" class="empty-state compact"><Truck :size="26" /><h2>Nenhum veículo cadastrado</h2></div></div>
    </section>

    <ModalDialog v-if="modal === 'trip'" :title="`Planejar ${editingTrip.leg_label.toLowerCase()} · ${editingTrip.quote_number}`" wide @close="modal = null"><form @submit.prevent="saveTrip"><div class="operation-context"><span class="eyebrow">{{ editingTrip.customer_name }}</span><strong>{{ editingTrip.leg_label }}</strong><small>{{ editingTrip.address }}<template v-if="editingTrip.complement"> · {{ editingTrip.complement }}</template></small></div><div class="form-grid transport-form">
      <div class="form-field"><label>Veículo</label><select v-model="tripForm.vehicle" required><option value="">Selecione</option><option v-for="vehicle in vehicles.filter(item => availableVehicles.some(available => available.id === item.id) || item.id === editingTrip.vehicle)" :key="vehicle.id" :value="vehicle.id">{{ vehicle.plate }} · {{ vehicle.brand }} {{ vehicle.model }}</option></select></div>
      <div class="form-field"><label>Motorista</label><select v-model="tripForm.driver" required><option value="">Selecione</option><option v-for="user in employees" :key="user.id" :value="user.id">{{ user.full_name }}</option></select></div>
      <div class="form-field"><label>Data e hora</label><input v-model="tripForm.scheduled_at" type="datetime-local" required /></div>
      <div class="form-field"><label>Endereço da entrega / coleta</label><input v-model="tripForm.address" required /></div>
      <div class="form-field span-2"><label>Complemento (opcional)</label><input v-model="tripForm.complement" maxlength="120" placeholder="Bloco, apartamento, portão ou ponto de referência" /></div>
      <div class="form-field span-2"><label>Instruções de transporte</label><textarea v-model="tripForm.notes" rows="3" placeholder="Contato no local, acesso, carga ou cuidados com o equipamento." /></div>
    </div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy">{{ busy ? 'Salvando...' : 'Salvar viagem' }}</button></div></form></ModalDialog>

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
