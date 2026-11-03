<script setup>
import { formatPlate, formatNumber } from '../services/formatters'
import { computed, onMounted, reactive, ref } from 'vue'
import { Pencil, Plus, Search, Trash2, Truck } from 'lucide-vue-next'
import { api, apiError, can, fetchAll, rows } from '../services/api'
import { matchesSearch, sortRecords } from '../services/listFilters'
import { usePagination } from '../services/pagination'
import ModalDialog from '../components/ModalDialog.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
const vehicles = ref([]), search = ref(''), modal = ref(false), editing = ref(null), deleting = ref(null), busy = ref(false), error = ref('')
const form = reactive({ plate: '', brand: '', model: '', vehicle_type: 'PICKUP', capacity_kg: '', status: 'AVAILABLE', notes: '' })
const vehicleType = ref(''), vehicleStatus = ref(''), ordering = ref('plate')
const sortOptions = [['plate', 'Placa A–Z'], ['-plate', 'Placa Z–A'], ['model', 'Modelo A–Z'], ['-capacity', 'Maior capacidade'], ['capacity', 'Menor capacidade']]
const filtered = computed(() => sortRecords(vehicles.value.filter(item => matchesSearch(search.value, item.plate, item.brand, item.model) && (!vehicleType.value || item.vehicle_type === vehicleType.value) && (!vehicleStatus.value || (item.in_transit ? 'IN_TRANSIT' : item.status) === vehicleStatus.value)), ordering.value, { plate: item => item.plate, model: item => item.model, capacity: item => item.capacity_kg == null ? null : Number(item.capacity_kg) }))
const { items, page } = usePagination(filtered, [search, vehicleType, vehicleStatus, ordering])
function clearListFilters() { search.value = ''; vehicleType.value = ''; vehicleStatus.value = ''; ordering.value = 'plate' }
async function load() { try { vehicles.value = rows((await fetchAll('/vehicles/')).data) } catch (event) { error.value = apiError(event) } }
function open(item = null) {
  editing.value = item; error.value = ''; modal.value = true
  Object.assign(form, { plate: item?.plate || '', brand: item?.brand || '', model: item?.model || '', vehicle_type: item?.vehicle_type || 'PICKUP', capacity_kg: item?.capacity_kg ?? '', status: item?.status || 'AVAILABLE', notes: item?.notes || '' })
}
async function save() {
  busy.value = true; error.value = ''
  try {
    const payload = { ...form, capacity_kg: form.capacity_kg === '' ? null : form.capacity_kg }
    editing.value ? await api.patch(`/vehicles/${editing.value.id}/`, payload) : await api.post('/vehicles/', payload)
    modal.value = false; await load()
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}
async function remove() {
  busy.value = true
  try { await api.delete(`/vehicles/${deleting.value.id}/`); deleting.value = null; await load() }
  catch (event) { error.value = apiError(event); deleting.value = null }
  finally { busy.value = false }
}
onMounted(load)
</script>
<template>
  <div class="page"><header class="page-heading compact"><div><span class="eyebrow">CADASTROS</span><h1>Veículos</h1><p>Frota utilizada nas entregas e coletas.</p></div><button v-if="can('logistics.manage')" class="btn primary" @click="open()"><Plus :size="18" />Novo veículo</button></header><GeneralError v-if="error && !modal" :message="error" @close="error = ''" /><section class="panel list-panel"><ListToolbar><template #search><label class="list-control list-search"><span>Pesquisar</span><span class="search-box"><Search :size="17" /><input v-model="search" type="search" placeholder="Placa, marca ou modelo" aria-label="Pesquisar veículos" /></span></label></template><template #filters><label class="list-control"><span>Tipo de veículo</span><AppSelect v-model="vehicleType"><option value="">Todos</option><option value="PICKUP">Picape</option><option value="VAN">Van</option><option value="TRUCK">Caminhão</option><option value="OTHER">Outro</option></AppSelect></label><label class="list-control"><span>Situação</span><AppSelect v-model="vehicleStatus"><option value="">Todas</option><option value="AVAILABLE">Disponível</option><option value="IN_TRANSIT">Em viagem</option><option value="MAINTENANCE">Em manutenção</option><option value="INACTIVE">Inativo</option></AppSelect></label><ListOrdering v-model="ordering" :options="sortOptions" /></template><template #meta><div class="filter-meta"><span class="result-count">{{ filtered.length }} veículo(s)</span><button type="button" class="btn secondary" @click="clearListFilters">Limpar filtros</button></div></template></ListToolbar><div class="table-wrap"><table><thead><tr><th>Veículo</th><th>Tipo</th><th>Capacidade</th><th>Situação</th><th class="right">Ações</th></tr></thead><tbody><tr v-for="vehicle in items" :key="vehicle.id"><td><strong>{{ formatPlate(vehicle.plate) }}</strong><small>{{ vehicle.brand }} {{ vehicle.model }}</small></td><td>{{ vehicle.vehicle_type_label }}</td><td>{{ vehicle.capacity_kg ? `${formatNumber(vehicle.capacity_kg)} kg` : 'Não informada' }}</td><td><StatusBadge :value="vehicle.in_transit ? 'IN_TRANSIT' : vehicle.status" :label="vehicle.in_transit ? 'Em viagem' : vehicle.status_label" /></td><td class="right"><div v-if="can('logistics.manage')" class="row-actions"><button class="icon-btn" aria-label="Editar veículo" @click="open(vehicle)"><Pencil :size="16" /></button><button class="icon-btn danger-icon" aria-label="Excluir veículo" @click="deleting = vehicle"><Trash2 :size="16" /></button></div></td></tr><tr v-if="!items.length"><td colspan="5" class="empty-cell"><Truck :size="20" />Nenhum veículo encontrado.</td></tr></tbody></table></div><PaginationBar v-model="page" :total="filtered.length" /></section>
    <ModalDialog v-if="modal" :title="editing ? 'Editar veículo' : 'Novo veículo'" @close="modal = false; error = ''"><form @submit.prevent="save"><div class="form-grid"><div class="form-field"><label>Placa<span class="required-mark" aria-hidden="true"> *</span></label><AppInput mask="plate" v-model="form.plate" required placeholder="Ex.: ABC-1D23" /></div><div class="form-field"><label>Tipo<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect required v-model="form.vehicle_type"><option value="PICKUP">Picape</option><option value="VAN">Van</option><option value="TRUCK">Caminhão</option><option value="OTHER">Outro</option></AppSelect></div><div class="form-field"><label>Marca<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="form.brand" required placeholder="Ex.: Marca do fabricante" /></div><div class="form-field"><label>Modelo<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="form.model" required placeholder="Ex.: Modelo e versão do veículo" /></div><div class="form-field"><label>Capacidade (kg)</label><AppInput mask="decimal" :precision="2" v-model="form.capacity_kg" min="1" placeholder="Ex.: 1000" /></div><div class="form-field"><label>Situação<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect required v-model="form.status"><option value="AVAILABLE">Disponível</option><option value="MAINTENANCE">Em manutenção</option><option value="INACTIVE">Inativo</option></AppSelect></div><div class="form-field span-2"><label>Observações</label><textarea v-model="form.notes" rows="2" placeholder="Restrições de carga, características ou cuidados com o veículo" /></div></div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><span class="spacer" /><button class="btn primary" :disabled="busy">Salvar veículo</button></div></form></ModalDialog>
    <ConfirmDialog v-if="deleting" title="Excluir veículo" :message="`Excluir ${deleting.plate}? Veículos com viagens devem ser inativados.`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
  </div>
</template>
