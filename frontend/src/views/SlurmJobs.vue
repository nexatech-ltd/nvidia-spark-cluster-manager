<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useApi } from '../composables/useApi'
import LogViewer from '../components/LogViewer.vue'

const { get, post, del } = useApi()

const jobs = ref([])
const templates = ref([])
const loading = ref(true)
const error = ref('')
let refreshTimer = null

const showSubmit = ref(false)
const scriptMode = ref(false)
const submitForm = ref({
  name: '', partition: 'gpu', nodes: 1, ntasks_per_node: 1,
  gpus_per_node: 1, container_image: '', command: '', working_dir: '/data',
  script: '',
})
const submitting = ref(false)
const submitError = ref('')
const selectedTemplate = ref('')

const logVisible = ref(false)
const logJobId = ref('')
const logTitle = ref('')

const cancelConfirm = ref('')

async function fetchJobs() {
  try {
    jobs.value = await get('/slurm/jobs')
    error.value = ''
  } catch (e) {
    error.value = e.message || 'Failed to load jobs'
  }
  loading.value = false
}

async function fetchTemplates() {
  try {
    templates.value = await get('/slurm/templates')
  } catch { /* non-critical */ }
}

onMounted(() => {
  fetchJobs()
  fetchTemplates()
  refreshTimer = setInterval(fetchJobs, 5000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

function stateColor(state) {
  const map = {
    RUNNING: 'bg-green-500/10 text-green-400 border-green-500/20',
    PENDING: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    COMPLETED: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    FAILED: 'bg-red-500/10 text-red-400 border-red-500/20',
    CANCELLED: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
  }
  return map[state] ?? 'bg-gray-500/10 text-gray-400 border-gray-500/20'
}

function openSubmit() {
  submitForm.value = {
    name: '', partition: 'gpu', nodes: 1, ntasks_per_node: 1,
    gpus_per_node: 1, container_image: '', command: '', working_dir: '/data',
    script: '',
  }
  selectedTemplate.value = ''
  scriptMode.value = false
  submitError.value = ''
  showSubmit.value = true
}

function applyTemplate() {
  const tpl = templates.value.find(t => t.name === selectedTemplate.value)
  if (!tpl) return
  const p = tpl.params
  submitForm.value.name = p.name ?? ''
  submitForm.value.partition = p.partition ?? 'gpu'
  submitForm.value.nodes = p.nodes ?? 1
  submitForm.value.ntasks_per_node = p.ntasks_per_node ?? 1
  submitForm.value.gpus_per_node = p.gpus_per_node ?? 1
  submitForm.value.container_image = p.container_image ?? ''
  submitForm.value.command = p.command ?? ''
  submitForm.value.working_dir = p.working_dir ?? '/data'
}

async function submitJob() {
  submitting.value = true
  submitError.value = ''
  try {
    const body = scriptMode.value
      ? { script: submitForm.value.script }
      : {
          name: submitForm.value.name,
          partition: submitForm.value.partition,
          nodes: submitForm.value.nodes,
          ntasks_per_node: submitForm.value.ntasks_per_node,
          gpus_per_node: submitForm.value.gpus_per_node,
          container_image: submitForm.value.container_image || null,
          command: submitForm.value.command,
          working_dir: submitForm.value.working_dir,
        }
    await post('/slurm/jobs', body)
    showSubmit.value = false
    await fetchJobs()
  } catch (e) {
    submitError.value = e.message || 'Submit failed'
  }
  submitting.value = false
}

function viewOutput(job) {
  logJobId.value = job.id
  logTitle.value = `Job ${job.id} — ${job.name}`
  logVisible.value = true
}

async function cancelJob(job) {
  if (cancelConfirm.value !== job.id) {
    cancelConfirm.value = job.id
    setTimeout(() => { cancelConfirm.value = '' }, 3000)
    return
  }
  try {
    await del(`/slurm/jobs/${job.id}`)
    cancelConfirm.value = ''
    await fetchJobs()
  } catch (e) {
    error.value = e.message || 'Cancel failed'
  }
}

function canCancel(state) {
  return state === 'RUNNING' || state === 'PENDING'
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold text-gray-100">Slurm Jobs</h2>
      <button
        @click="openSubmit"
        class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 transition-colors"
      >
        Submit Job
      </button>
    </div>

    <div v-if="error" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
      {{ error }}
    </div>

    <div v-if="loading" class="flex items-center gap-2 text-gray-400">
      <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Loading jobs...
    </div>

    <div v-else-if="!jobs.length" class="text-center py-16 text-gray-500">
      <div class="text-4xl mb-3">▶</div>
      <p>No jobs found</p>
      <p class="text-sm mt-1 text-gray-600">Submit a job to get started</p>
    </div>

    <div v-else class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-gray-400 border-b border-gray-700 bg-gray-800/80">
              <th class="py-3 px-4 font-medium">ID</th>
              <th class="py-3 px-4 font-medium">Name</th>
              <th class="py-3 px-4 font-medium">User</th>
              <th class="py-3 px-4 font-medium">State</th>
              <th class="py-3 px-4 font-medium">Nodes</th>
              <th class="py-3 px-4 font-medium">Partition</th>
              <th class="py-3 px-4 font-medium">Time</th>
              <th class="py-3 px-4 font-medium">GPUs</th>
              <th class="py-3 px-4 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="j in jobs" :key="j.id"
              class="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors"
            >
              <td class="py-3 px-4 font-mono text-gray-300">{{ j.id }}</td>
              <td class="py-3 px-4 font-medium text-gray-100">{{ j.name }}</td>
              <td class="py-3 px-4 text-gray-400">{{ j.user }}</td>
              <td class="py-3 px-4">
                <span
                  class="px-2 py-0.5 text-xs rounded-full border"
                  :class="stateColor(j.state)"
                >
                  {{ j.state }}
                </span>
              </td>
              <td class="py-3 px-4 text-gray-300">{{ j.nodes || '—' }}</td>
              <td class="py-3 px-4 text-gray-400">{{ j.partition }}</td>
              <td class="py-3 px-4 text-gray-400 font-mono text-xs">{{ j.time || '—' }}</td>
              <td class="py-3 px-4 text-gray-400">{{ j.gpus || '—' }}</td>
              <td class="py-3 px-4 text-right">
                <div class="flex items-center justify-end gap-1.5">
                  <button
                    @click="viewOutput(j)"
                    class="px-2.5 py-1 text-xs rounded-md bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white transition-colors"
                  >
                    Output
                  </button>
                  <button
                    v-if="canCancel(j.state)"
                    @click="cancelJob(j)"
                    class="px-2.5 py-1 text-xs rounded-md transition-colors"
                    :class="cancelConfirm === j.id
                      ? 'bg-red-500 text-white'
                      : 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20'"
                  >
                    {{ cancelConfirm === j.id ? 'Confirm?' : 'Cancel' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Submit Job Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showSubmit" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showSubmit = false">
          <div class="w-full max-w-3xl max-h-[90vh] bg-gray-900 rounded-xl border border-gray-700 shadow-2xl flex flex-col overflow-hidden">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700 shrink-0">
              <h3 class="text-lg font-semibold text-gray-100">Submit Job</h3>
              <button @click="showSubmit = false" class="text-gray-400 hover:text-white transition-colors">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div class="flex-1 overflow-y-auto p-5 space-y-4">
              <div v-if="submitError" class="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
                {{ submitError }}
              </div>

              <!-- Template selector -->
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Template</label>
                <select
                  v-model="selectedTemplate"
                  @change="applyTemplate"
                  class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50"
                >
                  <option value="">— Select a template —</option>
                  <option v-for="t in templates" :key="t.name" :value="t.name">
                    {{ t.name }} — {{ t.description }}
                  </option>
                </select>
              </div>

              <!-- Mode toggle -->
              <div class="flex items-center gap-3">
                <button
                  @click="scriptMode = false"
                  class="px-3 py-1.5 text-xs rounded-md border transition-colors"
                  :class="!scriptMode
                    ? 'bg-nvidia/10 text-nvidia border-nvidia/30'
                    : 'bg-gray-800 text-gray-400 border-gray-600 hover:bg-gray-700'"
                >
                  Form Mode
                </button>
                <button
                  @click="scriptMode = true"
                  class="px-3 py-1.5 text-xs rounded-md border transition-colors"
                  :class="scriptMode
                    ? 'bg-nvidia/10 text-nvidia border-nvidia/30'
                    : 'bg-gray-800 text-gray-400 border-gray-600 hover:bg-gray-700'"
                >
                  Script Mode
                </button>
              </div>

              <!-- Script mode -->
              <div v-if="scriptMode">
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Sbatch Script</label>
                <textarea
                  v-model="submitForm.script"
                  rows="16"
                  class="w-full px-3 py-2 rounded-lg bg-gray-950 border border-gray-600 text-gray-100 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500 resize-y"
                  placeholder="#!/bin/bash
#SBATCH --job-name=my-job
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --gpus-per-node=1

nvidia-smi"
                />
              </div>

              <!-- Form mode -->
              <template v-else>
                <div class="grid grid-cols-2 gap-4">
                  <div>
                    <label class="block text-sm font-medium text-gray-300 mb-1.5">Job Name</label>
                    <input
                      v-model="submitForm.name"
                      class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                      placeholder="my-job"
                    />
                  </div>
                  <div>
                    <label class="block text-sm font-medium text-gray-300 mb-1.5">Partition</label>
                    <input
                      v-model="submitForm.partition"
                      class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                      placeholder="gpu"
                    />
                  </div>
                  <div>
                    <label class="block text-sm font-medium text-gray-300 mb-1.5">Nodes</label>
                    <input
                      v-model.number="submitForm.nodes"
                      type="number" min="1" max="2"
                      class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50"
                    />
                  </div>
                  <div>
                    <label class="block text-sm font-medium text-gray-300 mb-1.5">Tasks per Node</label>
                    <input
                      v-model.number="submitForm.ntasks_per_node"
                      type="number" min="1"
                      class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50"
                    />
                  </div>
                  <div>
                    <label class="block text-sm font-medium text-gray-300 mb-1.5">GPUs per Node</label>
                    <input
                      v-model.number="submitForm.gpus_per_node"
                      type="number" min="0" max="4"
                      class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50"
                    />
                  </div>
                  <div>
                    <label class="block text-sm font-medium text-gray-300 mb-1.5">Working Directory</label>
                    <input
                      v-model="submitForm.working_dir"
                      class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                      placeholder="/data"
                    />
                  </div>
                </div>

                <div>
                  <label class="block text-sm font-medium text-gray-300 mb-1.5">Container Image <span class="text-gray-500 font-normal">(optional)</span></label>
                  <input
                    v-model="submitForm.container_image"
                    class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                    placeholder="nvcr.io/nvidia/pytorch:24.05-py3"
                  />
                </div>

                <div>
                  <label class="block text-sm font-medium text-gray-300 mb-1.5">Command</label>
                  <textarea
                    v-model="submitForm.command"
                    rows="3"
                    class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500 resize-y"
                    placeholder="nvidia-smi"
                  />
                </div>
              </template>
            </div>

            <div class="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-700 shrink-0">
              <button
                @click="showSubmit = false"
                class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button
                @click="submitJob"
                :disabled="submitting"
                class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                <svg v-if="submitting" class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {{ submitting ? 'Submitting...' : 'Submit Job' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Log Viewer -->
    <LogViewer
      :wsUrl="`/api/slurm/ws/jobs/${logJobId}/output`"
      :title="logTitle"
      :visible="logVisible"
      @close="logVisible = false"
    />
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
