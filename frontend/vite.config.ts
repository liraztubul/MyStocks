import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // Bundles go to /static/ (not Vite's default /assets/) so the /assets/:symbol route doesn't
    // collide with build files; vercel.json and nginx.conf exclude /static/ from the SPA fallback.
    assetsDir: 'static',
  },
  server: {
    proxy: {
      '/api': process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
    },
  },
})
