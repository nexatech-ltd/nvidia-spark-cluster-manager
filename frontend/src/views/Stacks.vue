<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi'
import ComposeEditor from '../components/ComposeEditor.vue'

const { get, post, put, del } = useApi()

const stacks = ref([])
const loading = ref(true)
const error = ref('')

const showDeploy = ref(false)
const deployName = ref('')
const deployCompose = ref('')
const deployEnvPairs = ref([])
const deploying = ref(false)
const deployError = ref('')

const showCompose = ref(false)
const composeTitle = ref('')
const composeContent = ref('')
const composeLoading = ref(false)
const copied = ref(false)

const showUpdate = ref(false)
const updateName = ref('')
const updateCompose = ref('')
const updateEnvPairs = ref([])
const updating = ref(false)
const updateError = ref('')

async function fetchStacks() {
  loading.value = true
  error.value = ''
  try {
    stacks.value = await get('/docker/stacks')
  } catch (e) {
    error.value = e.message || 'Failed to load stacks'
  }
  loading.value = false
}

onMounted(fetchStacks)

function openDeploy() {
  deployName.value = ''
  deployCompose.value = ''
  deployEnvPairs.value = [{ key: '', value: '' }]
  deployError.value = ''
  showDeploy.value = true
}

function addEnvPair(pairs) {
  pairs.push({ key: '', value: '' })
}

function removeEnvPair(pairs, idx) {
  pairs.splice(idx, 1)
}

function envPairsToObj(pairs) {
  const obj = {}
  for (const p of pairs) {
    if (p.key.trim()) obj[p.key.trim()] = p.value
  }
  return obj
}

async function deployStack() {
  if (!deployName.value.trim() || !deployCompose.value.trim()) {
    deployError.value = 'Stack name and compose content are required'
    return
  }
  deploying.value = true
  deployError.value = ''
  try {
    await post('/docker/stacks', {
      name: deployName.value.trim(),
      compose_content: deployCompose.value,
      env_vars: envPairsToObj(deployEnvPairs.value),
    })
    showDeploy.value = false
    await fetchStacks()
  } catch (e) {
    deployError.value = e.message || 'Deploy failed'
  }
  deploying.value = false
}

async function viewCompose(name) {
  composeTitle.value = name
  composeLoading.value = true
  composeContent.value = ''
  showCompose.value = true
  try {
    const data = await get(`/docker/stacks/${name}/compose`)
    composeContent.value = data.compose_content
  } catch (e) {
    composeContent.value = `# Error loading compose: ${e.message}`
  }
  composeLoading.value = false
}

