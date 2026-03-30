<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const sidebarOpen = ref(true)
const mobileOpen = ref(false)
const isLoginPage = computed(() => route.name === 'Login')

function logout() {
  localStorage.removeItem('token')
  router.push('/login')
}

const navSections = [
  {
    items: [
      { label: 'Dashboard', icon: '⊞', to: '/' },
    ]
  },
  {
    title: 'Docker',
    items: [
      { label: 'Stacks', icon: '☰', to: '/stacks' },
      { label: 'Services', icon: '⚙', to: '/services' },
      { label: 'Containers', icon: '▣', to: '/containers' },
      { label: 'Images', icon: '◉', to: '/images' },
    ]
  },
  {
    title: 'KVM',
    items: [
      { label: 'Virtual Machines', icon: '⊟', to: '/vms' },
    ]
  },
  {
    title: 'Slurm',
    items: [
      { label: 'Jobs', icon: '▶', to: '/slurm/jobs' },
      { label: 'Cluster', icon: '⬡', to: '/slurm/cluster' },
    ]
  },
  {
    title: 'Network',
    items: [
      { label: 'Traefik', icon: '◈', to: '/traefik' },
      { label: 'Interfaces', icon: '⇄', to: '/network' },
    ]
  },
  {
    title: 'Storage',
    items: [
      { label: 'NFS & Disks', icon: '▤', to: '/storage' },
      { label: 'File Browser', icon: '▦', to: '/files' },
    ]
  },
]

function isActive(to) {
  if (to === '/') return route.path === '/'
  return route.path.startsWith(to)
}
</script>

<template>
  <router-view v-if="isLoginPage" />

  <template v-else>
  <!-- Mobile overlay -->
  <div
    v-if="mobileOpen"
    class="fixed inset-0 bg-black/50 z-40 lg:hidden"
    @click="mobileOpen = false"
  />

  <div class="flex h-screen overflow-hidden bg-gray-900">
    <!-- Sidebar -->
    <aside
      :class="[
        'fixed lg:static inset-y-0 left-0 z-50 flex flex-col bg-gray-800 border-r border-gray-700 transition-all duration-200',
        sidebarOpen ? 'w-64' : 'w-16',
        mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
      ]"
    >
      <!-- Sidebar header -->
      <div class="flex items-center h-14 px-3 border-b border-gray-700 shrink-0">
        <div class="flex items-center gap-2 overflow-hidden">
          <span class="text-nvidia font-bold text-xl shrink-0">⚡</span>
          <span
            v-show="sidebarOpen"
            class="text-sm font-semibold text-white whitespace-nowrap"
          >
            Spark Cluster
          </span>
        </div>
        <button
          class="ml-auto text-gray-400 hover:text-white p-1 rounded hidden lg:block"
          @click="sidebarOpen = !sidebarOpen"
          :title="sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              v-if="sidebarOpen"
              stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M11 19l-7-7 7-7m8 14l-7-7 7-7"
            />
            <path
              v-else
              stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M13 5l7 7-7 7M5 5l7 7-7 7"
            />
          </svg>
        </button>
      </div>

      <!-- Navigation -->
      <nav class="flex-1 overflow-y-auto py-2 px-2 space-y-1">
        <template v-for="(section, si) in navSections" :key="si">
          <div
            v-if="section.title && sidebarOpen"
            class="px-2 pt-3 pb-1 text-[10px] uppercase tracking-wider text-gray-500 font-semibold"
          >
            {{ section.title }}
          </div>
          <div v-else-if="section.title && !sidebarOpen" class="border-t border-gray-700 my-2" />

          <router-link
            v-for="item in section.items"
            :key="item.to"
            :to="item.to"
            :class="[
              'flex items-center gap-3 px-2 py-2 rounded-lg text-sm transition-colors group',
              isActive(item.to)
                ? 'bg-nvidia/10 text-nvidia'
                : 'text-gray-400 hover:text-white hover:bg-gray-700/50'
            ]"
            :title="!sidebarOpen ? item.label : undefined"
            @click="mobileOpen = false"
          >
            <span class="text-base shrink-0 w-5 text-center">{{ item.icon }}</span>
            <span v-show="sidebarOpen" class="whitespace-nowrap">{{ item.label }}</span>
          </router-link>
        </template>
      </nav>
    </aside>

    <!-- Main content -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <!-- Top bar -->
      <header class="h-14 bg-gray-800 border-b border-gray-700 flex items-center px-4 shrink-0">
        <!-- Mobile menu button -->
        <button
          class="lg:hidden text-gray-400 hover:text-white mr-3"
          @click="mobileOpen = !mobileOpen"
        >
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <h1 class="text-lg font-semibold text-white">
          <span class="text-nvidia">Spark</span> Cluster Manager
        </h1>

        <div class="ml-auto flex items-center gap-3">
          <span class="text-xs text-gray-400 hidden sm:block">v1.5.0</span>
          <button
            @click="logout"
            class="h-8 px-3 rounded-lg bg-gray-700 text-xs text-gray-300 hover:bg-gray-600 hover:text-white transition-colors"
            title="Sign out"
          >
            Sign out
          </button>
        </div>
      </header>

      <!-- Page content -->
      <main class="flex-1 overflow-y-auto p-4 lg:p-6">
        <router-view />
      </main>
    </div>
  </div>
  </template>
</template>
