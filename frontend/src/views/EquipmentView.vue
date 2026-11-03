<script setup>
import { matchesSearch, sortRecords } from '../services/listFilters'
import { usePagination } from '../services/pagination'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ClipboardList, Files, PackageSearch, Pencil, Plus, QrCode, Search, SlidersHorizontal, Trash2, X } from 'lucide-vue-next'
import ChecklistItemsEditor from '../components/ChecklistItemsEditor.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EquipmentMediaModal from '../components/EquipmentMediaModal.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api, apiError, can, money, rows, fetchAll } from '../services/api'

const route = useRoute(), router = useRouter()
const equipment = ref([]), categories = ref([]), search = ref(''), status = ref(''), category = ref(''), subcategory = ref(''), brand = ref(''), model = ref(''), ordering = ref('code'), totalCount = ref(0), startDate = ref(''), endDate = ref(''), modal = ref(false), categoryModal = ref(false), editing = ref(null), deleting = ref(null), mediaEquipment = ref(null), qrEquipment = ref(null), qrUrl = ref(''), scanNotice = ref(''), error = ref(''), busy = ref(false)
const form = reactive({ category: '', name: '', brand: '', model: '', serial_number: '', internal_code: '', status: 'AVAILABLE', daily_rate: '', estimated_weight_kg: '', technical_details: '', current_usage_hours: 0 })
const tab = ref('equipment'), categorySearch = ref('')
const categoryKind = ref(''), categoryParent = ref(''), categoryOrdering = ref('name')
const equipmentSortOptions = [['code', 'Código'], ['name', 'Nome A–Z'], ['-name', 'Nome Z–A'], ['category', 'Categoria'], ['daily_rate', 'Menor diária'], ['-daily_rate', 'Maior diária'], ['usage', 'Maior utilização'], ['rentals', 'Mais locações'], ['-created', 'Mais recentes'], ['created', 'Mais antigos'], ['status', 'Situação']]
const categorySortOptions = [['name', 'Nome A–Z'], ['-name', 'Nome Z–A'], ['parent', 'Categoria superior'], ['-checks', 'Mais verificações']]
const filteredCategories = computed(() => sortRecords(categories.value.filter(item => matchesSearch(categorySearch.value, item.name, item.parent_name, item.description) && (!categoryKind.value || Boolean(item.parent) === (categoryKind.value === 'child')) && (!categoryParent.value || String(item.parent) === categoryParent.value)), categoryOrdering.value, { name: item => item.name, parent: item => item.parent_name, checks: item => (item.pre_rental_checklist?.length || 0) + (item.return_checklist?.length || 0) }))
function clearCategoryFilters() { categorySearch.value = ''; categoryKind.value = ''; categoryParent.value = ''; categoryOrdering.value = 'name' }
const categoryForm = reactive({ id: '', name: '', description: '', parent: '', pre_rental_checklist: [], return_checklist: [] })
const filtered = computed(() => equipment.value)
const showMore = ref(false)
const subcategoryOptions = computed(() => categories.value.filter(item => item.parent && (!category.value || Number(item.parent) === Number(category.value))))
const advancedCount = computed(() => [brand.value, model.value, startDate.value, endDate.value].filter(Boolean).length)
const hasFilters = computed(() => Boolean(search.value || status.value || category.value || subcategory.value) || advancedCount.value > 0 || ordering.value !== 'code')
const halfDateRange = computed(() => Boolean(startDate.value) !== Boolean(endDate.value))
function clearFilters() {
  search.value = ''; status.value = ''; category.value = ''; subcategory.value = ''; brand.value = ''; model.value = ''; startDate.value = ''; endDate.value = ''; ordering.value = 'code'
}

async function loadCategories() {
  const result = []
  let next = true, page = 1
  while (next) {
    const { data } = await fetchAll('/categories/', { params: { page } })
    result.push(...rows(data)); next = Boolean(data.next); page += 1
  }
  return result
}

