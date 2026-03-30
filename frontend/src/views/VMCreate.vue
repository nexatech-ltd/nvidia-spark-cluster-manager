<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'

const router = useRouter()
const { get, post } = useApi()

const MEMORY_PRESETS = [1024, 2048, 4096, 8192, 16384]
const NODES = ['spark-1', 'spark-2']

const form = ref({
  name: '',
  node: 'spark-1',
  vcpus: 4,
  memory_mb: 4096,
  disk_size_gb: 20,
  disk_format: 'qcow2',
  iso: '',
  network: 'default',
  os_variant: 'generic',
})

const isos = ref([])
const isosLoading = ref(false)
const submitting = ref(false)
const error = ref('')

async function fetchISOs() {
  isosLoading.value = true
  try {
    isos.value = await get(`/vms/isos/?node=${form.value.node}`)
  } catch { /* ignore */ }
  isosLoading.value = false
}

onMounted(fetchISOs)

function onNodeChange() {
  form.value.iso = ''
  fetchISOs()
}

function setMemoryPreset(mb) {
  form.value.memory_mb = mb
}

async function create() {
  error.value = ''
  if (!form.value.name.trim()) {
    error.value = 'VM name is required'
    return
  }
  submitting.value = true
  try {
    const payload = { ...form.value }
    if (!payload.iso) payload.iso = null
    await post('/vms/', payload)
    router.push('/vms')
  } catch (e) {
    error.value = e.message || 'Failed to create VM'
  }
  submitting.value = false
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i]
}
</script>

<template>
  <div class="max-w-2xl">
    <!-- Back nav -->
    <button
      class="text-sm text-gray-400 hover:text-white mb-4 flex items-center gap-1 transition-colors"
      @click="router.push('/vms')"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
      </svg>
      Back to VMs
    </button>

    <h2 class="text-2xl font-bold text-gray-100 mb-6">Create Virtual Machine</h2>

    <!-- Error -->
    <div v-if="error" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm flex items-center justify-between">
      <span>{{ error }}</span>
      <button @click="error = ''" class="text-red-300 hover:text-white ml-3 shrink-0">&times;</button>
    </div>

    <form @submit.prevent="create" class="space-y-5">
      <!-- Name -->
      <div>
        <label class="block text-sm font-medium text-gray-300 mb-1.5">VM Name</label>
        <input
          v-model="form.name"
          required
          placeholder="my-vm"
          class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50 placeholder-gray-500"
        />
      </div>

      <!-- Node -->
      <div>
        <label class="block text-sm font-medium text-gray-300 mb-1.5">Node</label>
        <div class="flex gap-2">
          <button
            v-for="n in NODES"
            :key="n"
            type="button"
            @click="form.node = n; onNodeChange()"
            class="flex-1 px-4 py-2.5 text-sm rounded-lg border transition-colors font-medium"
            :class="form.node === n
              ? 'bg-nvidia/10 text-nvidia border-nvidia/30'
              : 'bg-gray-800 text-gray-400 border-gray-600 hover:bg-gray-700'"
          >
            {{ n }}
          </button>
        </div>
      </div>

      <!-- vCPUs & Memory -->
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">vCPUs</label>
          <input
            v-model.number="form.vcpus"
            type="number"
            min="1"
            max="20"
            class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">Memory (MB)</label>
          <input
            v-model.number="form.memory_mb"
            type="number"
            min="256"
            step="256"
            class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50"
          />
          <div class="flex gap-1.5 mt-2">
            <button
              v-for="preset in MEMORY_PRESETS"
              :key="preset"
              type="button"
              @click="setMemoryPreset(preset)"
              class="px-2 py-0.5 text-xs rounded border transition-colors"
              :class="form.memory_mb === preset
                ? 'bg-nvidia/10 text-nvidia border-nvidia/30'
                : 'bg-gray-800 text-gray-500 border-gray-600 hover:bg-gray-700 hover:text-gray-300'"
            >
              {{ preset >= 1024 ? `${preset / 1024}G` : `${preset}M` }}
            </button>
          </div>
        </div>
      </div>

      <!-- Disk -->
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">Disk Size (GB)</label>
          <input
            v-model.number="form.disk_size_gb"
            type="number"
            min="1"
            class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">Disk Format</label>
          <div class="flex gap-2">
            <button
              v-for="fmt in ['qcow2', 'raw']"
              :key="fmt"
              type="button"
              @click="form.disk_format = fmt"
              class="flex-1 px-3 py-2.5 text-sm rounded-lg border transition-colors"
              :class="form.disk_format === fmt
                ? 'bg-nvidia/10 text-nvidia border-nvidia/30'
                : 'bg-gray-800 text-gray-400 border-gray-600 hover:bg-gray-700'"
            >
              {{ fmt }}
            </button>
          </div>
        </div>
      </div>

      <!-- ISO -->
      <div>
        <label class="block text-sm font-medium text-gray-300 mb-1.5">
          Boot ISO
          <span class="text-gray-500 font-normal">(optional)</span>
        </label>
        <select
          v-model="form.iso"
          class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50"
        >
          <option value="">None (import existing disk)</option>
          <option v-for="iso in isos" :key="iso.name" :value="iso.name">
            {{ iso.name }} ({{ formatBytes(iso.size) }})
          </option>
        </select>
        <p v-if="isosLoading" class="text-xs text-gray-500 mt-1">Loading ISOs from {{ form.node }}...</p>
      </div>

      <!-- Network & OS Variant -->
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">Network Bridge</label>
          <input
            v-model="form.network"
            class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50"
            placeholder="default"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">OS Variant</label>
          <input
            v-model="form.os_variant"
            class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50"
            placeholder="generic"
          />
          <p class="text-xs text-gray-500 mt-1">e.g. ubuntu22.04, debian11, win11, generic</p>
        </div>
      </div>

      <!-- Summary -->
      <div class="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
        <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Summary</h3>
        <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <span class="text-gray-500">Name:</span>
          <span class="text-gray-200">{{ form.name || '—' }}</span>
          <span class="text-gray-500">Node:</span>
          <span class="text-gray-200">{{ form.node }}</span>
          <span class="text-gray-500">CPU / RAM:</span>
          <span class="text-gray-200">{{ form.vcpus }} vCPUs / {{ form.memory_mb }} MB</span>
          <span class="text-gray-500">Disk:</span>
          <span class="text-gray-200">{{ form.disk_size_gb }} GB ({{ form.disk_format }})</span>
          <span class="text-gray-500">ISO:</span>
          <span class="text-gray-200">{{ form.iso || 'None' }}</span>
        </div>
      </div>

      <!-- Submit -->
      <div class="flex items-center gap-3 pt-2">
        <button
          type="submit"
          :disabled="submitting"
          class="px-6 py-2.5 bg-nvidia hover:bg-nvidia-dark text-black font-medium rounded-lg text-sm transition-colors disabled:opacity-50"
        >
          <span v-if="submitting" class="flex items-center gap-2">
            <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Creating...
          </span>
          <span v-else>Create VM</span>
        </button>
        <button
          type="button"
          @click="router.push('/vms')"
          class="px-6 py-2.5 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  </div>
</template>
