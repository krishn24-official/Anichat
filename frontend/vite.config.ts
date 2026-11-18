import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { adminPreview } from './dev/adminPreview.js'

// https://vite.dev/config/
// `npm run dev:admin` (mode "admin"): also serves the admin functions locally (dev/adminPreview.ts);
// `npm run dev:admin:live` (mode "admin-live"): the same, on the real store (the deployed form's data).
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss(), ...(mode.startsWith('admin') ? [adminPreview(mode === 'admin-live')] : [])],
}))