let loadRequest = 0
async function load() {
  const request = ++loadRequest
  const [e, c] = await Promise.all([
    fetchAll('/equipment/', { params: { search: search.value || undefined, status: status.value || undefined, category: category.value || undefined, subcategory: subcategory.value || undefined, brand: brand.value || undefined, model: model.value || undefined, start_date: startDate.value && endDate.value ? startDate.value : undefined, end_date: startDate.value && endDate.value ? endDate.value : undefined, ordering: ordering.value } }),
    loadCategories(),
  ])
  if (request !== loadRequest) return
  equipment.value = rows(e.data)
  totalCount.value = e.data?.count ?? equipment.value.length
  categories.value = c
}
let filterTimer
watch([search, status, category, subcategory, brand, model, ordering, startDate, endDate], () => {
  page.value = 1
  clearTimeout(filterTimer)
  filterTimer = setTimeout(() => load().catch(e => { error.value = apiError(e) }), 250)
})
watch(category, () => { if (subcategory.value && !subcategoryOptions.value.some(item => item.id === Number(subcategory.value))) subcategory.value = '' })
watch(() => route.query.search, value => { if (value) search.value = String(value) })
function open(item = null) {
  editing.value = item; error.value = ''; modal.value = true
  Object.assign(form, item ? { category: item.category, name: item.name, brand: item.brand, model: item.model, serial_number: item.serial_number, internal_code: item.internal_code, status: item.status, daily_rate: item.daily_rate, estimated_weight_kg: item.estimated_weight_kg ?? '', technical_details: item.technical_details, current_usage_hours: item.current_usage_hours } : { category: categories.value[0]?.id || '', name: '', brand: '', model: '', serial_number: '', internal_code: '', status: 'AVAILABLE', daily_rate: '', estimated_weight_kg: '', technical_details: '', current_usage_hours: 0 })
}
function selectCategory(id) {
  const category = categories.value.find(item => item.id === Number(id)) || categories.value[0]
  if (!category) return
  categoryForm.id = category.id
  categoryForm.name = category.name
  categoryForm.description = category.description || ''
  categoryForm.parent = category.parent || ''
  categoryForm.pre_rental_checklist = (category.pre_rental_checklist || []).map(item => typeof item === 'string' ? item : { ...item })
  categoryForm.return_checklist = (category.return_checklist || []).map(item => typeof item === 'string' ? item : { ...item })
}
function openCategorySettings(item) {
  error.value = ''
  categoryModal.value = true
  selectCategory(item?.id || categoryForm.id || categories.value[0]?.id)
}
function newCategory() {
  error.value = ''
  Object.assign(categoryForm, { id: '', name: '', description: '', parent: '', pre_rental_checklist: [], return_checklist: [] })
  categoryModal.value = true
}
async function saveCategorySettings() {
  busy.value = true; error.value = ''
  const criteria = items => items.map(item => typeof item === 'string' ? item.trim() : { ...item, label: item.label.trim() }).filter(item => typeof item === 'string' ? item : item.label)
  try {
    const payload = { name: categoryForm.name.trim(), description: categoryForm.description, parent: categoryForm.parent || null, pre_rental_checklist: criteria(categoryForm.pre_rental_checklist), return_checklist: criteria(categoryForm.return_checklist) }
    if (categoryForm.id) await api.patch(`/categories/${categoryForm.id}/`, payload)
    else await api.post('/categories/', payload)
    categoryModal.value = false
    await load()
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}
async function save() {
  busy.value = true; error.value = ''
  try { const payload = { ...form, estimated_weight_kg: form.estimated_weight_kg === '' ? null : form.estimated_weight_kg }; editing.value ? await api.patch(`/equipment/${editing.value.id}/`, payload) : await api.post('/equipment/', payload); modal.value = false; editing.value = null; await load() }
  catch (e) { error.value = apiError(e) }
  finally { busy.value = false }
}
async function remove() {
  busy.value = true
  try { await api.delete(`/equipment/${deleting.value.id}/`); deleting.value = null; await load() }
  catch (e) { error.value = apiError(e); deleting.value = null }
  finally { busy.value = false }
}
async function openQr(item) {
  qrEquipment.value = item; error.value = ''
  if (qrUrl.value) URL.revokeObjectURL(qrUrl.value)
  try { const { data } = await api.get(`/equipment/${item.id}/qr-code/`, { responseType: 'blob' }); qrUrl.value = URL.createObjectURL(data) }
  catch (e) { error.value = apiError(e) }
}
async function resolveScan() {
  if (!route.query.qr) return
  try {
    const { data } = await api.get(`/equipment/resolve-qr/?token=${encodeURIComponent(route.query.qr)}`)
    scanNotice.value = `QR identificado: ${data.internal_code} · ${data.name}`
    search.value = data.internal_code
    await openQr(data)
  } catch (e) { error.value = apiError(e) }
  finally { router.replace({ path: '/equipamentos' }) }
}
onMounted(async () => {
  // Dashboard shortcuts preserve the operational context in the target list.
  if (route.query.search) search.value = String(route.query.search)
  if (route.query.status) status.value = String(route.query.status)
  if (route.query.category) category.value = String(route.query.category)
  if (route.query.subcategory) subcategory.value = String(route.query.subcategory)
  if (route.query.start_date) startDate.value = String(route.query.start_date)
  if (route.query.end_date) endDate.value = String(route.query.end_date)
  if (startDate.value || endDate.value || route.query.brand) showMore.value = true
  await load()
  await resolveScan()
})
onBeforeUnmount(() => { if (qrUrl.value) URL.revokeObjectURL(qrUrl.value); clearTimeout(filterTimer) })

const { page: page, items: equipmentRows } = usePagination(filtered, [])
const { page: categoryPage, items: categoryRows } = usePagination(filteredCategories, [categorySearch, categoryKind, categoryParent, categoryOrdering])
</script>

<template>
  <div class="page"><header class="page-heading compact"><div><span class="eyebrow">PATRIMÔNIO LOCÁVEL</span><h1>Equipamentos</h1><p>Cadastro, QR Code, documentos e histórico técnico no mesmo contexto.</p></div><div v-if="can('assets.manage')" class="page-heading-actions"><button v-if="tab === 'categories'" class="btn primary" @click="newCategory"><Plus :size="18" />Nova categoria</button><button v-else class="btn primary" @click="open()"><Plus :size="18" />Novo equipamento</button></div></header>
    <div v-if="scanNotice" class="success-strip">{{ scanNotice }}</div><GeneralError v-if="error && !modal && !categoryModal && !qrEquipment" :message="error" @close="error = ''" />
    <div class="tabs" aria-label="Cadastros de equipamentos"><button :class="{ active: tab === 'equipment' }" @click="tab = 'equipment'"><PackageSearch :size="17" />Equipamentos</button><button :class="{ active: tab === 'categories' }" @click="tab = 'categories'"><ClipboardList :size="17" />Categorias e checklists</button></div>
    <section v-if="tab === 'equipment'" class="panel list-panel">
      <ListToolbar>
        <template #search><label class="list-control list-search"><span>Pesquisar</span><span class="search-box"><Search :size="17" /><input v-model="search" type="search" placeholder="Nome, código ou QR" aria-label="Buscar equipamentos" /></span></label></template>
        <template #filters>
          <label class="list-control"><span>Situação</span><AppSelect v-model="status"><option value="">Todas</option><option value="AVAILABLE">Disponível</option><option value="RESERVED">Reservado</option><option value="RENTED">Locado</option><option value="MAINTENANCE">Em manutenção</option><option value="INSPECTION">Em inspeção</option><option value="INACTIVE">Inativo</option></AppSelect></label>
          <label class="list-control"><span>Categoria</span><AppSelect searchable v-model="category"><option value="">Todas</option><option v-for="c in categories.filter(item => !item.parent)" :key="c.id" :value="c.id">{{ c.name }}</option></AppSelect></label>
          <label class="list-control"><span>Subcategoria</span><AppSelect searchable v-model="subcategory"><option value="">Todas</option><option v-for="c in subcategoryOptions" :key="c.id" :value="c.id">{{ c.name }}</option></AppSelect></label>
          <ListOrdering v-model="ordering" :options="equipmentSortOptions" />
        </template>
        <template #meta><div class="filter-meta"><span class="result-count">{{ totalCount }} equipamento(s)</span><div class="filters-actions"><button class="btn secondary" type="button" :aria-expanded="showMore" @click="showMore = !showMore"><SlidersHorizontal :size="16" />{{ showMore ? 'Menos filtros' : 'Mais filtros' }}<span v-if="advancedCount" class="filter-badge">{{ advancedCount }}</span></button><button v-if="hasFilters" class="btn secondary" type="button" @click="clearFilters"><X :size="16" />Limpar filtros</button></div></div></template>
        <template v-if="showMore" #more><div class="list-controls list-more-filters">
          <label class="list-control"><span>Marca</span><input v-model="brand" type="search" placeholder="Ex.: Honda" /></label>
          <label class="list-control"><span>Modelo</span><input v-model="model" type="search" placeholder="Ex.: GX160" /></label>
          <label class="list-control"><span>Disponível a partir de</span><AppDateTime v-model="startDate" type="date" /></label>
          <label class="list-control"><span>Disponível até</span><AppDateTime v-model="endDate" type="date" :min="startDate || undefined" /></label>
          <p v-if="halfDateRange" class="filters-hint">Informe as duas datas para filtrar por disponibilidade no período.</p>
        </div></template>
      </ListToolbar>
      <div class="table-wrap desktop-list"><table><thead><tr><th>Equipamento</th><th>Categoria</th><th>Identificação</th><th>Diária</th><th>Status</th><th>Mídias</th><th class="right">Ações</th></tr></thead><tbody>
        <tr v-for="item in equipmentRows" :key="item.id"><td><strong>{{ item.name }}</strong><small>{{ item.brand }} · {{ item.model }}</small></td><td>{{ item.category_name }}</td><td><strong>{{ item.internal_code }}</strong><small>Série {{ item.serial_number }}</small></td><td><strong>{{ money(item.daily_rate) }}</strong></td><td><StatusBadge :value="item.status" :label="item.status_label" /></td><td><button class="media-count" @click="mediaEquipment = item"><Files :size="15" />{{ item.media_count }} arquivo(s)</button></td><td class="right"><div class="row-actions"><button class="icon-btn table-action" title="Abrir QR Code" aria-label="Abrir QR Code" @click="openQr(item)"><QrCode :size="17" /></button><button class="icon-btn table-action" title="Documentos e mídias" aria-label="Documentos e mídias" @click="mediaEquipment = item"><Files :size="17" /></button><button v-if="can('assets.manage')" class="icon-btn table-action" title="Editar" aria-label="Editar" @click="open(item)"><Pencil :size="17" /></button><button v-if="can('assets.manage')" class="icon-btn danger-icon" title="Excluir" aria-label="Excluir" @click="deleting = item"><Trash2 :size="17" /></button></div></td></tr>
        <tr v-if="!filtered.length"><td colspan="7" class="empty-cell"><PackageSearch :size="20" />Nenhum equipamento encontrado com estes filtros.</td></tr>
      </tbody></table></div>
      <div class="mobile-card-list">
        <article v-for="item in equipmentRows" :key="item.id" class="mobile-record-card">
          <header><div><span class="eyebrow">{{ item.internal_code }}</span><strong>{{ item.name }}</strong><small>{{ item.brand }} · {{ item.model }}</small></div><StatusBadge :value="item.status" :label="item.status_label" /></header>
          <dl><div><dt>Categoria</dt><dd>{{ item.category_name }}</dd></div><div><dt>Diária</dt><dd>{{ money(item.daily_rate) }}</dd></div><div><dt>Série</dt><dd>{{ item.serial_number }}</dd></div><div><dt>Mídias</dt><dd>{{ item.media_count }} arquivo(s)</dd></div></dl>
          <footer><button class="btn secondary" @click="openQr(item)"><QrCode :size="16" />QR Code</button><button class="btn secondary" @click="mediaEquipment = item"><Files :size="16" />Mídias</button><button v-if="can('assets.manage')" class="btn secondary" @click="open(item)"><Pencil :size="16" />Editar</button><button v-if="can('assets.manage')" class="btn secondary" @click="deleting = item"><Trash2 :size="16" />Excluir</button></footer>
        </article>
        <div v-if="!filtered.length" class="empty-state compact"><PackageSearch :size="26" /><h2>Nenhum equipamento encontrado</h2><p>Ajuste ou limpe os filtros.</p></div>
      </div>
      <PaginationBar v-model="page" :total="(filtered).length" /></section>

    <section v-else class="panel list-panel"><ListToolbar><template #search><label class="list-control list-search"><span>Pesquisar</span><span class="search-box"><Search :size="17" /><input v-model="categorySearch" type="search" placeholder="Categoria, subcategoria ou descrição" aria-label="Buscar categorias" /></span></label></template><template #filters><label class="list-control"><span>Nível</span><AppSelect v-model="categoryKind"><option value="">Todos</option><option value="root">Categorias principais</option><option value="child">Subcategorias</option></AppSelect></label><label class="list-control"><span>Categoria superior</span><AppSelect searchable v-model="categoryParent"><option value="">Todas</option><option v-for="item in categories.filter(item => !item.parent)" :key="item.id" :value="String(item.id)">{{ item.name }}</option></AppSelect></label><ListOrdering v-model="categoryOrdering" :options="categorySortOptions" /></template><template #meta><div class="filter-meta"><span class="result-count">{{ filteredCategories.length }} categoria(s)</span><button type="button" class="btn secondary" @click="clearCategoryFilters">Limpar filtros</button></div></template></ListToolbar><div class="table-wrap"><table><thead><tr><th>Categoria</th><th>Categoria superior</th><th>Pré-locação</th><th>Devolução</th><th class="right">Ações</th></tr></thead><tbody><tr v-for="item in categoryRows" :key="item.id"><td><strong>{{ item.name }}</strong><small>{{ item.description || 'Sem descrição' }}</small></td><td>{{ item.parent_name || 'Categoria principal' }}</td><td>{{ item.pre_rental_checklist?.length || 0 }} ponto(s)</td><td>{{ item.return_checklist?.length || 0 }} ponto(s)</td><td class="right"><button v-if="can('assets.manage')" class="btn secondary" @click="openCategorySettings(item)"><Pencil :size="16" />Editar categoria</button></td></tr><tr v-if="!filteredCategories.length"><td colspan="5" class="empty-cell">Nenhuma categoria encontrada.</td></tr></tbody></table><PaginationBar v-model="categoryPage" :total="(filteredCategories).length" /></div></section>

    <ModalDialog v-if="modal" :title="editing ? 'Editar equipamento' : 'Cadastrar equipamento'" @close="modal = false; error = ''"><form class="equipment-registration" @submit.prevent="save"><div class="form-grid">
      <div class="form-field span-2"><label>Nome do equipamento<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="form.name" required placeholder="Ex.: Compactador de solo" /></div>
      <div class="form-field"><label>Categoria<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect searchable v-model="form.category" required><option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option></AppSelect></div><div class="form-field"><label>Código interno<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="form.internal_code" placeholder="EQ-001" required /></div>
      <div class="form-field"><label>Marca<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="form.brand" required placeholder="Ex.: Marca do fabricante" /></div><div class="form-field"><label>Modelo<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="form.model" required placeholder="Ex.: Modelo informado na identificação" /></div>
      <div class="form-field"><label>Número de série<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="form.serial_number" required placeholder="Número de série do fabricante" /></div><div class="form-field"><label>Status<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect required v-model="form.status"><option value="AVAILABLE">Disponível</option><option v-if="form.status === 'RESERVED'" value="RESERVED">Reservado</option><option v-if="form.status === 'RENTED'" value="RENTED">Locado</option><option value="MAINTENANCE">Em manutenção</option><option value="INSPECTION">Em inspeção</option><option value="INACTIVE">Inativo</option></AppSelect></div>
      <div class="form-field"><label>Valor da diária<span class="required-mark" aria-hidden="true"> *</span></label><AppInput mask="money" v-model="form.daily_rate" min="0" step="0.01" required placeholder="Ex.: 150,00" /></div><div class="form-field"><label>Peso estimado (kg)</label><AppInput mask="decimal" :precision="2" v-model="form.estimated_weight_kg" min="0.01" step="0.01" placeholder="Ex.: 85,5" /></div>
      <div class="form-field span-2"><label>Horas de uso</label><AppInput mask="decimal" :precision="2" v-model="form.current_usage_hours" min="0" placeholder="Ex.: 120" /></div><div class="form-field span-2"><label>Características técnicas</label><textarea v-model="form.technical_details" rows="2" placeholder="Potência, dimensões, capacidade e outras especificações" /></div>
      </div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><span class="spacer"/><button class="btn primary" :disabled="busy">{{ editing ? 'Salvar alterações' : 'Salvar equipamento' }}</button></div></form></ModalDialog>

    <ModalDialog v-if="categoryModal" :title="categoryForm.id ? 'Editar categoria e checklists' : 'Cadastrar categoria ou subcategoria'" wide @close="categoryModal = false; error = ''"><form @submit.prevent="saveCategorySettings"><div class="form-grid"><div class="form-field"><label>Nome<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="categoryForm.name" required maxlength="100" placeholder="Ex.: Concretagem" /></div><div class="form-field"><label>Categoria superior (opcional)</label><AppSelect searchable v-model="categoryForm.parent"><option value="">Categoria principal</option><option v-for="item in categories.filter(item => !item.parent && item.id !== categoryForm.id)" :key="item.id" :value="item.id">{{ item.name }}</option></AppSelect></div><div class="form-field span-2"><label>Descrição</label><textarea v-model="categoryForm.description" rows="2" placeholder="Tipos de equipamentos e aplicações desta categoria" /></div><ChecklistItemsEditor v-model="categoryForm.pre_rental_checklist" title="Checklist pré-locação" /><ChecklistItemsEditor v-model="categoryForm.return_checklist" title="Checklist de devolução" /></div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="categoryModal = false; error = ''">Fechar</button><span class="spacer"/><button class="btn primary" :disabled="busy">{{ busy ? 'Salvando...' : categoryForm.id ? 'Salvar categoria' : 'Criar categoria' }}</button></div></form></ModalDialog>

    <ModalDialog v-if="qrEquipment" title="QR Code do equipamento" @close="qrEquipment = null"><div class="qr-dialog"><div class="qr-image"><img v-if="qrUrl" :src="qrUrl" :alt="`QR Code ${qrEquipment.internal_code}`" /><span v-else>Gerando QR Code...</span></div><span class="eyebrow">IDENTIFICAÇÃO ÚNICA</span><h2>{{ qrEquipment.internal_code }} · {{ qrEquipment.name }}</h2><p>Ao escanear, um usuário autenticado abre diretamente este equipamento no PANDORA.</p><code>{{ qrEquipment.qr_code_token }}</code><a v-if="qrUrl" class="btn primary" :href="qrUrl" :download="`qr-${qrEquipment.internal_code}.png`">Baixar QR Code</a></div><GeneralError v-if="error" :message="error" @close="error = ''" /></ModalDialog>
    <EquipmentMediaModal v-if="mediaEquipment" :equipment="mediaEquipment" @close="mediaEquipment = null" @changed="load" />
    <ConfirmDialog v-if="deleting" title="Excluir equipamento" :message="`Excluir “${deleting.name}”? Locações, ordens ou documentos vinculados podem impedir a exclusão.`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
  </div>
</template>
