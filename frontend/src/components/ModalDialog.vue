<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { X } from 'lucide-vue-next'
defineProps({ title: String, wide: Boolean, alert: Boolean, descriptionId: String })
defineEmits(['close'])
const dialog = ref(null)
let previousFocus
const focusable = () => Array.from(dialog.value?.querySelectorAll('button, input, textarea, select, a[href], [tabindex="0"]') || []).filter(element => !element.disabled && element.getAttribute('aria-hidden') !== 'true' && element.getClientRects().length)
function containFocus(event) {
  if (event.target?.closest?.('.calendar-panel')) return
  if (event.key !== 'Tab' || Array.from(document.querySelectorAll('.modal')).at(-1) !== dialog.value) return
  const elements = focusable(), first = elements[0], last = elements.at(-1)
  if (!first) { event.preventDefault(); dialog.value?.focus(); return }
  if (!dialog.value?.contains(document.activeElement) || (event.shiftKey && document.activeElement === first)) { event.preventDefault(); (event.shiftKey ? last : first).focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
const updateModalLock = delta => {
  const count = Math.max(Number(document.body.dataset.pandoraModalCount || 0) + delta, 0)
  document.body.dataset.pandoraModalCount = String(count)
  document.body.classList.toggle('modal-open', count > 0)
}
onMounted(() => {
  previousFocus = document.activeElement
  updateModalLock(1)
  document.addEventListener('keydown', containFocus)
  nextTick(() => focusable()[0]?.focus())
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', containFocus)
  updateModalLock(-1)
  if (previousFocus?.isConnected) previousFocus.focus()
})
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" :class="{ 'general-error-backdrop': alert }" @mousedown.self.prevent>
      <section ref="dialog" class="modal" :class="{ wide, 'general-error-dialog': alert }" :role="alert ? 'alertdialog' : 'dialog'" aria-modal="true" :aria-label="title" :aria-describedby="descriptionId" tabindex="-1">
        <header><div><span class="eyebrow">PANDORA</span><h2>{{ title }}</h2></div><button class="icon-btn modal-close" aria-label="Fechar janela" @click="$emit('close')"><X :size="20" /></button></header>
        <div class="modal-body"><slot /></div>
      </section>
    </div>
  </Teleport>
</template>
