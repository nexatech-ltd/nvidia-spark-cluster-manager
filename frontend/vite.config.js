import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://localhost:8443',
      '/ws': { target: 'ws://localhost:8443', ws: true }
    }
  },
  build: {
    target: 'esnext'
  }
})
