<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { KeyRound, Pencil, Plus, Search, ShieldCheck, Trash2, UserCog, UsersRound } from 'lucide-vue-next'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api, apiError, auth, can, rows } from '../services/api'

const users = ref([]), customers = ref([]), groups = ref([]), catalog = ref([]), search = ref(''), modal = ref(null), editing = ref(null), deleting = ref(null), error = ref(''), busy = ref(false)
const initialTab = can('customers.view') ? 'customers' : 'users'
const tab = ref(initialTab)
const customerForm = reactive({ person_type: 'PJ', name: '', document: '', email: '', phone: '', address: '', notes: '', is_active: true })
const userForm = reactive({ full_name: '', email: '', phone: '', role: 'SALES', access_group: '', password: '', is_active: true })
const groupForm = reactive({ name: '', description: '', permissions: [] })
const filteredCustomers = computed(() => customers.value.filter(x => `${x.name} ${x.document}`.toLowerCase().includes(search.value.toLowerCase())))
const filteredUsers = computed(() => users.value.filter(x => `${x.full_name} ${x.email}`.toLowerCase().includes(search.value.toLowerCase())))
const modules = computed(() => Object.entries(catalog.value.reduce((acc, item) => { (acc[item.module] ||= []).push(item); return acc }, {})))

