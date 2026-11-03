<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Eye, EyeOff } from 'lucide-vue-next'
import { apiError, login } from '../services/api'

const router = useRouter()
const email = ref('')
const password = ref('')
const show = ref(false)
const loading = ref(false)
const error = ref('')
async function submit() {
  if (loading.value) return
  loading.value = true; error.value = ''
  try { await login(email.value.trim(), password.value); router.push('/') }
  catch (e) { error.value = apiError(e) }
  finally { loading.value = false }
}
</script>

<template>
  <main class="login-page">
    <section class="login-intro" aria-label="PANDORA, gestão de equipamentos">
      <div class="login-intro-brand"><div class="brand-mark" aria-hidden="true">P</div><strong>PANDORA</strong></div>
      <div class="login-intro-copy"><span class="login-rule" aria-hidden="true" /><h2>Gestão de<br />equipamentos.</h2><p>Locação, transporte<br />e manutenção.</p></div>
      <footer>Mazzi Materiais de Construção</footer>
    </section>
    <section class="login-access">
    <form class="login-card" :aria-busy="loading" aria-labelledby="login-title" @submit.prevent="submit">
      <header><span class="eyebrow">ACESSO AO SISTEMA</span><h1 id="login-title">Entrar no PANDORA</h1><p>Informe seu e-mail e sua senha.</p></header>
      <div class="form-field"><label for="login-email">E-mail<span class="required-mark" aria-hidden="true"> *</span></label><input id="login-email" v-model="email" type="email" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="seu@email.com" :disabled="loading" required /></div>
      <div class="form-field"><label for="login-password">Senha<span class="required-mark" aria-hidden="true"> *</span></label><div class="password-field"><input id="login-password" v-model="password" :type="show ? 'text' : 'password'" autocomplete="current-password" :disabled="loading" required /><button type="button" :aria-label="show ? 'Ocultar senha' : 'Mostrar senha'" :aria-pressed="show" :disabled="loading" @click="show = !show"><component :is="show ? EyeOff : Eye" :size="19" /></button></div></div>
      <div v-if="error" class="error-message" role="alert">{{ error }}</div>
      <button type="submit" class="btn primary login-submit" :disabled="loading"><span>{{ loading ? 'Entrando...' : 'Entrar' }}</span><ArrowRight :size="18" /></button>
    </form>
    </section>
  </main>
</template>

<style scoped>
.login-page { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); min-height: 100vh; min-height: 100dvh; background: var(--white); }
.login-intro { position: relative; isolation: isolate; overflow: hidden; display: flex; flex-direction: column; justify-content: space-between; gap: 64px; padding: clamp(36px, 5vw, 76px); border-right: 4px solid var(--amber); color: white; background: var(--ink); }
.login-intro::before { content: ''; position: absolute; inset: 0; z-index: 0; pointer-events: none; background-image: linear-gradient(#ffffff12 1px, transparent 1px), linear-gradient(90deg, #ffffff12 1px, transparent 1px); background-size: 48px 48px; mask-image: linear-gradient(135deg, black, transparent 85%); }
.login-intro > * { position: relative; z-index: 1; }
.login-intro-brand { display: flex; align-items: center; gap: 14px; }.login-intro-brand strong { font-size: 19px; letter-spacing: .16em; }.login-intro-brand .brand-mark { width: 46px; height: 46px; }
.login-intro-copy { margin-block: 30px; }.login-rule { display: block; width: 56px; height: 4px; margin-bottom: 28px; background: var(--amber); }
.login-intro h2 { margin: 0; font-size: clamp(38px, 4.5vw, 66px); line-height: 1.12; font-weight: 700; letter-spacing: -.045em; }
.login-intro p { margin: 24px 0 0; font-size: clamp(17px, 1.7vw, 22px); line-height: 1.6; color: #b8babe; }.login-intro footer { color: #a4a6aa; font-size: 12px; }
.login-access { display: grid; place-items: center; padding: 64px 40px; }.login-card { width: min(370px, 100%); }
.login-card header { margin-bottom: 36px; }.login-card header .eyebrow { display: block; margin-bottom: 14px; color: var(--burnt); font-size: 10px; letter-spacing: .12em; }
.login-card h1 { margin: 0 0 12px; font-size: 28px; letter-spacing: -.04em; }
.login-card p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.6; }
.form-field { margin-bottom: 20px; }
.form-field label { text-transform: none; font-size: 13px; letter-spacing: 0; }
.form-field input { min-height: 48px; padding: 12px; font-size: 16px; }
.password-field { display: flex; border: 1px solid var(--line); border-radius: 8px; }
.password-field:focus-within { border-color: var(--amber); box-shadow: 0 0 0 3px #f0a50020; }
.password-field input { min-width: 0; border: 0; box-shadow: none; }
.password-field button { display: grid; place-items: center; flex-shrink: 0; width: 46px; border: 0; border-radius: 0 8px 8px 0; color: var(--muted); background: transparent; cursor: pointer; }
.password-field button:hover { color: var(--ink); background: var(--paper); }
.login-submit { display: flex; justify-content: space-between; width: 100%; min-height: 48px; margin-top: 8px; padding-inline: 16px; }
@media (max-width: 820px) { .login-page { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }.login-intro { padding: 24px 32px; border-right: 0; border-bottom: 3px solid var(--amber); }.login-intro-copy, .login-intro footer { display: none; }.login-access { padding: 48px 32px; }.login-card h1 { font-size: 26px; } }
@media (max-width: 380px) { .login-intro { padding: 20px 24px; }.login-access { padding: 36px 24px; } }
</style>
