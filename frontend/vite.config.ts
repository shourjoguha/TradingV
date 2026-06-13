import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  // Plotly.js + transitive `has-hover` reference Node's `global`. Map to
  // `globalThis` so the bundle runs in the browser.
  define: {
    global: 'globalThis',
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // Pin React to one copy. react-day-picker (and similar libs)
      // resolved through hoisted node_modules can otherwise pull their
      // own React, triggering "Invalid hook call" at runtime.
      react: path.resolve(__dirname, './node_modules/react'),
      'react-dom': path.resolve(__dirname, './node_modules/react-dom'),
    },
    dedupe: ['react', 'react-dom'],
  },
  optimizeDeps: {
    include: ['react-day-picker', 'date-fns'],
  },
  server: {
    port: 3000,
    proxy: {
      '/v1': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
