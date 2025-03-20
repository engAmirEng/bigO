import { defineConfig, loadEnv } from 'vite';
import { resolve, join } from 'path';
import react from '@vitejs/plugin-react';

export default defineConfig((mode) => {
  const env = loadEnv(mode, '.', '');
  const STATIC_URL_PREFIX = env.STATIC_URL_PREFIX;
  const DEV_SERVER_PORT = env.DEV_SERVER_PORT;

  const INPUT_DIR = './assets';
  const OUTPUT_DIR = join('dist', STATIC_URL_PREFIX);

  return {
    plugins: [
    react({
      include: '**/*.disabled',
    }),
    ],
    root: resolve(INPUT_DIR),
    base: join('/static/', STATIC_URL_PREFIX),
    server: {
      host: "127.0.0.1",
      port: DEV_SERVER_PORT,
    },
    build: {
      manifest: "manifest.json",
      emptyOutDir: true,
      outDir: resolve(OUTPUT_DIR),
      rollupOptions: {
        input: {
          aaa: join(INPUT_DIR, 'src/aaa.ts'),
          main: join(INPUT_DIR, 'src/main.tsx'),
        },
      },
    },
  };
});
