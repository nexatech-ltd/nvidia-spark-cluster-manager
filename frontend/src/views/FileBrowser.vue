<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useApi } from '../composables/useApi'

const { get, post, put, del, request } = useApi()

const selectedNode = ref('spark-1')
const currentPath = ref('/data')
const entries = ref([])
const loading = ref(true)
const error = ref('')
const viewMode = ref('list')

const sortKey = ref('name')
const sortAsc = ref(true)

const dragging = ref(false)
const uploading = ref(false)
const uploadProgress = ref([])

const showChmod = ref(false)
const chmodTarget = ref(null)
const chmodBits = ref(Array(9).fill(false))
const chmodSubmitting = ref(false)

const showRename = ref(false)
const renameTarget = ref(null)
const renameName = ref('')
const renameSubmitting = ref(false)

const showDelete = ref(false)
const deleteTarget = ref(null)
const deleteSubmitting = ref(false)

const showMkdir = ref(false)
const mkdirName = ref('')
const mkdirSubmitting = ref(false)

const fileInputRef = ref(null)

async function loadDir(path) {
  loading.value = true
  error.value = ''
  try {
    entries.value = await get(`/files/${selectedNode.value}/list?path=${encodeURIComponent(path)}`)
    currentPath.value = path
  } catch (e) {
    error.value = e.message || 'Failed to load directory'
    entries.value = []
  }
  loading.value = false
}

onMounted(() => loadDir('/data'))

watch(selectedNode, () => {
  currentPath.value = '/data'
  loadDir('/data')
})

const breadcrumbs = computed(() => {
  if (currentPath.value === '/') return [{ name: '/', path: '/' }]
  const parts = currentPath.value.split('/').filter(Boolean)
  const crumbs = [{ name: '/', path: '/' }]
  let acc = ''
  for (const p of parts) {
    acc += `/${p}`
    crumbs.push({ name: p, path: acc })
  }
  return crumbs
})

const sortedEntries = computed(() => {
  const dirs = entries.value.filter(e => e.type === 'dir')
  const files = entries.value.filter(e => e.type !== 'dir')

  function cmp(a, b) {
    let va, vb
    if (sortKey.value === 'name') { va = a.name.toLowerCase(); vb = b.name.toLowerCase() }
    else if (sortKey.value === 'size') { va = a.size; vb = b.size }
    else if (sortKey.value === 'modified') { va = a.modified; vb = b.modified }
    else { va = a.name.toLowerCase(); vb = b.name.toLowerCase() }

    if (va < vb) return sortAsc.value ? -1 : 1
    if (va > vb) return sortAsc.value ? 1 : -1
    return 0
  }

  return [...dirs.sort(cmp), ...files.sort(cmp)]
})

function toggleSort(key) {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value
  } else {
    sortKey.value = key
    sortAsc.value = true
  }
}

function sortIcon(key) {
  if (sortKey.value !== key) return ''
  return sortAsc.value ? '↑' : '↓'
}

function navigate(entry) {
  if (entry.type === 'dir') {
    loadDir(entry.path)
  }
}

function goToBreadcrumb(crumb) {
  loadDir(crumb.path)
}

function formatSize(bytes) {
  if (bytes == null || bytes < 0) return '—'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let val = bytes
  while (val >= 1024 && i < units.length - 1) { val /= 1024; i++ }
  return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function formatDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) + ' ' +
    d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

function downloadFile(entry) {
  const url = `/api/files/${selectedNode.value}/download?path=${encodeURIComponent(entry.path)}`
  const a = document.createElement('a')
  a.href = url
  a.download = entry.name
  a.click()
}

// Chmod
function parsePerm(permStr) {
  const bits = Array(9).fill(false)
  if (!permStr || permStr.length < 9) return bits
  const s = permStr.slice(-9)
  const chars = 'rwxrwxrwx'
  for (let i = 0; i < 9; i++) {
    bits[i] = s[i] === chars[i]
  }
  return bits
}

function bitsToOctal(bits) {
  let oct = ''
  for (let g = 0; g < 3; g++) {
    let val = 0
    if (bits[g * 3]) val += 4
    if (bits[g * 3 + 1]) val += 2
    if (bits[g * 3 + 2]) val += 1
    oct += val.toString()
  }
  return oct
}

function bitsToString(bits) {
  const chars = 'rwxrwxrwx'
  return bits.map((b, i) => b ? chars[i] : '-').join('')
}

