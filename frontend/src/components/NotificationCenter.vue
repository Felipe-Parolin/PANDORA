<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, BellOff, ClipboardList, Trash2, Truck, Wrench } from 'lucide-vue-next'
import { api, auth } from '../services/api'
import ConfirmDialog from './ConfirmDialog.vue'

const route = useRoute(), router = useRouter()
const open = ref(false), wrap = ref(null), items = ref([]), unread = ref(0), counts = ref({}), filter = ref('unread')
const loading = ref(false), error = ref(''), nextPage = ref(null), deleting = ref(null), busy = ref(false)
const kinds = {
  RENTAL: { label: 'Locações', icon: ClipboardList, tone: 'rental' },
  MAINTENANCE: { label: 'Manutenção', icon: Wrench, tone: 'maintenance' },
  TRANSPORT: { label: 'Transporte', icon: Truck, tone: 'transport' },
}
const tabs = computed(() => [
  { key: 'unread', label: 'Não lidas', count: unread.value },
  ...Object.entries(kinds).map(([key, value]) => ({ key, label: value.label, count: counts.value[key] || 0 })),
  { key: 'all', label: 'Todas', count: Object.values(counts.value).reduce((sum, value) => sum + value, 0) },
])
let request = 0, timer
async function load(append = false, quiet = false) {
  if (!auth.token) return
  const current = ++request, owner = auth.user?.id
  if (!quiet) loading.value = true
  error.value = ''
  const params = { page: append ? nextPage.value : 1 }
  if (filter.value === 'unread') params.status = 'unread'
  else if (kinds[filter.value]) params.kind = filter.value
  try {
    const { data } = await api.get('/notifications/', { params })
    if (current !== request || owner !== auth.user?.id || !auth.token) return
    items.value = append ? [...items.value, ...data.results] : data.results
    unread.value = data.unread_count; counts.value = data.counts || {}; nextPage.value = data.next_page
  } catch {
    if (current === request && owner === auth.user?.id) error.value = 'Não foi possível carregar as notificações.'
  } finally { if (current === request) loading.value = false }
}
function toggle() { open.value = !open.value; if (open.value) load() }
async function openItem(item) {
  try {
    if (!item.read_at) await api.post(`/notifications/${item.id}/read/`)
    await load()
    open.value = false
    if (item.target_url?.startsWith('/') && !item.target_url.startsWith('//')) await router.push(item.target_url)
  } catch { error.value = 'Não foi possível abrir a notificação.' }
}
async function markAllRead() {
  busy.value = true
  try { await api.post('/notifications/read-all/'); await load() }
  catch { error.value = 'Não foi possível marcar as notificações como lidas.' }
  finally { busy.value = false }
}
async function remove() {
  if (!deleting.value || busy.value) return
  busy.value = true
  try { await api.delete(`/notifications/${deleting.value.id}/`); deleting.value = null; open.value = true; await load() }
  catch { deleting.value = null; open.value = true; error.value = 'Não foi possível excluir a notificação. Tente novamente.' }
  finally { busy.value = false }
}
function timeAgo(value) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000))
  if (minutes < 1) return 'agora'
  if (minutes < 60) return `há ${minutes} min`
  if (minutes < 1440) return `há ${Math.floor(minutes / 60)} h`
  return new Date(value).toLocaleDateString('pt-BR')
}
function outside(event) { if (!deleting.value && wrap.value && !wrap.value.contains(event.target)) open.value = false }
function escape(event) { if (event.key === 'Escape') open.value = false }
watch(filter, () => { items.value = []; load() })
watch(() => route.fullPath, () => { open.value = false })
watch(() => auth.user?.id, () => {
  request += 1; items.value = []; unread.value = 0; counts.value = {}; nextPage.value = null; deleting.value = null; open.value = false; error.value = ''; loading.value = false
  if (filter.value !== 'unread') filter.value = 'unread'
  else load()
})
onMounted(() => {
  load()
  timer = window.setInterval(() => { if (!loading.value && !busy.value && (!open.value || items.value.length <= 30)) load(false, true) }, 30000)
  document.addEventListener('pointerdown', outside)
  document.addEventListener('keydown', escape)
})
onBeforeUnmount(() => { request += 1; window.clearInterval(timer); document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape) })
</script>

