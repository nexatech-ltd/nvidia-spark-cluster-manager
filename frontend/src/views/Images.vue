<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi'

const { get, post, del } = useApi()

const images = ref([])
const loading = ref(true)
const error = ref('')

const showPull = ref(false)
const pullImage = ref('')
const pullTag = ref('latest')
const pullRegistry = ref('')
const pulling = ref(false)

const showBuild = ref(false)
const buildTag = ref('')
const buildDockerfile = ref('FROM ubuntu:latest\n\nRUN apt-get update && apt-get install -y curl\n')
const buildContextPath = ref('.')
const building = ref(false)

const progressLog = ref([])
const showProgress = ref(false)

const removeConfirm = ref('')
const pruning = ref(false)

async function fetchImages() {
  loading.value = true
  error.value = ''
  try {
    images.value = await get('/images/')
  } catch (e) {
    error.value = e.message || 'Failed to load images'
  }
  loading.value = false
}

onMounted(fetchImages)

function formatSize(bytes) {
  if (!bytes) return '—'
  const mb = bytes / 1024 / 1024
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(0)} MB`
}

function formatDate(dateStr) {
  if (!dateStr) return '—'
  try {
    return new Date(dateStr).toLocaleString()
  } catch {
    return dateStr
  }
}

function formatTags(tags) {
  if (!tags || !tags.length) return ['<none>']
  return tags
}

async function doPull() {
  if (!pullImage.value.trim()) return
  pulling.value = true
  progressLog.value = []
  showProgress.value = true
  error.value = ''
  try {
    const body = {
      image: pullImage.value.trim(),
      tag: pullTag.value.trim() || 'latest',
    }
    if (pullRegistry.value.trim()) body.registry = pullRegistry.value.trim()
    const res = await fetch('/api/images/pull', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop()
      for (const line of lines) {
        if (line.trim()) {
          try {
            const event = JSON.parse(line)
            const msg = event.status
              ? `${event.status}${event.progress ? ' ' + event.progress : ''}${event.id ? ' [' + event.id + ']' : ''}`
              : event.error || JSON.stringify(event)
            progressLog.value.push(msg)
          } catch {
            progressLog.value.push(line)
          }
        }
      }
    }
    showPull.value = false
    await fetchImages()
  } catch (e) {
    progressLog.value.push(`Error: ${e.message}`)
  }
  pulling.value = false
}

async function doBuild() {
  if (!buildTag.value.trim()) return
  building.value = true
  progressLog.value = []
  showProgress.value = true
  error.value = ''
  try {
    const res = await fetch('/api/images/build', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dockerfile: buildDockerfile.value,
        tag: buildTag.value.trim(),
        context_path: buildContextPath.value.trim() || '.',
      }),
    })
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop()
      for (const line of lines) {
        if (line.trim()) {
          try {
            const event = JSON.parse(line)
            const msg = event.stream?.trimEnd() || event.error || JSON.stringify(event)
            if (msg) progressLog.value.push(msg)
          } catch {
            progressLog.value.push(line)
          }
        }
      }
    }
    showBuild.value = false
    await fetchImages()
  } catch (e) {
    progressLog.value.push(`Error: ${e.message}`)
  }
  building.value = false
}

async function removeImage(imageId) {
  if (removeConfirm.value !== imageId) {
    removeConfirm.value = imageId
    setTimeout(() => { removeConfirm.value = '' }, 3000)
    return
  }
  removeConfirm.value = ''
  try {
    await del(`/images/${encodeURIComponent(imageId)}`)
    await fetchImages()
  } catch (e) {
    error.value = e.message || 'Remove failed'
  }
}

async function pruneAll() {
  pruning.value = true
  try {
    const result = await post('/images/prune')
    const count = result.images_deleted?.length || 0
    const space = formatSize(result.space_reclaimed || 0)
    progressLog.value = [`Pruned ${count} image(s), reclaimed ${space}`]
    showProgress.value = true
    await fetchImages()
  } catch (e) {
    error.value = e.message || 'Prune failed'
  }
  pruning.value = false
}
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold text-gray-100">Images</h2>
      <div class="flex items-center gap-2">
        <button
          @click="showPull = true; pullImage = ''; pullTag = 'latest'; pullRegistry = ''"
          class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 transition-colors"
        >
          Pull Image
        </button>
        <button
          @click="showBuild = true; buildTag = ''; buildDockerfile = 'FROM ubuntu:latest\n\nRUN apt-get update\n'; buildContextPath = '.'"
          class="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-500 transition-colors"
        >
          Build
        </button>
        <button
          @click="pruneAll"
          :disabled="pruning"
          class="px-4 py-2 text-sm rounded-lg bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors disabled:opacity-50"
        >
          {{ pruning ? 'Pruning...' : 'Prune All' }}
        </button>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm flex items-center justify-between">
      <span>{{ error }}</span>
      <button @click="error = ''" class="text-red-300 hover:text-white ml-3 shrink-0">&times;</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-2 text-gray-400">
      <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Loading images...
    </div>

    <!-- Empty -->
    <div v-else-if="!images.length" class="text-center py-16 text-gray-500">
      <div class="text-4xl mb-3">◉</div>
      <p>No images found</p>
      <p class="text-sm mt-1 text-gray-600">Pull or build your first image</p>
    </div>

    <!-- Images table -->
    <div v-else class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-gray-400 border-b border-gray-700 bg-gray-800/80">
            <th class="py-3 px-4 font-medium">Tags</th>
            <th class="py-3 px-4 font-medium">Size</th>
            <th class="py-3 px-4 font-medium">Created</th>
            <th class="py-3 px-4 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="img in images"
            :key="img.id"
            class="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors"
          >
            <td class="py-3 px-4">
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="tag in formatTags(img.tags)"
                  :key="tag"
                  class="px-2 py-0.5 text-xs rounded-full font-mono"
                  :class="tag === '<none>'
                    ? 'bg-gray-700 text-gray-500'
                    : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'"
                >
                  {{ tag }}
                </span>
              </div>
            </td>
            <td class="py-3 px-4 text-gray-300 font-mono text-xs">{{ formatSize(img.size) }}</td>
            <td class="py-3 px-4 text-gray-500 text-xs whitespace-nowrap">{{ formatDate(img.created) }}</td>
            <td class="py-3 px-4 text-right">
              <button
                @click="removeImage(img.id)"
                class="px-2.5 py-1 text-xs rounded-md transition-colors"
                :class="removeConfirm === img.id
                  ? 'bg-red-500 text-white'
                  : 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20'"
              >
                {{ removeConfirm === img.id ? 'Confirm?' : 'Remove' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Progress Log (collapsible) -->
    <div v-if="showProgress && progressLog.length" class="mt-4">
      <div
        class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden"
      >
        <button
          @click="showProgress = false"
          class="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-300 hover:bg-gray-700/50 transition-colors"
        >
          <span>Output Log ({{ progressLog.length }} lines)</span>
          <svg class="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
        <div class="max-h-64 overflow-y-auto bg-gray-950 p-4 border-t border-gray-700">
          <pre class="font-mono text-xs text-gray-400 whitespace-pre-wrap break-all">{{ progressLog.join('\n') }}</pre>
        </div>
      </div>
    </div>

    <!-- Pull Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showPull" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showPull = false">
          <div class="w-full max-w-md bg-gray-900 rounded-xl border border-gray-700 shadow-2xl">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700">
              <h3 class="text-lg font-semibold text-gray-100">Pull Image</h3>
              <button @click="showPull = false" class="text-gray-400 hover:text-white transition-colors">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div class="p-5 space-y-4">
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Image Name</label>
                <input
                  v-model="pullImage"
                  class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                  placeholder="nginx"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Tag</label>
                <input
                  v-model="pullTag"
                  class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                  placeholder="latest"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">
                  Registry
                  <span class="text-gray-500 font-normal">(optional)</span>
                </label>
                <input
                  v-model="pullRegistry"
                  class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                  placeholder="registry.example.com"
                />
              </div>
            </div>
            <div class="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-700">
              <button
                @click="showPull = false"
                class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button
                @click="doPull"
                :disabled="pulling || !pullImage.trim()"
                class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                <svg v-if="pulling" class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {{ pulling ? 'Pulling...' : 'Pull' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Build Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showBuild" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showBuild = false">
          <div class="w-full max-w-2xl max-h-[90vh] bg-gray-900 rounded-xl border border-gray-700 shadow-2xl flex flex-col overflow-hidden">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700 shrink-0">
              <h3 class="text-lg font-semibold text-gray-100">Build Image</h3>
              <button @click="showBuild = false" class="text-gray-400 hover:text-white transition-colors">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div class="flex-1 overflow-y-auto p-5 space-y-4">
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Image Tag</label>
                <input
                  v-model="buildTag"
                  class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                  placeholder="myapp:latest"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Context Path</label>
                <input
                  v-model="buildContextPath"
                  class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500 font-mono"
                  placeholder="."
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">Dockerfile Content</label>
                <div class="rounded-lg border border-gray-600 overflow-hidden">
                  <textarea
                    v-model="buildDockerfile"
                    class="w-full min-h-[200px] bg-gray-950 text-gray-200 font-mono text-sm leading-relaxed p-4 resize-y outline-none focus:ring-1 focus:ring-nvidia/40 placeholder-gray-600"
                    spellcheck="false"
                    placeholder="FROM ubuntu:latest"
                  />
                </div>
              </div>
            </div>
            <div class="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-700 shrink-0">
              <button
                @click="showBuild = false"
                class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button
                @click="doBuild"
                :disabled="building || !buildTag.trim()"
                class="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                <svg v-if="building" class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {{ building ? 'Building...' : 'Build' }}
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