async function load() {
  const requests = []
  if (can('customers.view')) requests.push(api.get('/customers/').then(r => customers.value = rows(r.data)))
  if (can('accounts.users.view')) requests.push(api.get('/users/').then(r => users.value = rows(r.data)))
  if (can('accounts.groups.manage') || can('accounts.users.manage')) {
    requests.push(api.get('/access-groups/').then(r => groups.value = rows(r.data)))
    if (can('accounts.groups.manage')) requests.push(api.get('/access-groups/catalog/').then(r => catalog.value = r.data))
  }
  await Promise.all(requests)
}
function openCustomer(item = null) {
  editing.value = item; modal.value = 'customer'; error.value = ''
  Object.assign(customerForm, item ? { ...item } : { person_type: 'PJ', name: '', document: '', email: '', phone: '', address: '', notes: '', is_active: true })
}
function openUser(item = null) {
  editing.value = item; modal.value = 'user'; error.value = ''
  Object.assign(userForm, item ? { full_name: item.full_name, email: item.email, phone: item.phone, role: item.role, access_group: item.access_group, password: '', is_active: item.is_active } : { full_name: '', email: '', phone: '', role: 'SALES', access_group: groups.value[0]?.id || '', password: 'Pandora@123', is_active: true })
}
function openGroup(item = null) {
  editing.value = item; modal.value = 'group'; error.value = ''
  Object.assign(groupForm, item ? { name: item.name, description: item.description, permissions: [...item.permissions] } : { name: '', description: '', permissions: [] })
}
function togglePermission(code) {
  const index = groupForm.permissions.indexOf(code)
  if (index >= 0) groupForm.permissions.splice(index, 1); else groupForm.permissions.push(code)
}
async function saveCustomer() { await persist('/customers/', customerForm) }
async function saveUser() {
  const payload = { ...userForm }
  if (!payload.password) delete payload.password
  await persist('/users/', payload)
}
async function saveGroup() { await persist('/access-groups/', groupForm) }
async function persist(base, payload) {
  busy.value = true; error.value = ''
  try { editing.value ? await api.patch(`${base}${editing.value.id}/`, payload) : await api.post(base, payload); modal.value = null; editing.value = null; await load() }
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
onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-heading compact"><div><span class="eyebrow">CADASTROS E ACL</span><h1>Pessoas e acessos</h1><p>Gerencie usuários e crie grupos com permissões específicas por operação.</p></div><button v-if="tab === 'customers' && can('customers.manage')" class="btn primary" @click="openCustomer()"><Plus :size="18" />Novo cliente</button><button v-else-if="tab === 'users' && can('accounts.users.manage')" class="btn primary" @click="openUser()"><Plus :size="18" />Novo funcionário</button><button v-else-if="tab === 'groups' && can('accounts.groups.manage')" class="btn primary" @click="openGroup()"><Plus :size="18" />Novo grupo</button></header>
    <div class="tabs"><button v-if="can('customers.view')" :class="{ active: tab === 'customers' }" @click="tab = 'customers'"><UsersRound :size="17" />Clientes</button><button v-if="can('accounts.users.view')" :class="{ active: tab === 'users' }" @click="tab = 'users'"><UserCog :size="17" />Funcionários</button><button v-if="can('accounts.groups.manage')" :class="{ active: tab === 'groups' }" @click="tab = 'groups'"><ShieldCheck :size="17" />Grupos de permissão</button></div>

    <section v-if="tab !== 'groups'" class="panel list-panel"><header class="list-toolbar"><div class="search-box"><Search :size="17" /><input v-model="search" placeholder="Buscar por nome, documento ou e-mail" /></div><span class="result-count">{{ tab === 'customers' ? filteredCustomers.length : filteredUsers.length }} registros</span></header><div class="table-wrap"><table v-if="tab === 'customers'"><thead><tr><th>Cliente</th><th>Documento</th><th>Contato</th><th>Tipo</th><th>Status</th><th class="right">Ações</th></tr></thead><tbody><tr v-for="customer in filteredCustomers" :key="customer.id"><td><strong>{{ customer.name }}</strong><small>{{ customer.email || 'Sem e-mail' }}</small></td><td>{{ customer.document }}</td><td>{{ customer.phone }}</td><td>{{ customer.person_type_label }}</td><td><StatusBadge :value="customer.is_active ? 'ACTIVE' : 'INACTIVE'" :label="customer.is_active ? 'Ativo' : 'Inativo'" /></td><td class="right"><div v-if="can('customers.manage')" class="row-actions"><button class="icon-btn table-action" title="Editar" @click="openCustomer(customer)"><Pencil :size="16" /></button><button class="icon-btn danger-icon" title="Excluir" @click="requestDelete('customer', customer)"><Trash2 :size="16" /></button></div></td></tr></tbody></table><table v-else><thead><tr><th>Funcionário</th><th>Contato</th><th>Grupo ACL</th><th>Status</th><th class="right">Ações</th></tr></thead><tbody><tr v-for="user in filteredUsers" :key="user.id"><td><strong>{{ user.full_name }}</strong><small>#{{ String(user.id).padStart(4, '0') }}</small></td><td>{{ user.email }}<small>{{ user.phone || 'Sem telefone' }}</small></td><td><span class="acl-chip"><KeyRound :size="13" />{{ user.access_group_name || user.role_label }}</span></td><td><StatusBadge :value="user.is_active ? 'ACTIVE' : 'INACTIVE'" :label="user.is_active ? 'Ativo' : 'Inativo'" /></td><td class="right"><div v-if="can('accounts.users.manage')" class="row-actions"><button class="icon-btn table-action" title="Editar" @click="openUser(user)"><Pencil :size="16" /></button><button v-if="user.id !== auth.user?.id" class="icon-btn danger-icon" title="Excluir" @click="requestDelete('user', user)"><Trash2 :size="16" /></button></div></td></tr></tbody></table></div></section>

    <section v-else class="group-grid acl-groups"><article v-for="group in groups" :key="group.id" class="group-card"><div class="group-card-head"><div class="group-icon"><ShieldCheck :size="22" /></div><span v-if="group.is_system" class="system-tag">PADRÃO</span></div><div><span class="eyebrow">{{ group.user_count }} USUÁRIO(S)</span><h2>{{ group.name }}</h2><p>{{ group.description || 'Grupo personalizado de acesso.' }}</p></div><div class="permission-pills"><span v-for="code in group.permissions.slice(0, 4)" :key="code">{{ permissionLabel(code) }}</span><span v-if="group.permissions.length > 4">+{{ group.permissions.length - 4 }}</span></div><footer><button class="btn secondary" @click="openGroup(group)"><Pencil :size="15" />Editar ACL</button><button v-if="!group.is_system" class="icon-btn danger-icon" title="Excluir grupo" @click="requestDelete('group', group)"><Trash2 :size="17" /></button></footer></article></section>

    <ModalDialog v-if="modal === 'customer'" :title="editing ? 'Editar cliente' : 'Cadastrar cliente'" @close="modal = null"><form @submit.prevent="saveCustomer"><div class="form-grid"><div class="form-field"><label>Tipo de pessoa</label><select v-model="customerForm.person_type"><option value="PF">Pessoa física</option><option value="PJ">Pessoa jurídica</option></select></div><div class="form-field"><label>CPF ou CNPJ</label><input v-model="customerForm.document" required /></div><div class="form-field span-2"><label>Nome / razão social</label><input v-model="customerForm.name" required /></div><div class="form-field"><label>E-mail</label><input v-model="customerForm.email" type="email" /></div><div class="form-field"><label>Telefone</label><input v-model="customerForm.phone" required /></div><div class="form-field span-2"><label>Endereço</label><input v-model="customerForm.address" /></div><label class="check-line span-2"><input v-model="customerForm.is_active" type="checkbox" />Cliente ativo</label></div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy">{{ editing ? 'Salvar alterações' : 'Salvar cliente' }}</button></div></form></ModalDialog>

    <ModalDialog v-if="modal === 'user'" :title="editing ? 'Editar funcionário' : 'Cadastrar funcionário'" @close="modal = null"><form @submit.prevent="saveUser"><div class="form-grid"><div class="form-field span-2"><label>Nome completo</label><input v-model="userForm.full_name" required /></div><div class="form-field"><label>E-mail</label><input v-model="userForm.email" type="email" required /></div><div class="form-field"><label>Telefone</label><input v-model="userForm.phone" /></div><div class="form-field span-2"><label>Grupo de acesso</label><select v-model="userForm.access_group" required><option v-for="group in groups" :key="group.id" :value="group.id">{{ group.name }}</option></select></div><div class="form-field span-2"><label>{{ editing ? 'Nova senha (opcional)' : 'Senha temporária' }}</label><input v-model="userForm.password" type="password" :required="!editing" /></div><label class="check-line span-2"><input v-model="userForm.is_active" type="checkbox" />Usuário ativo</label></div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy">Salvar funcionário</button></div></form></ModalDialog>

    <ModalDialog v-if="modal === 'group'" :title="editing ? 'Editar grupo e ACL' : 'Criar grupo de acesso'" wide @close="modal = null"><form @submit.prevent="saveGroup"><div class="form-grid"><div class="form-field"><label>Nome do grupo</label><input v-model="groupForm.name" required /></div><div class="form-field"><label>Descrição</label><input v-model="groupForm.description" /></div></div><div class="acl-editor"><header><div><span class="eyebrow">MATRIZ DE ACESSO</span><h3>Permissões do grupo</h3></div><span>{{ groupForm.permissions.includes('*') ? 'Acesso total' : `${groupForm.permissions.length} selecionadas` }}</span></header><label class="permission-master"><input type="checkbox" :checked="groupForm.permissions.includes('*')" @change="groupForm.permissions = $event.target.checked ? ['*'] : []" /><span><strong>Acesso total</strong><small>Ignora a matriz abaixo e libera todas as operações.</small></span></label><div v-if="!groupForm.permissions.includes('*')" class="permission-modules"><section v-for="[module, permissions] in modules" :key="module"><h4>{{ module }}</h4><label v-for="permission in permissions" :key="permission.code"><input type="checkbox" :checked="groupForm.permissions.includes(permission.code)" @change="togglePermission(permission.code)" /><span>{{ permission.label }}</span></label></section></div></div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null">Cancelar</button><span class="spacer" /><button class="btn primary" :disabled="busy">Salvar grupo</button></div></form></ModalDialog>

    <ConfirmDialog v-if="deleting" :title="`Excluir ${deleting.kind === 'group' ? 'grupo' : 'cadastro'}`" :message="`Esta ação excluirá “${deleting.item.name || deleting.item.full_name}”. Registros vinculados podem impedir a operação.`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
    <div v-if="error && !modal" class="floating-error">{{ error }}</div>
  </div>
</template>
