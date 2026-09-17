<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Eye, EyeOff, ShieldCheck, Wrench } from 'lucide-vue-next'
import { apiError, login } from '../services/api'

const router = useRouter()
const email = ref('admin@pandora.local')
const password = ref('Pandora@123')
const show = ref(false)
const loading = ref(false)
const error = ref('')
async function submit() {
  loading.value = true; error.value = ''
  try { await login(email.value, password.value); router.push('/') }
  catch (e) { error.value = apiError(e) }
  finally { loading.value = false }
}
</script>

<template>
  <div class="login-page">
    <section class="login-hero">
      <div class="hero-grid" />
      <div class="login-brand"><div class="brand-mark large">P</div><strong>PANDORA</strong></div>
      <div class="hero-copy"><span class="eyebrow light">OPERAÇÃO CONECTADA</span><h1>Equipamentos prontos.<br><em>Decisões mais seguras.</em></h1><p>Locação, inspeção e manutenção em uma única linha do tempo, da proposta à liberação técnica.</p></div>
      <div class="hero-proof"><ShieldCheck :size="20" /><span><strong>Rastreabilidade por projeto</strong>Permissões, evidências e decisões humanas registradas.</span></div>
    </section>
    <section class="login-panel">
      <form class="login-card" @submit.prevent="submit">
        <div class="mobile-brand"><div class="brand-mark">P</div><strong>PANDORA</strong></div>
        <span class="eyebrow">ACESSO INTERNO</span><h2>Bem-vindo de volta</h2><p class="muted">Entre com seu e-mail corporativo para continuar.</p>
        <div class="form-field"><label>E-mail</label><input v-model="email" type="email" autocomplete="email" placeholder="voce@empresa.com" required /></div>
        <div class="form-field"><label>Senha</label><div class="password-field"><input v-model="password" :type="show ? 'text' : 'password'" autocomplete="current-password" required /><button type="button" @click="show = !show"><component :is="show ? EyeOff : Eye" :size="19" /></button></div></div>
        <div v-if="error" class="error-message">{{ error }}</div>
        <button class="btn primary login-submit" :disabled="loading"><span>{{ loading ? 'Entrando...' : 'Entrar no PANDORA' }}</span><ArrowRight :size="18" /></button>
        <div class="demo-hint"><Wrench :size="18" /><span>Ambiente demonstrativo<br><strong>admin@pandora.local / Pandora@123</strong></span></div>
      </form>
    </section>
  </div>
</template>
