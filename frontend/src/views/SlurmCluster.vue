<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useApi } from '../composables/useApi'

const { get } = useApi()

const cluster = ref(null)
const loading = ref(true)
const error = ref('')
let refreshTimer = null

async function fetchCluster() {
  try {
    cluster.value = await get('/slurm/cluster')
    error.value = ''
  } catch (e) {
    error.value = e.message || 'Failed to load cluster info'
  }
  loading.value = false
}

onMounted(() => {
  fetchCluster()
  refreshTimer = setInterval(fetchCluster, 10000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

const nodes = computed(() => cluster.value?.nodes ?? [])
const jobsRunning = computed(() => cluster.value?.jobs_running ?? 0)
const jobsPending = computed(() => cluster.value?.jobs_pending ?? 0)

function stateColor(state) {
  if (!state) return { bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/20', dot: 'bg-gray-400' }
  const s = state.toLowerCase()
  if (s.includes('idle')) return { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/20', dot: 'bg-green-400' }
  if (s.includes('alloc')) return { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/20', dot: 'bg-blue-400' }
  if (s.includes('mixed') || s.includes('mix')) return { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/20', dot: 'bg-yellow-400' }
  if (s.includes('down') || s.includes('drain')) return { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/20', dot: 'bg-red-400' }
  return { bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/20', dot: 'bg-gray-400' }
}

function cpuPercent(node) {
  if (!node.cpus) return 0
  return Math.round((node.alloc_cpus / node.cpus) * 100)
}

function memPercent(node) {
  if (!node.memory) return 0
  return Math.round((node.alloc_memory / node.memory) * 100)
}

function formatMem(mb) {
  if (!mb) return '0'
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`
  return `${mb} MB`
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold text-gray-100">Slurm Cluster</h2>
      <div class="flex items-center gap-2 text-xs text-gray-500">
        <div class="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
        Auto-refresh 10s
      </div>
    </div>

    <div v-if="error" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
      {{ error }}
    </div>

    <div v-if="loading" class="flex items-center gap-2 text-gray-400">
      <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Loading cluster info...
    </div>

    <template v-else-if="cluster">
      <!-- Job Summary -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <div class="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <div class="text-xs text-gray-500 uppercase tracking-wider mb-1">Nodes</div>
          <div class="text-2xl font-bold text-gray-100">{{ nodes.length }}</div>
        </div>
        <div class="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <div class="text-xs text-gray-500 uppercase tracking-wider mb-1">Running Jobs</div>
          <div class="text-2xl font-bold text-green-400">{{ jobsRunning }}</div>
        </div>
        <div class="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <div class="text-xs text-gray-500 uppercase tracking-wider mb-1">Pending Jobs</div>
          <div class="text-2xl font-bold text-yellow-400">{{ jobsPending }}</div>
        </div>
        <div class="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <div class="text-xs text-gray-500 uppercase tracking-wider mb-1">Total GPUs</div>
          <div class="text-2xl font-bold text-nvidia">{{ nodes.reduce((s, n) => s + (n.gpus || 0), 0) }}</div>
        </div>
      </div>

      <!-- Node Cards -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div
          v-for="node in nodes" :key="node.name"
          class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden"
        >
          <!-- Node Header -->
          <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700">
            <div class="flex items-center gap-3">
              <div class="w-2.5 h-2.5 rounded-full" :class="stateColor(node.state).dot" />
              <h3 class="font-semibold text-gray-100">{{ node.name }}</h3>
            </div>
            <span
              class="px-2.5 py-0.5 text-xs rounded-full border"
              :class="[stateColor(node.state).bg, stateColor(node.state).text, stateColor(node.state).border]"
            >
              {{ node.state }}
            </span>
          </div>

          <div class="p-5 space-y-4">
            <!-- CPUs -->
            <div>
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-sm text-gray-400">CPUs</span>
                <span class="text-sm text-gray-300">{{ node.alloc_cpus }} / {{ node.cpus }}</span>
              </div>
              <div class="h-2 bg-gray-700 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-500"
                  :class="cpuPercent(node) > 80 ? 'bg-orange-500' : 'bg-blue-500'"
                  :style="{ width: `${cpuPercent(node)}%` }"
                />
              </div>
              <div class="text-xs text-gray-500 mt-1">{{ cpuPercent(node) }}% utilized</div>
            </div>

            <!-- Memory -->
            <div>
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-sm text-gray-400">Memory</span>
                <span class="text-sm text-gray-300">{{ formatMem(node.alloc_memory) }} / {{ formatMem(node.memory) }}</span>
              </div>
              <div class="h-2 bg-gray-700 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-500"
                  :class="memPercent(node) > 80 ? 'bg-orange-500' : 'bg-purple-500'"
                  :style="{ width: `${memPercent(node)}%` }"
                />
              </div>
              <div class="text-xs text-gray-500 mt-1">{{ memPercent(node) }}% utilized</div>
            </div>

            <!-- GPUs -->
            <div class="flex items-center justify-between">
              <span class="text-sm text-gray-400">GPUs</span>
              <span class="text-sm font-medium text-nvidia">{{ node.gpus }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