function openChmod(entry) {
  chmodTarget.value = entry
  chmodBits.value = parsePerm(entry.permissions)
  showChmod.value = true
}

async function applyChmod() {
  if (!chmodTarget.value) return
  chmodSubmitting.value = true
  try {
    await put(`/files/${selectedNode.value}/chmod`, {
      path: chmodTarget.value.path,
      mode: bitsToOctal(chmodBits.value),
    })
    showChmod.value = false
    await loadDir(currentPath.value)
  } catch (e) {
    error.value = e.message || 'Chmod failed'
  }
  chmodSubmitting.value = false
}

// Rename
function openRename(entry) {
  renameTarget.value = entry
  renameName.value = entry.name
  showRename.value = true
}

async function applyRename() {
  if (!renameTarget.value || !renameName.value.trim()) return
  renameSubmitting.value = true
  try {
    const dir = renameTarget.value.path.substring(0, renameTarget.value.path.lastIndexOf('/')) || '/'
    const newPath = dir === '/' ? `/${renameName.value.trim()}` : `${dir}/${renameName.value.trim()}`
    await put(`/files/${selectedNode.value}/rename`, {
      old_path: renameTarget.value.path,
      new_path: newPath,
    })
    showRename.value = false
    await loadDir(currentPath.value)
  } catch (e) {
    error.value = e.message || 'Rename failed'
  }
  renameSubmitting.value = false
}

// Delete
function openDelete(entry) {
  deleteTarget.value = entry
  showDelete.value = true
}

async function applyDelete() {
  if (!deleteTarget.value) return
  deleteSubmitting.value = true
  try {
    const isDir = deleteTarget.value.type === 'dir'
    await del(`/files/${selectedNode.value}/delete?path=${encodeURIComponent(deleteTarget.value.path)}&recursive=${isDir}`)
    showDelete.value = false
    await loadDir(currentPath.value)
  } catch (e) {
    error.value = e.message || 'Delete failed'
  }
  deleteSubmitting.value = false
}

// Mkdir
function openMkdir() {
  mkdirName.value = ''
  showMkdir.value = true
}

async function applyMkdir() {
  if (!mkdirName.value.trim()) return
  mkdirSubmitting.value = true
  try {
    const newPath = currentPath.value === '/' ? `/${mkdirName.value.trim()}` : `${currentPath.value}/${mkdirName.value.trim()}`
    await post(`/files/${selectedNode.value}/mkdir`, { path: newPath })
    showMkdir.value = false
    await loadDir(currentPath.value)
  } catch (e) {
    error.value = e.message || 'Mkdir failed'
  }
  mkdirSubmitting.value = false
}

// Upload
function triggerUpload() {
  fileInputRef.value?.click()
}

async function handleFileUpload(event) {
  const files = event.target.files
  if (!files?.length) return
  await uploadFiles(files)
  event.target.value = ''
}

function onDragOver(e) {
  e.preventDefault()
  dragging.value = true
}

function onDragLeave() {
  dragging.value = false
}

function onDrop(e) {
  e.preventDefault()
  dragging.value = false
  const files = e.dataTransfer?.files
  if (files?.length) uploadFiles(files)
}

