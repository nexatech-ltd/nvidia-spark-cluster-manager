<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'

const router = useRouter()
const { get, post, del } = useApi()

const vms = ref([])
const loading = ref(true)
const error = ref('')
const nodeFilter = ref('all')
const viewMode = ref('grid')
const deleteConfirm = ref('')

const NODES = ['all', 'spark-1', 'spark-2']

const STATE_STYLES = {
  running: 'bg-green-500/15 text-green-400 border-green-500/30',
  shutoff: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
  paused: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  crashed: 'bg-red-500/15 text-red-400 border-red-500/30',
  pmsuspended: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
}

function stateClass(state) {
  return STATE_STYLES[state] || 'bg-gray-500/15 text-gray-400 border-gray-500/30'
}

const filteredVMs = computed(() => {
  if (nodeFilter.value === 'all') return vms.value
  return vms.value.filter(v => v.node === nodeFilter.value)
})

async function fetchVMs() {
  loading.value = true
  error.value = ''
  try {
    vms.value = await get('/vms/')
  } catch (e) {
    error.value = e.message || 'Failed to load VMs'
  }
  loading.value = false
}

onMounted(fetchVMs)

async function vmAction(vm, action) {
  try {
    await post(`/vms/${vm.name}/action?node=${vm.node}`, { action })
    await fetchVMs()
  } catch (e) {
    error.value = e.message || `Action '${action}' failed`
  }
}

async function deleteVM(vm) {
  if (deleteConfirm.value !== vm.name) {
    deleteConfirm.value = vm.name
    setTimeout(() => { deleteConfirm.value = '' }, 3000)
    return
  }
  deleteConfirm.value = ''
  try {
    await del(`/vms/${vm.name}?node=${vm.node}`)
    await fetchVMs()
  } catch (e) {
    error.value = e.message || 'Failed to delete VM'
  }
}

function goToVM(vm) {
  router.push({ path: `/vms/${vm.name}`, query: { node: vm.node } })
}

