import { mount } from 'svelte';
import './styles/tokens.css';
import App from './App.svelte';

// 主题初始化：默认浅色，读 localStorage `cc-theme`（light / dark）
const theme = (() => {
  try {
    const saved = localStorage.getItem('cc-theme');
    return saved === 'dark' || saved === 'light' ? saved : 'light';
  } catch {
    return 'light';
  }
})();
document.documentElement.setAttribute('data-theme', theme);

const app = mount(App, {
  target: document.getElementById('app'),
});

export default app;
