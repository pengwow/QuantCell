import type { PluginInfo } from '@/api/plugin';

const loadedScripts = new Set<string>();
const loadedLinks = new Set<string>();

function loadScript(src: string): Promise<void> {
  if (loadedScripts.has(src)) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const el = document.createElement('script');
    el.src = src;
    el.async = true;
    el.onload = () => {
      loadedScripts.add(src);
      resolve();
    };
    el.onerror = () => reject(new Error(`加载脚本失败: ${src}`));
    document.head.appendChild(el);
  });
}

function loadCSS(href: string): Promise<void> {
  if (loadedLinks.has(href)) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const el = document.createElement('link');
    el.rel = 'stylesheet';
    el.href = href;
    el.onload = () => {
      loadedLinks.add(href);
      resolve();
    };
    el.onerror = () => reject(new Error(`加载样式失败: ${href}`));
    document.head.appendChild(el);
  });
}

export async function loadPluginAssets(plugin: PluginInfo): Promise<void> {
  const base = `/api/plugins/${plugin.name}/assets`;
  const cssUrl = `${base}/index.css`;
  const jsUrl = `${base}/index.js`;

  try {
    await loadCSS(cssUrl);
  } catch {
    // CSS 加载失败不阻塞插件运行
  }
  await loadScript(jsUrl);
}

export function unloadPluginAssets(pluginName: string): void {
  document
    .querySelectorAll(`script[data-plugin="${pluginName}"], link[data-plugin="${pluginName}"]`)
    .forEach((el) => el.remove());
}
