<script setup>
import { formatTaxId, formatPhone } from '../services/formatters'
import { matchesSearch, sortRecords } from '../services/listFilters'
import { usePagination } from '../services/pagination'
import { splitAddress } from '../services/rentalDestinations'
import { documentCaret, formatDocument, normalizeDocument } from '../services/documents'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { KeyRound, Pencil, Plus, Search, ShieldCheck, Trash2, UserCog, UsersRound } from 'lucide-vue-next'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api, apiError, auth, can, canAny, refreshCurrentUser, rows, fetchAll } from '../services/api'

const users = ref([]), customers = ref([]), groups = ref([]), catalog = ref([]), search = ref(''), modal = ref(null), editing = ref(null), deleting = ref(null), error = ref(''), busy = ref(false)
const router = useRouter()
const initialTab = can('customers.view') ? 'customers' : can('accounts.users.view') ? 'users' : 'groups'
const tab = ref(initialTab)
const activity = ref(''), personType = ref(''), accessGroup = ref(''), groupKind = ref(''), ordering = ref('name')
function clearListFilters() { search.value = ''; activity.value = ''; personType.value = ''; accessGroup.value = ''; groupKind.value = ''; ordering.value = 'name' }
watch(tab, clearListFilters)
const groupOptions = computed(() => [...new Map(users.value.map(user => [String(user.access_group ?? user.role), user.access_group_name || user.role_label])).entries()])
const sortOptions = computed(() => [['name', 'Nome A–Z'], ['-name', 'Nome Z–A'], ...(tab.value === 'groups' ? [['-users', 'Mais usuários'], ['users', 'Menos usuários']] : [['-id', 'Mais recentes'], ['id', 'Mais antigos']])])
const activeMatch = item => !activity.value || (item.is_active !== false) === (activity.value === 'active')
const customerForm = reactive({ person_type: 'PJ', name: '', document: '', email: '', phone: '', address: '', number: '', address_cep: '', notes: '', is_active: true, marketing_opt_in: false })
const customerDocument = computed(() => formatDocument(customerForm.document, customerForm.person_type))
function onCustomerDocumentInput(event) {
  const input = event.target
  const rawPosition = normalizeDocument(input.value.slice(0, input.selectionStart ?? input.value.length)).length
  customerForm.document = normalizeDocument(input.value)
  input.value = customerDocument.value
  const caret = documentCaret(input.value, rawPosition)
  input.setSelectionRange(caret, caret)
}
const userForm = reactive({ full_name: '', email: '', phone: '', role: 'SALES', access_group: '', password: '', is_active: true })
const groupForm = reactive({ name: '', description: '', permissions: [] })
const filteredCustomers = computed(() => sortRecords(customers.value.filter(item => activeMatch(item) && (!personType.value || item.person_type === personType.value) && matchesSearch(search.value, item.name, item.document, item.email, item.phone)), ordering.value, { name: item => item.name, id: item => item.id }))
const filteredUsers = computed(() => sortRecords(users.value.filter(item => activeMatch(item) && (!accessGroup.value || String(item.access_group ?? item.role) === accessGroup.value) && matchesSearch(search.value, item.full_name, item.email, item.phone, item.access_group_name)), ordering.value, { name: item => item.full_name, id: item => item.id }))
const filteredGroups = computed(() => sortRecords(groups.value.filter(item => (!groupKind.value || Boolean(item.is_system) === (groupKind.value === 'system')) && matchesSearch(search.value, item.name, item.description)), ordering.value, { name: item => item.name, users: item => Number(item.user_count || 0) }))
const modules = computed(() => Object.entries(catalog.value.reduce((acc, item) => { (acc[item.module] ||= []).push(item); return acc }, {})))

