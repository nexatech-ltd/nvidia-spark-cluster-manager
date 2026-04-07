<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'

const router = useRouter()
const { get, post } = useApi()

const MEMORY_PRESETS = [1024, 2048, 4096, 8192, 16384, 32768, 65536]

const nodes = ref([])
const isos = ref([])
const bridges = ref([])
const osVariants = ref([])
const isosLoading = ref(false)
const bridgesLoading = ref(false)
const osVariantsLoading = ref(false)
const submitting = ref(false)
const error = ref('')
const osSearch = ref('')
const osDropdownOpen = ref(false)

const form = ref({
  name: '',
  node: '',
  vcpus: 4,
  memory_mb: 4096,
  disk_size_gb: 20,
  disk_format: 'qcow2',
  iso: '',
  network: '',
  os_variant: 'generic',
})

const filteredVariants = computed(() => {
  const q = osSearch.value.toLowerCase()
  if (!q) return osVariants.value
  return osVariants.value.filter(v => v.toLowerCase().includes(q))
})

async function fetchNodes() {
  try {
    const health = await get('/health')
    nodes.value = health.nodes || []
    if (nodes.value.length && !form.value.node) {
      form.value.node = nodes.value[0]
    }
  } catch { /* ignore */ }
}

async function fetchISOs() {
  isosLoading.value = true
  try {
    isos.value = await get(`/vms/isos/?node=${form.value.node}`)
  } catch { /* ignore */ }
  isosLoading.value = false
}

async function fetchBridges() {
  bridgesLoading.value = true
  try {
    bridges.value = await get(`/vms/bridges/?node=${form.value.node}`)
    if (bridges.value.length && !bridges.value.find(b => b.name === form.value.network)) {
      form.value.network = bridges.value[0].name
    }
  } catch { /* ignore */ }
  bridgesLoading.value = false
}

async function fetchOsVariants() {
  osVariantsLoading.value = true
  try {
    osVariants.value = await get(`/vms/os-variants/?node=${form.value.node}`)
  } catch { /* ignore */ }
  osVariantsLoading.value = false
}

watch(() => form.value.node, (val) => {
  if (val) {
    form.value.iso = ''
    fetchISOs()
    fetchBridges()
    fetchOsVariants()
  }
})

onMounted(async () => {
  await fetchNodes()
  if (form.value.node) {
    fetchISOs()
    fetchBridges()
    fetchOsVariants()
  }
})

function selectOsVariant(val) {
  form.value.os_variant = val
  osDropdownOpen.value = false
  osSearch.value = ''
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
            v-for="n in nodes"
            :key="n"
            type="button"
            @click="form.node = n"
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
            max="72"
            class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50"
          />
          <p class="text-xs text-gray-500 mt-1">Grace CPU: up to 72 cores</p>
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
          <div class="flex flex-wrap gap-1.5 mt-2">
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
          <option v-for="iso in isos" :key="iso.path" :value="iso.path">
            {{ iso.name }} ({{ formatBytes(iso.size) }}) &mdash; {{ iso.path }}
          </option>
        </select>
        <p v-if="isosLoading" class="text-xs text-gray-500 mt-1">Loading ISOs from {{ form.node }}...</p>
        <p v-else class="text-xs text-gray-500 mt-1">
          Place ISO files in <code class="text-gray-400">/var/lib/libvirt/isos</code> on the node, or upload via File Browser to <code class="text-gray-400">/data/shared*</code>
        </p>
      </div>

      <!-- Network Bridge & OS Variant -->
      <div class="grid grid-cols-2 gap-4">
        <!-- Network Bridge -->
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">Network Bridge</label>
          <select
            v-if="bridges.length"
            v-model="form.network"
            class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50"
          >
            <option v-for="br in bridges" :key="br.name" :value="br.name">
              {{ br.name }} ({{ br.type === 'network' ? 'libvirt' : br.state }})
            </option>
          </select>
          <input
            v-else
            v-model="form.network"
            placeholder="e.g. virbr0, br0"
            class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50 placeholder-gray-500"
          />
          <p v-if="bridgesLoading" class="text-xs text-gray-500 mt-1">Loading bridges...</p>
          <div v-else-if="!bridges.length" class="mt-1.5 p-2 rounded bg-amber-500/10 border border-amber-500/20">
            <p class="text-xs text-amber-400">No bridges detected on {{ form.node }}. Create one with:</p>
            <code class="block text-xs text-amber-300 mt-1">sudo virsh net-start default</code>
            <p class="text-xs text-amber-400 mt-0.5">or configure a custom bridge via <code class="text-amber-300">nmcli</code></p>
          </div>
        </div>

        <!-- OS Variant -->
        <div class="relative">
          <label class="block text-sm font-medium text-gray-300 mb-1.5">OS Variant</label>
          <button
            type="button"
            @click="osDropdownOpen = !osDropdownOpen"
            class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-left text-gray-100 focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50 flex items-center justify-between"
          >
            <span>{{ form.os_variant }}</span>
            <svg class="w-4 h-4 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          <div
            v-if="osDropdownOpen"
            class="absolute z-20 mt-1 w-full bg-gray-800 border border-gray-600 rounded-lg shadow-xl max-h-64 overflow-hidden flex flex-col"
          >
            <input
              v-model="osSearch"
              placeholder="Search OS variant..."
              class="px-3 py-2 bg-gray-750 border-b border-gray-600 text-sm text-gray-100 focus:outline-none placeholder-gray-500"
            />
            <ul class="overflow-y-auto max-h-56">
              <li
                v-for="v in filteredVariants"
                :key="v"
                @click="selectOsVariant(v)"
                class="px-3 py-1.5 text-sm cursor-pointer transition-colors"
                :class="form.os_variant === v
                  ? 'bg-nvidia/10 text-nvidia'
                  : 'text-gray-300 hover:bg-gray-700'"
              >
                {{ v }}
              </li>
              <li v-if="!filteredVariants.length" class="px-3 py-2 text-sm text-gray-500">No match</li>
            </ul>
          </div>
          <p v-if="osVariantsLoading" class="text-xs text-gray-500 mt-1">Loading variants...</p>
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
          <span class="text-gray-200">{{ form.vcpus }} vCPUs / {{ form.memory_mb >= 1024 ? `${(form.memory_mb / 1024).toFixed(1)} GB` : `${form.memory_mb} MB` }}</span>
          <span class="text-gray-500">Disk:</span>
          <span class="text-gray-200">{{ form.disk_size_gb }} GB ({{ form.disk_format }})</span>
          <span class="text-gray-500">ISO:</span>
          <span class="text-gray-200">{{ form.iso ? isos.find(i => i.path === form.iso)?.name || form.iso : 'None' }}</span>
          <span class="text-gray-500">Network:</span>
          <span class="text-gray-200">{{ form.network || '—' }}</span>
          <span class="text-gray-500">OS:</span>
          <span class="text-gray-200">{{ form.os_variant }}</span>
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
