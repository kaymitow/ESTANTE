import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'

// O build vai para app/static/novo e é servido pelo FastAPI em / (a interface clássica fica em /classica).
// Em desenvolvimento (npm run dev), /api é repassado ao servidor local.
export default defineConfig({
  plugins: [svelte()],
  base: '/static/novo/',
  build: { outDir: '../static/novo', emptyOutDir: true },
  server: { proxy: { '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true, headers: { origin: 'http://127.0.0.1:8765' } } } },   // o servidor só aceita a própria origem
})