async function uploadFiles(files) {
  uploading.value = true
  uploadProgress.value = Array.from(files).map(f => ({ name: f.name, percent: 0, done: false }))

  const formData = new FormData()
  for (const f of files) formData.append('files', f)

  try {
    await request(`/files/${selectedNode.value}/upload?path=${encodeURIComponent(currentPath.value)}`, {
      method: 'POST',
      body: formData,
    })
    uploadProgress.value.forEach(p => { p.percent = 100; p.done = true })
    setTimeout(async () => {
      uploading.value = false
      uploadProgress.value = []
      await loadDir(currentPath.value)
    }, 800)
  } catch (e) {
    error.value = e.message || 'Upload failed'
    uploading.value = false
    uploadProgress.value = []
  }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-2xl font-bold text-gray-100">File Browser</h2>
      <div class="flex items-center gap-1 bg-gray-800 rounded-lg p-1 border border-gray-700">
        <button
          v-for="node in ['spark-1', 'spark-2']" :key="node"
          @click="selectedNode = node"
          class="px-3 py-1.5 text-sm rounded-md transition-colors"
          :class="selectedNode === node ? 'bg-gray-700 text-white font-medium' : 'text-gray-400 hover:text-gray-200'"
        >
          {{ node }}
        </button>
      </div>
    </div>

    <!-- Breadcrumbs -->
    <div class="flex items-center gap-1 mb-4 text-sm overflow-x-auto">
      <template v-for="(crumb, idx) in breadcrumbs" :key="crumb.path">
        <span v-if="idx > 0" class="text-gray-600">/</span>
        <button
          @click="goToBreadcrumb(crumb)"
          class="px-1.5 py-0.5 rounded hover:bg-gray-700 transition-colors whitespace-nowrap"
          :class="idx === breadcrumbs.length - 1 ? 'text-gray-100 font-medium' : 'text-gray-400 hover:text-gray-200'"
        >
          {{ crumb.name }}
        </button>
      </template>
    </div>

    <!-- Toolbar -->
    <div class="flex items-center gap-2 mb-4">
      <button
        @click="openMkdir"
        class="px-3 py-1.5 text-sm rounded-lg bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
      >
        New Folder
      </button>
      <button
        @click="triggerUpload"
        class="px-3 py-1.5 text-sm rounded-lg bg-nvidia text-black font-medium hover:bg-nvidia/90 transition-colors"
      >
        Upload
      </button>
      <input ref="fileInputRef" type="file" multiple class="hidden" @change="handleFileUpload" />

      <div class="ml-auto flex items-center gap-1 bg-gray-800 rounded-lg p-0.5 border border-gray-700">
        <button
          @click="viewMode = 'list'"
          class="p-1.5 rounded transition-colors"
          :class="viewMode === 'list' ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-300'"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" /></svg>
        </button>
        <button
          @click="viewMode = 'grid'"
          class="p-1.5 rounded transition-colors"
          :class="viewMode === 'grid' ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-300'"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zM14 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" /></svg>
        </button>
      </div>
    </div>

    <!-- Upload Progress -->
    <div v-if="uploading" class="mb-4 space-y-2">
      <div
        v-for="up in uploadProgress" :key="up.name"
        class="bg-gray-800 rounded-lg border border-gray-700 p-3"
      >
        <div class="flex items-center justify-between mb-1">
          <span class="text-sm text-gray-200 truncate">{{ up.name }}</span>
          <span class="text-xs text-gray-400">{{ up.done ? 'Done' : 'Uploading...' }}</span>
        </div>
        <div class="h-1.5 bg-gray-700 rounded-full overflow-hidden">
          <div
            class="h-full bg-nvidia rounded-full transition-all duration-300"
            :class="up.done ? '' : 'animate-pulse'"
            :style="{ width: `${up.done ? 100 : 60}%` }"
          />
        </div>
      </div>
    </div>

    <div v-if="error" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
      {{ error }}
      <button @click="error = ''" class="ml-2 text-red-300 hover:text-white">dismiss</button>
    </div>

    <div v-if="loading" class="flex items-center gap-2 text-gray-400">
      <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Loading...
    </div>

    <!-- File List / Drop Zone -->
    <div
      v-else
      class="relative"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <!-- Drop overlay -->
      <div
        v-if="dragging"
        class="absolute inset-0 z-10 bg-nvidia/10 border-2 border-dashed border-nvidia rounded-xl flex items-center justify-center"
      >
        <div class="text-center">
          <div class="text-3xl mb-2 text-nvidia">↑</div>
          <p class="text-nvidia font-medium">Drop files to upload</p>
          <p class="text-sm text-gray-400 mt-1">to {{ currentPath }}</p>
        </div>
      </div>

      <div v-if="!sortedEntries.length" class="text-center py-16 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
        <div class="text-4xl mb-3">📂</div>
        <p>Empty directory</p>
        <p class="text-sm mt-1 text-gray-600">Upload files or create a folder</p>
      </div>

      <!-- List view -->
      <div v-else-if="viewMode === 'list'" class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-gray-400 border-b border-gray-700 bg-gray-800/80">
                <th class="py-3 px-4 w-10"></th>
                <th class="py-3 px-4 font-medium cursor-pointer hover:text-gray-200 select-none" @click="toggleSort('name')">
                  Name {{ sortIcon('name') }}
                </th>
                <th class="py-3 px-4 font-medium cursor-pointer hover:text-gray-200 select-none" @click="toggleSort('size')">
                  Size {{ sortIcon('size') }}
                </th>
                <th class="py-3 px-4 font-medium">Permissions</th>
                <th class="py-3 px-4 font-medium">Owner</th>
                <th class="py-3 px-4 font-medium cursor-pointer hover:text-gray-200 select-none" @click="toggleSort('modified')">
                  Modified {{ sortIcon('modified') }}
                </th>
                <th class="py-3 px-4 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="entry in sortedEntries" :key="entry.path"
                class="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors group"
                :class="entry.type === 'dir' ? 'cursor-pointer' : ''"
                @click="navigate(entry)"
              >
                <td class="py-2.5 px-4 text-center">
                  <span v-if="entry.type === 'dir'" class="text-yellow-400">📁</span>
                  <span v-else class="text-gray-400">📄</span>
                </td>
                <td class="py-2.5 px-4">
                  <span :class="entry.type === 'dir' ? 'text-blue-400 font-medium' : 'text-gray-100'">
                    {{ entry.name }}
                  </span>
                </td>
                <td class="py-2.5 px-4 text-gray-400 text-xs whitespace-nowrap">
                  {{ entry.type === 'dir' ? '—' : formatSize(entry.size) }}
                </td>
                <td class="py-2.5 px-4 font-mono text-xs text-gray-500">{{ entry.permissions }}</td>
                <td class="py-2.5 px-4 text-gray-400 text-xs">{{ entry.owner }}</td>
                <td class="py-2.5 px-4 text-gray-400 text-xs whitespace-nowrap">{{ formatDate(entry.modified) }}</td>
                <td class="py-2.5 px-4 text-right" @click.stop>
                  <div class="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      v-if="entry.type !== 'dir'"
                      @click="downloadFile(entry)"
                      class="px-2 py-1 text-xs rounded bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white transition-colors"
                      title="Download"
                    >
                      ↓
                    </button>
                    <button
                      @click="openRename(entry)"
                      class="px-2 py-1 text-xs rounded bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white transition-colors"
                      title="Rename"
                    >
                      ✎
                    </button>
                    <button
                      @click="openChmod(entry)"
                      class="px-2 py-1 text-xs rounded bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white transition-colors"
                      title="Permissions"
                    >
                      🔑
                    </button>
                    <button
                      @click="openDelete(entry)"
                      class="px-2 py-1 text-xs rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
                      title="Delete"
                    >
                      ✕
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Grid view -->
      <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <div
          v-for="entry in sortedEntries" :key="entry.path"
          class="bg-gray-800 rounded-xl border border-gray-700 p-4 hover:bg-gray-700/50 transition-colors cursor-pointer group relative"
          @click="navigate(entry)"
        >
          <div class="text-center mb-2">
            <span class="text-3xl">{{ entry.type === 'dir' ? '📁' : '📄' }}</span>
          </div>
          <div class="text-sm text-center truncate" :class="entry.type === 'dir' ? 'text-blue-400' : 'text-gray-200'">
            {{ entry.name }}
          </div>
          <div v-if="entry.type !== 'dir'" class="text-xs text-gray-500 text-center mt-1">
            {{ formatSize(entry.size) }}
          </div>
          <div class="absolute top-2 right-2 flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity" @click.stop>
            <button
              v-if="entry.type !== 'dir'"
              @click="downloadFile(entry)"
              class="p-1 text-xs rounded bg-gray-700/80 text-gray-300 hover:bg-gray-600 transition-colors"
            >↓</button>
            <button
              @click="openDelete(entry)"
              class="p-1 text-xs rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
            >✕</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Chmod Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showChmod" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showChmod = false">
          <div class="w-full max-w-md bg-gray-900 rounded-xl border border-gray-700 shadow-2xl">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700">
              <h3 class="text-lg font-semibold text-gray-100">Change Permissions</h3>
              <button @click="showChmod = false" class="text-gray-400 hover:text-white">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div class="p-5 space-y-4">
              <div class="text-sm text-gray-400">
                <span class="font-mono text-gray-200">{{ chmodTarget?.name }}</span>
              </div>

              <div class="grid grid-cols-4 gap-2 text-sm">
                <div></div>
                <div class="text-center text-gray-400 font-medium">Read</div>
                <div class="text-center text-gray-400 font-medium">Write</div>
                <div class="text-center text-gray-400 font-medium">Exec</div>

                <div class="text-gray-300">Owner</div>
                <div v-for="i in [0,1,2]" :key="`o${i}`" class="text-center">
                  <input type="checkbox" v-model="chmodBits[i]" class="w-4 h-4 accent-nvidia rounded" />
                </div>

                <div class="text-gray-300">Group</div>
                <div v-for="i in [3,4,5]" :key="`g${i}`" class="text-center">
                  <input type="checkbox" v-model="chmodBits[i]" class="w-4 h-4 accent-nvidia rounded" />
                </div>

                <div class="text-gray-300">Other</div>
                <div v-for="i in [6,7,8]" :key="`t${i}`" class="text-center">
                  <input type="checkbox" v-model="chmodBits[i]" class="w-4 h-4 accent-nvidia rounded" />
                </div>
              </div>

              <div class="flex items-center gap-4 text-sm">
                <span class="text-gray-400">Preview:</span>
                <span class="font-mono text-gray-100">{{ bitsToString(chmodBits) }}</span>
                <span class="font-mono text-gray-400">({{ bitsToOctal(chmodBits) }})</span>
              </div>
            </div>
            <div class="flex justify-end gap-3 px-5 py-4 border-t border-gray-700">
              <button @click="showChmod = false" class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors">Cancel</button>
              <button @click="applyChmod" :disabled="chmodSubmitting" class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 disabled:opacity-50 transition-colors">
                {{ chmodSubmitting ? 'Applying...' : 'Apply' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Rename Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showRename" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showRename = false">
          <div class="w-full max-w-md bg-gray-900 rounded-xl border border-gray-700 shadow-2xl">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700">
              <h3 class="text-lg font-semibold text-gray-100">Rename</h3>
              <button @click="showRename = false" class="text-gray-400 hover:text-white">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div class="p-5 space-y-4">
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1.5">New Name</label>
                <input
                  v-model="renameName"
                  @keyup.enter="applyRename"
                  class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                />
              </div>
            </div>
            <div class="flex justify-end gap-3 px-5 py-4 border-t border-gray-700">
              <button @click="showRename = false" class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors">Cancel</button>
              <button @click="applyRename" :disabled="renameSubmitting" class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 disabled:opacity-50 transition-colors">
                {{ renameSubmitting ? 'Renaming...' : 'Rename' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Delete Confirmation -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showDelete" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showDelete = false">
          <div class="w-full max-w-md bg-gray-900 rounded-xl border border-gray-700 shadow-2xl">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700">
              <h3 class="text-lg font-semibold text-gray-100">Confirm Delete</h3>
              <button @click="showDelete = false" class="text-gray-400 hover:text-white">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div class="p-5">
              <p class="text-sm text-gray-300">
                Are you sure you want to delete
                <span class="font-mono font-semibold text-gray-100">{{ deleteTarget?.name }}</span>?
              </p>
              <p v-if="deleteTarget?.type === 'dir'" class="text-xs text-red-400 mt-2">
                This will recursively delete all contents.
              </p>
            </div>
            <div class="flex justify-end gap-3 px-5 py-4 border-t border-gray-700">
              <button @click="showDelete = false" class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors">Cancel</button>
              <button @click="applyDelete" :disabled="deleteSubmitting" class="px-4 py-2 text-sm font-medium rounded-lg bg-red-600 text-white hover:bg-red-500 disabled:opacity-50 transition-colors">
                {{ deleteSubmitting ? 'Deleting...' : 'Delete' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Mkdir Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showMkdir" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @mousedown.self="showMkdir = false">
          <div class="w-full max-w-md bg-gray-900 rounded-xl border border-gray-700 shadow-2xl">
            <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700">
              <h3 class="text-lg font-semibold text-gray-100">New Folder</h3>
              <button @click="showMkdir = false" class="text-gray-400 hover:text-white">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div class="p-5">
              <label class="block text-sm font-medium text-gray-300 mb-1.5">Folder Name</label>
              <input
                v-model="mkdirName"
                @keyup.enter="applyMkdir"
                class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-nvidia/50 placeholder-gray-500"
                placeholder="new-folder"
              />
            </div>
            <div class="flex justify-end gap-3 px-5 py-4 border-t border-gray-700">
              <button @click="showMkdir = false" class="px-4 py-2 text-sm rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors">Cancel</button>
              <button @click="applyMkdir" :disabled="mkdirSubmitting" class="px-4 py-2 text-sm font-medium rounded-lg bg-nvidia text-black hover:bg-nvidia/90 disabled:opacity-50 transition-colors">
                {{ mkdirSubmitting ? 'Creating...' : 'Create' }}
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
