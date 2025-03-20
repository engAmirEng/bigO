import { defineConfig, loadEnv } from 'vite';
import { resolve, join } from 'path';

export default defineConfig((mode) => {
  const env = loadEnv(mode, '.', '');
  const STATIC_URL_PREFIX = env.STATIC_URL_PREFIX;
  const DEV_SERVER_PORT = env.STATIC_URL_PREFIX;

  const INPUT_DIR = './assets';
  const OUTPUT_DIR = join('dist', STATIC_URL_PREFIX);

  return {
    root: resolve(INPUT_DIR),
    base: join('/static/', STATIC_URL_PREFIX),
    server: {
      host: "127.0.0.1",
      port: parseInt(DEV_SERVER_PORT),
    },
    build: {
      manifest: true,
      emptyOutDir: true,
      outDir: resolve(OUTPUT_DIR),
      rollupOptions: {
        input: {
          aaa: join(INPUT_DIR, 'src/aaa.ts'),
        },
      },
    },
  };
});