let loadRequest = 0
async function load() {
  const request = ++loadRequest
  const groupAccess = can('accounts.groups.manage') || can('accounts.users.manage')
  const [userResponse, customerResponse, groupResponse, catalogResponse] = await Promise.all([
    can('accounts.users.view') ? fetchAll('/users/') : { data: [] },
    can('customers.view') ? fetchAll('/customers/') : { data: [] },
    groupAccess ? fetchAll('/access-groups/') : { data: [] },
    can('accounts.groups.manage') ? api.get('/access-groups/catalog/') : { data: [] },
  ])
  if (request !== loadRequest) return
  users.value = rows(userResponse.data); customers.value = rows(customerResponse.data)
  groups.value = rows(groupResponse.data); catalog.value = catalogResponse.data
}

const customerAddressBusy = ref(false), customerAddressError = ref('')
let customerAddressRequest = 0
function invalidateCustomerAddress() { customerAddressRequest += 1; customerAddressBusy.value = false; customerAddressError.value = '' }
async function lookupCustomerAddress() {
  invalidateCustomerAddress()
  if (!/^\d{8}$/.test(customerForm.address_cep)) { customerAddressError.value = 'Informe um CEP com 8 dígitos.'; return }
  const request = customerAddressRequest, cep = customerForm.address_cep, previousAddress = customerForm.address
  customerAddressBusy.value = true
  try {
    const { data } = await api.get('/customers/lookup-address/', { params: { cep } })
    if (request !== customerAddressRequest || modal.value !== 'customer' || cep !== customerForm.address_cep || previousAddress !== customerForm.address) return
    customerForm.address = [data.street, data.neighborhood, `${data.city}/${data.state}`].filter(Boolean).join(', ')
  } catch (event) { if (request === customerAddressRequest) customerAddressError.value = apiError(event) }
  finally { if (request === customerAddressRequest) customerAddressBusy.value = false }
}
function openCustomer(item = null) {
  invalidateCustomerAddress()
  editing.value = item; modal.value = 'customer'; error.value = ''
  Object.assign(customerForm, { person_type: item?.person_type || 'PJ', name: item?.name || '', document: item?.document || '', email: item?.email || '', phone: item?.phone || '', ...splitAddress(item?.address, item?.address_number), address_cep: item?.address_cep || '', notes: item?.notes || '', is_active: item?.is_active ?? true, marketing_opt_in: item?.marketing_opt_in ?? false })
}
function openUser(item = null) {
  editing.value = item; modal.value = 'user'; error.value = ''
  Object.assign(userForm, item ? { full_name: item.full_name, email: item.email, phone: item.phone, role: item.role, access_group: item.access_group, password: '', is_active: item.is_active } : { full_name: '', email: '', phone: '', role: 'SALES', access_group: groups.value[0]?.id || '', password: 'Pandora@123', is_active: true })
}
function openGroup(item = null) {
  editing.value = item; modal.value = 'group'; error.value = ''
  Object.assign(groupForm, item ? { name: item.name, description: item.description, permissions: [...item.permissions] } : { name: '', description: '', permissions: [] })
}
const moduleChecked = permissions => permissions.every(permission => groupForm.permissions.includes(permission.code))
const modulePartial = permissions => !moduleChecked(permissions) && permissions.some(permission => groupForm.permissions.includes(permission.code))
function toggleModule(permissions, checked) {
  const codes = new Set(permissions.map(permission => permission.code))
  groupForm.permissions = checked ? [...new Set([...groupForm.permissions, ...codes])] : groupForm.permissions.filter(code => !codes.has(code))
}
function togglePermission(code) {
  const index = groupForm.permissions.indexOf(code)
  if (index >= 0) groupForm.permissions.splice(index, 1); else groupForm.permissions.push(code)
}
async function saveCustomer() { const {number,...payload}=customerForm; await persist('/customers/', { ...payload, address_number: number || '', document: normalizeDocument(customerForm.document) }) }
async function saveUser() {
  const payload = { ...userForm }
  if (!payload.password) delete payload.password
  await persist('/users/', payload)
}
async function saveGroup() { await persist('/access-groups/', groupForm) }
async function persist(base, payload) {
  busy.value = true; error.value = ''
  try {
    editing.value ? await api.patch(`${base}${editing.value.id}/`, payload) : await api.post(base, payload)
    modal.value = null
    editing.value = null
    if (base === '/access-groups/' || base === '/users/') await refreshCurrentUser()
    if (!canAny(['customers.view', 'accounts.users.view', 'accounts.groups.manage'])) await router.replace('/')
    else {
      if ((tab.value === 'customers' && !can('customers.view')) || (tab.value === 'users' && !can('accounts.users.view')) || (tab.value === 'groups' && !can('accounts.groups.manage'))) {
        tab.value = can('customers.view') ? 'customers' : can('accounts.users.view') ? 'users' : 'groups'
      }
      await load()
    }
  }
  catch (e) { error.value = apiError(e) }
  finally { busy.value = false }
}
function requestDelete(kind, item) { deleting.value = { kind, item } }
async function remove() {
  busy.value = true; error.value = ''
  const bases = { customer: '/customers/', user: '/users/', group: '/access-groups/' }
  try { await api.delete(`${bases[deleting.value.kind]}${deleting.value.item.id}/`); deleting.value = null; await load() }
  catch (e) { error.value = apiError(e); deleting.value = null }
  finally { busy.value = false }
}
const permissionLabel = code => code === '*' ? 'Acesso total' : catalog.value.find(x => x.code === code)?.label || code
onMounted(() => load().catch(event => { error.value = apiError(event) }))

