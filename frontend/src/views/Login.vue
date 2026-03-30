<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'

const router = useRouter()
const { login } = useApi()

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await login(username.value, password.value)
    router.push('/')
  } catch (e) {
    error.value = 'Invalid credentials'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-900 px-4">
    <div class="w-full max-w-sm">
      <div class="text-center mb-8">
        <span class="text-nvidia font-bold text-4xl">⚡</span>
        <h1 class="mt-3 text-2xl font-bold text-white">
          <span class="text-nvidia">Spark</span> Cluster Manager
        </h1>
        <p class="mt-1 text-sm text-gray-400">Sign in to continue</p>
      </div>

      <form
        @submit.prevent="handleLogin"
        class="bg-gray-800 border border-gray-700 rounded-xl p-6 space-y-4"
      >
        <div v-if="error" class="bg-red-500/10 border border-red-500/30 text-red-400 text-sm rounded-lg px-3 py-2">
          {{ error }}
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-400 mb-1.5">Username</label>
          <input
            v-model="username"
            type="text"
            autocomplete="username"
            required
            class="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-white
                   placeholder-gray-500 focus:outline-none focus:border-nvidia focus:ring-1 focus:ring-nvidia
                   transition-colors"
            placeholder="admin"
          />
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-400 mb-1.5">Password</label>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            class="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-white
                   placeholder-gray-500 focus:outline-none focus:border-nvidia focus:ring-1 focus:ring-nvidia
                   transition-colors"
            placeholder="••••••••"
          />
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="w-full bg-nvidia hover:bg-nvidia-dark text-black font-semibold py-2.5 px-4 rounded-lg
                 text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ loading ? 'Signing in...' : 'Sign In' }}
        </button>
      </form>
    </div>
  </div>
</template>