function formatMemory(mb) {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`
  return `${mb} MB`
}
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold text-gray-100">Virtual Machines</h2>
      <div class="flex items-center gap-2">
        <button
          @click="fetchVMs"
          class="px-3 py-1.5 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
        >
          Refresh
        </button>
        <router-link
          to="/vms/create"
          class="px-4 py-1.5 text-sm font-medium rounded-lg bg-nvidia hover:bg-nvidia-dark text-black transition-colors"
        >
          Create VM
        </router-link>
      </div>
    </div>

    <!-- Filters & View Toggle -->
    <div class="flex flex-wrap items-center gap-3 mb-4">
      <div class="flex gap-1">
        <button
          v-for="n in NODES"
          :key="n"
          @click="nodeFilter = n"
          class="px-3 py-1.5 text-xs rounded-lg border transition-colors capitalize"
          :class="nodeFilter === n
            ? 'bg-nvidia/10 text-nvidia border-nvidia/30'
            : 'bg-gray-800 text-gray-400 border-gray-600 hover:bg-gray-700'"
        >
          {{ n === 'all' ? 'All Nodes' : n }}
        </button>
      </div>

      <div class="flex-1" />

      <div class="flex gap-1 bg-gray-800 rounded-lg p-0.5 border border-gray-700">
        <button
          @click="viewMode = 'grid'"
          class="p-1.5 rounded-md transition-colors"
          :class="viewMode === 'grid' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-gray-200'"
          title="Grid view"
        >
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zM11 13a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
        </button>
        <button
          @click="viewMode = 'table'"
          class="p-1.5 rounded-md transition-colors"
          :class="viewMode === 'table' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-gray-200'"
          title="Table view"
        >
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M3 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm flex items-center justify-between">
      <span>{{ error }}</span>
      <button @click="error = ''" class="text-red-300 hover:text-white ml-3 shrink-0">&times;</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-2 text-gray-400 py-12 justify-center">
      <svg class="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Loading virtual machines...
    </div>

    <!-- Empty State -->
    <div v-else-if="!filteredVMs.length" class="text-center py-16 text-gray-500">
      <div class="text-4xl mb-3">⊟</div>
      <p v-if="vms.length" class="mb-1">No VMs match the selected filter</p>
      <p v-else class="mb-3">No virtual machines found</p>
      <router-link
        v-if="!vms.length"
        to="/vms/create"
        class="inline-block px-4 py-2 text-sm rounded-lg bg-nvidia/10 text-nvidia border border-nvidia/30 hover:bg-nvidia/20 transition-colors"
      >
        Create your first VM
      </router-link>
    </div>

    <!-- Grid View -->
    <div v-else-if="viewMode === 'grid'" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <div
        v-for="vm in filteredVMs"
        :key="vm.name + vm.node"
        class="bg-gray-800 rounded-xl border border-gray-700 hover:border-gray-600 transition-colors overflow-hidden"
      >
        <div class="p-5 cursor-pointer" @click="goToVM(vm)">
          <div class="flex items-start justify-between mb-3">
            <div class="min-w-0">
              <h3 class="font-semibold text-gray-100 truncate">{{ vm.name }}</h3>
              <span class="text-xs text-gray-500">{{ vm.node }}</span>
            </div>
            <span
              class="px-2 py-0.5 text-xs rounded-full border shrink-0 ml-2"
              :class="stateClass(vm.state)"
            >
              {{ vm.state }}
            </span>
          </div>

          <div class="grid grid-cols-2 gap-2 text-sm text-gray-400">
            <div class="flex items-center gap-1.5">
              <svg class="w-3.5 h-3.5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              {{ vm.vcpus }} vCPUs
            </div>
            <div class="flex items-center gap-1.5">
              <svg class="w-3.5 h-3.5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              {{ formatMemory(vm.memory_mb) }}
            </div>
          </div>
        </div>

        <div class="px-5 py-3 border-t border-gray-700/50 flex items-center gap-1.5 flex-wrap bg-gray-800/50">
          <button
            v-if="vm.state !== 'running'"
            @click.stop="vmAction(vm, 'start')"
            class="px-2 py-1 text-xs rounded-md bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors"
          >
            Start
          </button>
          <button
            v-if="vm.state === 'running'"
            @click.stop="vmAction(vm, 'shutdown')"
            class="px-2 py-1 text-xs rounded-md bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 hover:bg-yellow-500/20 transition-colors"
          >
            Shutdown
          </button>
          <button
            @click.stop="goToVM(vm)"
            class="px-2 py-1 text-xs rounded-md bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
          >
            Console
          </button>
          <div class="flex-1" />
          <button
            @click.stop="deleteVM(vm)"
            class="px-2 py-1 text-xs rounded-md transition-colors"
            :class="deleteConfirm === vm.name
              ? 'bg-red-500 text-white'
              : 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20'"
          >
            {{ deleteConfirm === vm.name ? 'Confirm?' : 'Delete' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Table View -->
    <div v-else class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-gray-400 border-b border-gray-700 bg-gray-800/80">
              <th class="py-3 px-4 font-medium">Name</th>
              <th class="py-3 px-4 font-medium">State</th>
              <th class="py-3 px-4 font-medium">vCPUs</th>
              <th class="py-3 px-4 font-medium">Memory</th>
              <th class="py-3 px-4 font-medium">Node</th>
              <th class="py-3 px-4 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="vm in filteredVMs"
              :key="vm.name + vm.node"
              class="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors cursor-pointer"
              @click="goToVM(vm)"
            >
              <td class="py-3 px-4 font-medium text-gray-100 whitespace-nowrap">{{ vm.name }}</td>
              <td class="py-3 px-4">
                <span class="px-2 py-0.5 text-xs rounded-full border" :class="stateClass(vm.state)">
                  {{ vm.state }}
                </span>
              </td>
              <td class="py-3 px-4 text-gray-400">{{ vm.vcpus }}</td>
              <td class="py-3 px-4 text-gray-400">{{ formatMemory(vm.memory_mb) }}</td>
              <td class="py-3 px-4 text-gray-400 text-xs">{{ vm.node }}</td>
              <td class="py-3 px-4 text-right">
                <div class="flex items-center justify-end gap-1 flex-wrap" @click.stop>
                  <button
                    v-if="vm.state !== 'running'"
                    @click="vmAction(vm, 'start')"
                    class="px-2 py-1 text-xs rounded-md bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors"
                  >
                    Start
                  </button>
                  <button
                    v-if="vm.state === 'running'"
                    @click="vmAction(vm, 'shutdown')"
                    class="px-2 py-1 text-xs rounded-md bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 hover:bg-yellow-500/20 transition-colors"
                  >
                    Shutdown
                  </button>
                  <button
                    @click="goToVM(vm)"
                    class="px-2 py-1 text-xs rounded-md bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
                  >
                    Console
                  </button>
                  <button
                    @click="deleteVM(vm)"
                    class="px-2 py-1 text-xs rounded-md transition-colors"
                    :class="deleteConfirm === vm.name
                      ? 'bg-red-500 text-white'
                      : 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20'"
                  >
                    {{ deleteConfirm === vm.name ? 'Confirm?' : 'Delete' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
