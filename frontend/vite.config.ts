/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { compression } from 'vite-plugin-compression2'
import path from 'path'

const repoEnvDir = path.resolve(__dirname, '..')

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, repoEnvDir, 'VITE_')
  const sentryEnabled = env.VITE_SENTRY_ENABLED === 'true' || Boolean(env.VITE_SENTRY_DSN)
  const enableSourceMaps = env.VITE_SOURCEMAP === 'true' || sentryEnabled

  return {
    envDir: repoEnvDir,
    plugins: [
      tailwindcss(),
      react(),
      compression({ algorithms: ['gzip', 'brotliCompress'] }),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          ws: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: enableSourceMaps ? 'hidden' : false,
      target: 'es2022',
      minify: true,
      cssMinify: true,
      chunkSizeWarningLimit: 1100,
      rollupOptions: {
        output: {
          manualChunks(id: string) {
            if (id.includes('node_modules/react-dom') || id.includes('node_modules/react/') || id.includes('node_modules/react-router-dom')) {
              return 'vendor-react'
            }
            if (id.includes('node_modules/@tanstack/react-query')) {
              return 'vendor-query'
            }
            if (id.includes('node_modules/framer-motion')) {
              return 'vendor-motion'
            }
            if (id.includes('node_modules/@radix-ui')) {
              return 'vendor-radix'
            }
            if (id.includes('node_modules/lucide-react')) {
              return 'vendor-icons'
            }
          },
        },
      },
      rolldownOptions: {
        checks: {
          pluginTimings: false,
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
      css: true,
    },
  }
})