<template>
  <div ref="wrap" class="notification-wrap">
    <button class="icon-btn notification-trigger" type="button" :aria-expanded="open" aria-haspopup="dialog" aria-label="Notificações" @click="toggle"><Bell :size="20" /><span v-if="unread" class="notification-count">{{ unread > 99 ? '99+' : unread }}</span></button>
    <div v-if="open" class="notification-panel" role="dialog" aria-label="Notificações">
      <header><strong>Notificações</strong><button type="button" :disabled="!unread || busy" @click="markAllRead">Marcar todas como lidas</button></header>
      <div class="notification-selector"><label for="notification-filter">Mostrar</label><AppSelect id="notification-filter" v-model="filter"><option v-for="option in tabs" :key="option.key" :value="option.key">{{ option.label }} ({{ option.count }})</option></AppSelect></div>
      <div v-if="loading && !items.length" class="notification-empty" role="status">Carregando notificações...</div>
      <div v-else-if="!items.length" class="notification-empty"><BellOff :size="26" /><span>Nenhuma notificação nesta aba.</span></div>
      <div v-else class="notification-entries">
        <article v-for="item in items" :key="item.id" :class="{ unread: !item.read_at }">
          <button type="button" class="notification-open" @click="openItem(item)"><span class="notification-icon" :class="kinds[item.kind]?.tone"><component :is="kinds[item.kind]?.icon || Bell" :size="17" /></span><span class="notification-copy"><small>{{ kinds[item.kind]?.label || 'Sistema' }} · {{ timeAgo(item.created_at) }}</small><strong>{{ item.title }}</strong><span>{{ item.message }}</span></span></button>
          <button type="button" class="icon-btn danger-icon notification-delete" :aria-label="`Excluir notificação: ${item.title}`" title="Excluir notificação" :disabled="busy" @click="deleting = item"><Trash2 :size="16" /></button>
        </article>
        <button v-if="nextPage" class="btn secondary notification-more" :disabled="loading" @click="load(true)">{{ loading ? 'Carregando...' : 'Carregar mais' }}</button>
      </div>
    </div>
  </div>
  <GeneralError v-if="error" :message="error" @close="error = ''" />
  <ConfirmDialog v-if="deleting" title="Excluir notificação" :message="`Deseja excluir a notificação “${deleting.title}”? Esta ação remove somente a notificação do seu perfil.`" :busy="busy" @cancel="deleting = null" @confirm="remove" />
</template>

<style scoped>
.notification-tabs { flex-wrap: wrap; gap: 6px; padding-top: 4px; }
.notification-tabs button { padding-inline: 9px; font-size: 11px; }
.notification-entries { overflow-y: auto; overscroll-behavior: contain; }
.notification-entries article { display: flex; align-items: flex-start; gap: 4px; border-bottom: 1px solid var(--line); }
.notification-entries article.unread { background: #fffaf0; box-shadow: inset 3px 0 var(--amber); }
.notification-open { display: flex; align-items: flex-start; flex: 1; gap: 12px; min-width: 0; padding: 15px 8px 15px 17px; background: transparent; border: 0; text-align: left; cursor: pointer; }
.notification-open:hover { background: #00000004; }.notification-copy { display: grid; gap: 5px; min-width: 0; }.notification-copy strong { font-size: 13px; line-height: 1.45; overflow-wrap: anywhere; }.notification-copy > span { font-size: 12px; line-height: 1.5; color: var(--muted); }.notification-copy small { font-size: 10px; color: var(--muted); }
.notification-delete { flex-shrink: 0; margin: 12px 9px 0 0; }.notification-more { display: flex; margin: 12px auto; }
</style>