async function copyCompose() {
  try {
    await navigator.clipboard.writeText(composeContent.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = composeContent.value
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  }
}

function downloadCompose() {
  const blob = new Blob([composeContent.value], { type: 'application/x-yaml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${composeTitle.value}-docker-compose.yml`
  a.click()
  URL.revokeObjectURL(url)
}

async function openUpdate(name) {
  updateName.value = name
  updateError.value = ''
  updateCompose.value = ''
  updateEnvPairs.value = [{ key: '', value: '' }]
  showUpdate.value = true
  try {
    const data = await get(`/docker/stacks/${name}/compose`)
    updateCompose.value = data.compose_content
  } catch {
    updateCompose.value = ''
  }
}

async function updateStack() {
  if (!updateCompose.value.trim()) {
    updateError.value = 'Compose content is required'
    return
  }
  updating.value = true
  updateError.value = ''
  try {
    await put(`/docker/stacks/${updateName.value}`, {
      name: updateName.value,
      compose_content: updateCompose.value,
      env_vars: envPairsToObj(updateEnvPairs.value),
    })
    showUpdate.value = false
    await fetchStacks()
  } catch (e) {
    updateError.value = e.message || 'Update failed'
  }
  updating.value = false
}

const removeConfirm = ref('')
async function removeStack(name) {
  if (removeConfirm.value !== name) {
    removeConfirm.value = name
    setTimeout(() => { removeConfirm.value = '' }, 3000)
    return
  }
  try {
    await del(`/docker/stacks/${name}`)
    removeConfirm.value = ''
    await fetchStacks()
  } catch (e) {
    error.value = e.message || 'Remove failed'
  }
}
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold text-gray-100">Stacks</h2>
      <button
        @click="openDeploy"
        class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 transition-colors"
      >
        Deploy Stack
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
      Loading stacks...
    </div>

    <!-- Empty -->
    <div v-else-if="!stacks.length" class="text-center py-16 text-gray-500">
      <div class="text-4xl mb-3">☰</div>
      <p>No stacks deployed yet</p>
      <p class="text-sm mt-1 text-gray-600">Deploy your first stack to get started</p>
    </div>

    <!-- Stacks table -->
    <div v-else class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-gray-400 border-b border-gray-700 bg-gray-800/80">
            <th class="py-3 px-4 font-medium">Name</th>
            <th class="py-3 px-4 font-medium">Services</th>
            <th class="py-3 px-4 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in stacks"
            :key="s.name"
            class="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors"
          >
            <td class="py-3 px-4 font-medium text-gray-100">{{ s.name }}</td>
            <td class="py-3 px-4">
              <span class="px-2 py-0.5 text-xs rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                {{ s.services }} service{{ s.services !== 1 ? 's' : '' }}
              </span>
            </td>
            <td class="py-3 px-4 text-right">
              <div class="flex items-center justify-end gap-1.5">
                <button
                  @click="viewCompose(s.name)"
                  class="px-2.5 py-1 text-xs rounded-md bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white transition-colors"
                >
                  Compose
                </button>
                <button
                  @click="openUpdate(s.name)"
                  class="px-2.5 py-1 text-xs rounded-md bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
                >
                  Update
                </button>
                <button
                  @click="removeStack(s.name)"
                  class="px-2.5 py-1 text-xs rounded-md transition-colors"
                  :class="removeConfirm === s.name
                    ? 'bg-red-500 text-white'
                    : 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20'"
                >
                  {{ removeConfirm === s.name ? 'Confirm?' : 'Remove' }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Deploy Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showDeploy" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showDeploy = false">
          <div class="w-full max-w-3xl max-h-[90vh] bg-gray-900 rounded-xl border border-gray-700 shadow-2xl flex flex-col overflow-hidden">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700 shrink-0">
              <h3 class="text-lg font-semibold text-gray-100">Deploy Stack</h3>
              <button @click="showDeploy = false" class="text-gray-400 hover:text-white transition-colors">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div class="flex-1 overflow-y-auto p-5 space-y-4">
              <div v-if="deployError" class="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
                {{ deployError }}
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Stack Name</label>
                <input
                  v-model="deployName"
                  class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 focus:border-nvidia/50 placeholder-gray-500"
                  placeholder="my-stack"
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Compose File</label>
                <ComposeEditor v-model="deployCompose" />
              </div>

              <div>
                <div class="flex items-center justify-between mb-1.5">
                  <label class="block text-sm font-medium text-gray-300">Environment Variables</label>
                  <button
                    @click="addEnvPair(deployEnvPairs)"
                    class="text-xs text-nvidia hover:text-nvidia/80 transition-colors"
                  >
                    + Add Variable
                  </button>
                </div>
                <div class="space-y-2">
                  <div v-for="(pair, idx) in deployEnvPairs" :key="idx" class="flex gap-2">
                    <input
                      v-model="pair.key"
                      placeholder="KEY"
                      class="flex-1 px-3 py-1.5 rounded-md bg-gray-800 border border-gray-600 text-gray-100 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                    />
                    <input
                      v-model="pair.value"
                      placeholder="value"
                      class="flex-1 px-3 py-1.5 rounded-md bg-gray-800 border border-gray-600 text-gray-100 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                    />
                    <button
                      @click="removeEnvPair(deployEnvPairs, idx)"
                      class="px-2 text-gray-500 hover:text-red-400 transition-colors"
                    >
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div class="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-700 shrink-0">
              <button
                @click="showDeploy = false"
                class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button
                @click="deployStack"
                :disabled="deploying"
                class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                <svg v-if="deploying" class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {{ deploying ? 'Deploying...' : 'Deploy' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- View Compose Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showCompose" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showCompose = false">
          <div class="w-full max-w-3xl max-h-[80vh] bg-gray-900 rounded-xl border border-gray-700 shadow-2xl flex flex-col overflow-hidden">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700 shrink-0">
              <h3 class="text-lg font-semibold text-gray-100">{{ composeTitle }} — docker-compose.yml</h3>
              <div class="flex items-center gap-1.5">
                <button
                  @click="copyCompose"
                  :disabled="composeLoading || !composeContent"
                  class="p-1.5 rounded-md text-gray-400 hover:text-white hover:bg-gray-700 disabled:opacity-30 transition-colors"
                  :title="copied ? 'Copied!' : 'Copy to clipboard'"
                >
                  <svg v-if="!copied" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <rect x="9" y="9" width="13" height="13" rx="2" stroke-width="2" />
                    <path stroke-width="2" d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                  </svg>
                  <svg v-else class="w-4 h-4 text-nvidia" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                </button>
                <button
                  @click="downloadCompose"
                  :disabled="composeLoading || !composeContent"
                  class="p-1.5 rounded-md text-gray-400 hover:text-white hover:bg-gray-700 disabled:opacity-30 transition-colors"
                  title="Download file"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3" />
                  </svg>
                </button>
                <button @click="showCompose = false" class="p-1.5 rounded-md text-gray-400 hover:text-white hover:bg-gray-700 transition-colors">
                  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
            <div class="flex-1 overflow-y-auto p-5">
              <div v-if="composeLoading" class="flex items-center gap-2 text-gray-400 text-sm">
                <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Loading...
              </div>
              <ComposeEditor v-else :modelValue="composeContent" :readonly="true" />
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Update Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showUpdate" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showUpdate = false">
          <div class="w-full max-w-3xl max-h-[90vh] bg-gray-900 rounded-xl border border-gray-700 shadow-2xl flex flex-col overflow-hidden">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700 shrink-0">
              <h3 class="text-lg font-semibold text-gray-100">Update Stack: {{ updateName }}</h3>
              <button @click="showUpdate = false" class="text-gray-400 hover:text-white transition-colors">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div class="flex-1 overflow-y-auto p-5 space-y-4">
              <div v-if="updateError" class="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
                {{ updateError }}
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Compose File</label>
                <ComposeEditor v-model="updateCompose" />
              </div>

              <div>
                <div class="flex items-center justify-between mb-1.5">
                  <label class="block text-sm font-medium text-gray-300">Environment Variables</label>
                  <button
                    @click="addEnvPair(updateEnvPairs)"
                    class="text-xs text-nvidia hover:text-nvidia/80 transition-colors"
                  >
                    + Add Variable
                  </button>
                </div>
                <div class="space-y-2">
                  <div v-for="(pair, idx) in updateEnvPairs" :key="idx" class="flex gap-2">
                    <input
                      v-model="pair.key"
                      placeholder="KEY"
                      class="flex-1 px-3 py-1.5 rounded-md bg-gray-800 border border-gray-600 text-gray-100 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                    />
                    <input
                      v-model="pair.value"
                      placeholder="value"
                      class="flex-1 px-3 py-1.5 rounded-md bg-gray-800 border border-gray-600 text-gray-100 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                    />
                    <button
                      @click="removeEnvPair(updateEnvPairs, idx)"
                      class="px-2 text-gray-500 hover:text-red-400 transition-colors"
                    >
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div class="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-700 shrink-0">
              <button
                @click="showUpdate = false"
                class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button
                @click="updateStack"
                :disabled="updating"
                class="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                <svg v-if="updating" class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {{ updating ? 'Updating...' : 'Update Stack' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
