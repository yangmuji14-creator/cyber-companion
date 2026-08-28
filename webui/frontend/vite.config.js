import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

const BACKEND = 'http://127.0.0.1:8000';

// 单目录方案：源码在 webui/frontend，构建产物直接接管 webui/static。
// base:'./' 保证产物用相对路径引用 assets，后端 add_static('/static/') 直出。
export default defineConfig({
  // base 必须与后端挂载点一致：aiohttp add_static("/static/", STATIC_DIR)
  // 产物 index.html 会引用 /static/assets/...，恰好命中后端 static 路由
  base: '/static/',
  plugins: [svelte()],
  build: {
    outDir: '../static',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
  server: {
    port: 5173,
    proxy: {
      // 所有后端路径代理到本机 aiohttp 服务（python main.py web）
      '/api': { target: BACKEND, changeOrigin: true },
      '/static': { target: BACKEND, changeOrigin: true },
      '/avatars': { target: BACKEND, changeOrigin: true },
      '/stickers': { target: BACKEND, changeOrigin: true },
    },
  },
});