const { page: customerPage, items: customerRows } = usePagination(filteredCustomers, [search, activity, personType, ordering])
const { page: userPage, items: userRows } = usePagination(filteredUsers, [search, activity, accessGroup, ordering])
const { page: groupPage, items: groupRows } = usePagination(filteredGroups, [search, groupKind, ordering])
</script>

<template>
  <div class="page">
    <header class="page-heading compact"><div><span class="eyebrow">CADASTROS E ACL</span><h1>Pessoas e acessos</h1><p>Gerencie usuários e crie grupos com permissões específicas por operação.</p></div><button v-if="tab === 'customers' && can('customers.manage')" class="btn primary" @click="openCustomer()"><Plus :size="18" />Novo cliente</button><button v-else-if="tab === 'users' && can('accounts.users.manage')" class="btn primary" @click="openUser()"><Plus :size="18" />Novo funcionário</button><button v-else-if="tab === 'groups' && can('accounts.groups.manage')" class="btn primary" @click="openGroup()"><Plus :size="18" />Novo grupo</button></header>
    <div class="tabs"><button v-if="can('customers.view')" :class="{ active: tab === 'customers' }" @click="tab = 'customers'"><UsersRound :size="17" />Clientes</button><button v-if="can('accounts.users.view')" :class="{ active: tab === 'users' }" @click="tab = 'users'"><UserCog :size="17" />Funcionários</button><button v-if="can('accounts.groups.manage')" :class="{ active: tab === 'groups' }" @click="tab = 'groups'"><ShieldCheck :size="17" />Grupos de permissão</button></div>

    <section v-if="tab !== 'groups'" class="panel list-panel"><ListToolbar><template #search><label class="list-control list-search"><span>Pesquisar</span><span class="search-box"><Search :size="17" /><input v-model="search" type="search" :placeholder="tab === 'customers' ? 'Nome, documento ou contato' : 'Nome, e-mail ou grupo'" aria-label="Pesquisar pessoas" /></span></label></template><template #filters><label class="list-control"><span>Situação</span><AppSelect v-model="activity"><option value="">Todas</option><option value="active">Ativos</option><option value="inactive">Inativos</option></AppSelect></label>
      <label v-if="tab === 'customers'" class="list-control"><span>Tipo de pessoa</span><AppSelect v-model="personType"><option value="">Todos</option><option value="PF">Pessoa física</option><option value="PJ">Pessoa jurídica</option></AppSelect></label>
      <label v-else class="list-control"><span>Grupo de permissão</span><AppSelect searchable v-model="accessGroup"><option value="">Todos</option><option v-for="[id, name] in groupOptions" :key="id" :value="id">{{ name }}</option></AppSelect></label>
      <ListOrdering v-model="ordering" :options="sortOptions" /></template><template #meta><div class="filter-meta"><span class="result-count">{{ tab === 'customers' ? filteredCustomers.length : filteredUsers.length }} registros</span><button type="button" class="btn secondary" @click="clearListFilters">Limpar filtros</button></div></template></ListToolbar><div class="table-wrap"><table v-if="tab === 'customers'"><thead><tr><th>Cliente</th><th>Documento</th><th>Contato</th><th>Tipo</th><th>Status</th><th class="right">Ações</th></tr></thead><tbody><tr v-for="customer in customerRows" :key="customer.id"><td><strong>{{ customer.name }}</strong><small>{{ customer.email || 'Sem e-mail' }}</small></td><td>{{ formatTaxId(customer.document, customer.person_type) }}</td><td>{{ formatPhone(customer.phone) }}</td><td>{{ customer.person_type_label }}</td><td><StatusBadge :value="customer.is_active ? 'ACTIVE' : 'INACTIVE'" :label="customer.is_active ? 'Ativo' : 'Inativo'" /></td><td class="right"><div v-if="can('customers.manage')" class="row-actions"><button class="icon-btn table-action" title="Editar" @click="openCustomer(customer)"><Pencil :size="16" /></button><button class="icon-btn danger-icon" title="Excluir" @click="requestDelete('customer', customer)"><Trash2 :size="16" /></button></div></td></tr></tbody></table><PaginationBar v-if="tab === 'customers'" v-model="customerPage" :total="(filteredCustomers).length" /><table v-if="tab === 'users'"><thead><tr><th>Funcionário</th><th>Contato</th><th>Grupo ACL</th><th>Status</th><th class="right">Ações</th></tr></thead><tbody><tr v-for="user in userRows" :key="user.id"><td><strong>{{ user.full_name }}</strong><small>#{{ String(user.id).padStart(4, '0') }}</small></td><td>{{ user.email }}<small>{{ user.phone ? formatPhone(user.phone) : 'Sem telefone' }}</small></td><td><span class="acl-chip"><KeyRound :size="13" />{{ user.access_group_name || user.role_label }}</span></td><td><StatusBadge :value="user.is_active ? 'ACTIVE' : 'INACTIVE'" :label="user.is_active ? 'Ativo' : 'Inativo'" /></td><td class="right"><div v-if="can('accounts.users.manage')" class="row-actions"><button class="icon-btn table-action" title="Editar" @click="openUser(user)"><Pencil :size="16" /></button><button v-if="user.id !== auth.user?.id" class="icon-btn danger-icon" title="Excluir" @click="requestDelete('user', user)"><Trash2 :size="16" /></button></div></td></tr></tbody></table><PaginationBar v-if="tab === 'users'" v-model="userPage" :total="(filteredUsers).length" /></div></section>

    <section v-else class="panel list-panel"><ListToolbar><template #search><label class="list-control list-search"><span>Pesquisar</span><span class="search-box"><Search :size="17" /><input v-model="search" type="search" placeholder="Nome ou descrição do grupo" aria-label="Pesquisar grupos" /></span></label></template><template #filters><label class="list-control"><span>Tipo de grupo</span><AppSelect v-model="groupKind"><option value="">Todos</option><option value="system">Padrão</option><option value="custom">Personalizado</option></AppSelect></label><ListOrdering v-model="ordering" :options="sortOptions" /></template><template #meta><div class="filter-meta"><span class="result-count">{{ filteredGroups.length }} grupo(s)</span><button type="button" class="btn secondary" @click="clearListFilters">Limpar filtros</button></div></template></ListToolbar><div class="table-wrap"><table><thead><tr><th>Grupo</th><th>Usuários</th><th>Tipo</th><th class="right">Ações</th></tr></thead><tbody><tr v-for="group in groupRows" :key="group.id"><td><strong>{{ group.name }}</strong><small>{{ group.description || 'Grupo personalizado de acesso.' }}</small></td><td>{{ group.user_count }}</td><td>{{ group.is_system ? 'Padrão' : 'Personalizado' }}</td><td class="right"><div class="row-actions"><button class="icon-btn table-action" title="Editar grupo e permissões" @click="openGroup(group)"><Pencil :size="16" /></button><button v-if="!group.is_system" class="icon-btn danger-icon" title="Excluir grupo" @click="requestDelete('group', group)"><Trash2 :size="16" /></button></div></td></tr><tr v-if="!filteredGroups.length"><td colspan="4" class="empty-cell">Nenhum grupo encontrado.</td></tr></tbody></table><PaginationBar v-model="groupPage" :total="(filteredGroups).length" /></div></section>

    <ModalDialog v-if="modal === 'customer'" :title="editing ? 'Editar cliente' : 'Cadastrar cliente'" @close="modal = null; error = ''"><form @submit.prevent="saveCustomer"><div class="form-grid"><div class="form-field"><label>Tipo de pessoa<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect required v-model="customerForm.person_type"><option value="PF">Pessoa física</option><option value="PJ">Pessoa jurídica</option></AppSelect></div><div class="form-field"><label for="customer-document">{{ customerForm.person_type === 'PF' ? 'CPF' : 'CNPJ' }}<span class="required-mark" aria-hidden="true"> *</span></label><input id="customer-document" :value="customerDocument" type="text" :inputmode="customerForm.person_type === 'PF' ? 'numeric' : 'text'" :placeholder="customerForm.person_type === 'PF' ? '000.000.000-00' : '00.000.000/0000-00'" :pattern="customerForm.person_type === 'PF' ? '[0-9]{3}\\.[0-9]{3}\\.[0-9]{3}-[0-9]{2}' : '[A-Z0-9]{2}\\.[A-Z0-9]{3}\\.[A-Z0-9]{3}/[A-Z0-9]{4}-[0-9]{2}'" :title="customerForm.person_type === 'PF' ? 'Informe o CPF completo, com 11 dígitos.' : 'Informe o CNPJ completo, com 14 caracteres e dois dígitos finais.'" required @input="onCustomerDocumentInput" /></div><div class="form-field span-2"><label>Nome / razão social<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="customerForm.name" required placeholder="Nome completo ou razão social" /></div><div class="form-field"><label>E-mail</label><input v-model="customerForm.email" type="email" placeholder="Ex.: contato@empresa.com.br" /></div><div class="form-field"><label>Telefone<span class="required-mark" aria-hidden="true"> *</span></label><AppInput mask="phone" v-model="customerForm.phone" required placeholder="Ex.: (19) 99999-9999" /></div><div class="form-field"><label for="customer-cep">CEP</label><div class="address-lookup-row"><AppInput mask="cep" id="customer-cep" v-model="customerForm.address_cep" inputmode="numeric" placeholder="00000-000" @input="customerForm.address_cep = customerForm.address_cep.replace(/\D/g, ''); invalidateCustomerAddress()" /><button type="button" class="btn secondary" :disabled="customerAddressBusy" @click="lookupCustomerAddress">{{ customerAddressBusy ? 'Buscando...' : 'Preencher endereço' }}</button></div><small v-if="customerAddressError" class="address-lookup-error" role="alert">{{ customerAddressError }}</small></div><div class="form-field"><label for="customer-number">Número</label><input id="customer-number" v-model="customerForm.number" maxlength="20" placeholder="Ex.: 120 ou S/N" /></div><div class="form-field span-2"><label for="customer-address">Logradouro, bairro e cidade</label><input id="customer-address" v-model="customerForm.address" maxlength="255" placeholder="Logradouro, bairro e cidade/UF" /><small>Usado como endereço inicial nas novas locações. Preencha o número no campo separado.</small></div><div class="form-field span-2"><label for="customer-notes">Observações do cliente</label><textarea id="customer-notes" v-model="customerForm.notes" rows="3" placeholder="Notas internas sobre o atendimento e particularidades do cliente." /></div><label class="check-line span-2"><input v-model="customerForm.is_active" type="checkbox" />Cliente ativo</label></div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null; error = ''">Fechar</button><span class="spacer" /><button class="btn primary" :disabled="busy">{{ editing ? 'Salvar alterações' : 'Salvar cliente' }}</button></div></form></ModalDialog>

    <ModalDialog v-if="modal === 'user'" :title="editing ? 'Editar funcionário' : 'Cadastrar funcionário'" @close="modal = null; error = ''"><form @submit.prevent="saveUser"><div class="form-grid"><div class="form-field span-2"><label>Nome completo<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="userForm.full_name" required placeholder="Nome completo do funcionário" /></div><div class="form-field"><label>E-mail<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="userForm.email" type="email" required placeholder="Ex.: nome@empresa.com.br" /></div><div class="form-field"><label>Telefone</label><AppInput mask="phone" v-model="userForm.phone" placeholder="Ex.: (19) 99999-9999" /></div><div class="form-field span-2"><label>Grupo de acesso<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect searchable v-model="userForm.access_group" required><option v-for="group in groups" :key="group.id" :value="group.id">{{ group.name }}</option></AppSelect></div><div class="form-field span-2"><label>{{ editing ? 'Nova senha (opcional)' : 'Senha temporária' }}<span class="required-mark" aria-hidden="true" v-if="!editing"> *</span></label><input v-model="userForm.password" type="password" :required="!editing"  :placeholder="editing ? 'Deixe em branco para manter a senha atual' : 'Defina a senha de acesso'" /></div><label class="check-line span-2"><input v-model="userForm.is_active" type="checkbox" />Usuário ativo</label></div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null; error = ''">Fechar</button><span class="spacer" /><button class="btn primary" :disabled="busy">Salvar funcionário</button></div></form></ModalDialog>

    <ModalDialog v-if="modal === 'group'" :title="editing ? 'Editar grupo e ACL' : 'Criar grupo de acesso'" wide @close="modal = null; error = ''"><form @submit.prevent="saveGroup"><div class="form-grid"><div class="form-field"><label>Nome do grupo<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="groupForm.name" required placeholder="Ex.: Equipe de transporte" /></div><div class="form-field"><label>Descrição</label><input v-model="groupForm.description" placeholder="Descreva os acessos e a finalidade do grupo" /></div></div><div class="acl-editor"><header><div><span class="eyebrow">MATRIZ DE ACESSO</span><h3>Permissões do grupo</h3></div><span>{{ groupForm.permissions.includes('*') ? 'Acesso total' : `${groupForm.permissions.length} selecionadas` }}</span></header><label class="permission-master"><input type="checkbox" :checked="groupForm.permissions.includes('*')" @change="groupForm.permissions = $event.target.checked ? ['*'] : []" /><span><strong>Acesso total</strong><small>Ignora a matriz abaixo e libera todas as operações.</small></span></label><div v-if="!groupForm.permissions.includes('*')" class="permission-modules"><section v-for="[module, permissions] in modules" :key="module"><header class="permission-sector-header"><h4>{{ module }}</h4><label><input type="checkbox" :checked="moduleChecked(permissions)" :indeterminate="modulePartial(permissions)" @change="toggleModule(permissions, $event.target.checked)" />Selecionar todas</label></header><label v-for="permission in permissions" :key="permission.code"><input type="checkbox" :checked="groupForm.permissions.includes(permission.code)" @change="togglePermission(permission.code)" /><span>{{ permission.label }}</span></label></section></div></div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null; error = ''">Fechar</button><span class="spacer" /><button class="btn primary" :disabled="busy">Salvar grupo</button></div></form></ModalDialog>

    <ConfirmDialog v-if="deleting" :title="`Excluir ${deleting.kind === 'group' ? 'grupo' : 'cadastro'}`" :message="`Esta ação excluirá “${deleting.item.name || deleting.item.full_name}”. Registros vinculados podem impedir a operação.`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
    <GeneralError v-if="error && !modal" :message="error" @close="error = ''" />
  </div>
</template>
