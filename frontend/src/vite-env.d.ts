/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_LAPTOP_URL?: string
  readonly VITE_LAPTOP_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
