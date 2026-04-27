/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_LAPTOP_URL?: string
  readonly VITE_RAILWAY_URL?: string
  readonly VITE_LAPTOP_KEY?: string
  readonly VITE_RAILWAY_KEY?: string
  readonly VITE_DEFAULT_BACKEND?: 'laptop' | 'railway'
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
