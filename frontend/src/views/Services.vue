<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi'
import LogViewer from '../components/LogViewer.vue'

const { get, post } = useApi()

const services = ref([])
const loading = ref(true)
const error = ref('')

const showScale = ref(false)
const scaleService = ref(null)
const scaleReplicas = ref(1)
const scaling = ref(false)
const scaleError = ref('')

const showLogs = ref(false)
const logTitle = ref('')
const logWsUrl = ref('')

async function fetchServices() {
  loading.value = true
  error.value = ''
  try {
    services.value = await get('/docker/services')
  } catch (e) {
    error.value = e.message || 'Failed to load services'
  }
  loading.value = false
}

onMounted(fetchServices)

function openScale(svc) {
  scaleService.value = svc
  const match = svc.replicas.match(/^(\d+)\/(\d+)$/)
  scaleReplicas.value = match ? parseInt(match[2]) : 1
  scaleError.value = ''
  showScale.value = true
}

async function doScale() {
  scaling.value = true
  scaleError.value = ''
  try {
    await post(`/docker/services/${scaleService.value.id}/scale?replicas=${scaleReplicas.value}`)
    showScale.value = false
    await fetchServices()
  } catch (e) {
    scaleError.value = e.message || 'Scale failed'
  }
  scaling.value = false
}

function openLogs(svc) {
  logTitle.value = `Service Logs: ${svc.name}`
  logWsUrl.value = `/api/docker/ws/logs/service/${svc.id}`
  showLogs.value = true
}

function replicaColor(replicas) {
  const match = replicas.match(/^(\d+)\/(\d+)$/)
  if (!match) return 'text-gray-400'
  return parseInt(match[1]) >= parseInt(match[2]) ? 'text-green-400' : 'text-yellow-400'
}
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold text-gray-100">Services</h2>
      <button
        @click="fetchServices"
        class="px-3 py-1.5 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
      >
        Refresh
      </button>
    </div>

    <!-- Error -->
    <div v-if="error" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
      {{ error }}
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-2 text-gray-400">
      <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Loading services...
    </div>

    <!-- Empty -->
    <div v-else-if="!services.length" class="text-center py-16 text-gray-500">
      <div class="text-4xl mb-3">⚙</div>
      <p>No services running</p>
    </div>

    <!-- Services table -->
    <div v-else class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-gray-400 border-b border-gray-700 bg-gray-800/80">
            <th class="py-3 px-4 font-medium">Name</th>
            <th class="py-3 px-4 font-medium">Mode</th>
            <th class="py-3 px-4 font-medium">Replicas</th>
            <th class="py-3 px-4 font-medium">Image</th>
            <th class="py-3 px-4 font-medium">Ports</th>
            <th class="py-3 px-4 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="svc in services"
            :key="svc.id"
            class="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors"
          >
            <td class="py-3 px-4 font-medium text-gray-100">{{ svc.name }}</td>
            <td class="py-3 px-4">
              <span class="px-2 py-0.5 text-xs rounded-full bg-gray-700 text-gray-300">
                {{ svc.mode }}
              </span>
            </td>
            <td class="py-3 px-4">
              <span class="font-mono text-sm" :class="replicaColor(svc.replicas)">
                {{ svc.replicas }}
              </span>
            </td>
            <td class="py-3 px-4 text-gray-400 font-mono text-xs truncate max-w-xs" :title="svc.image">
              {{ svc.image }}
            </td>
            <td class="py-3 px-4 text-gray-400 text-xs">
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="port in svc.ports"
                  :key="port"
                  class="px-1.5 py-0.5 rounded bg-gray-700/50 font-mono"
                >
                  {{ port }}
                </span>
                <span v-if="!svc.ports.length" class="text-gray-600">—</span>
              </div>
            </td>
            <td class="py-3 px-4 text-right">
              <div class="flex items-center justify-end gap-1.5">
                <button
                  @click="openScale(svc)"
                  class="px-2.5 py-1 text-xs rounded-md bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
                >
                  Scale
                </button>
                <button
                  @click="openLogs(svc)"
                  class="px-2.5 py-1 text-xs rounded-md bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white transition-colors"
                >
                  Logs
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Scale Dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showScale" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showScale = false">
          <div class="w-full max-w-sm bg-gray-900 rounded-xl border border-gray-700 shadow-2xl">
            <div class="px-5 py-4 border-b border-gray-700">
              <h3 class="text-lg font-semibold text-gray-100">Scale Service</h3>
              <p class="text-sm text-gray-400 mt-1">{{ scaleService?.name }}</p>
            </div>
            <div class="p-5">
              <div v-if="scaleError" class="mb-3 p-2 rounded bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
                {{ scaleError }}
              </div>
              <label class="block text-sm font-medium text-gray-300 mb-1.5">Replicas</label>
              <input
                v-model.number="scaleReplicas"
                type="number"
                min="0"
                max="100"
                class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50"
              />
            </div>
            <div class="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-700">
              <button
                @click="showScale = false"
                class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button
                @click="doScale"
                :disabled="scaling"
                class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 disabled:opacity-50 transition-colors"
              >
                {{ scaling ? 'Scaling...' : 'Apply' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Log Viewer -->
    <LogViewer
      :wsUrl="logWsUrl"
      :title="logTitle"
      :visible="showLogs"
      @close="showLogs = false"
    />
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
