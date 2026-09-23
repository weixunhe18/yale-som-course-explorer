import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Honour PORT when the environment assigns one; Vite otherwise picks 5173
    // and silently increments when that is taken, which strands any tooling
    // that expected the port it handed us.
    port: process.env.PORT ? Number(process.env.PORT) : 5173,
  },
})
