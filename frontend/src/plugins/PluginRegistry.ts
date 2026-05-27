import type { ReactNode } from 'react';
import type { PluginInfo } from '@/api/plugin';

export interface PluginMenuItem {
  key: string;
  label: string;
  icon?: ReactNode;
  pluginName: string;
}

export interface PluginRoute {
  path: string;
  element: ReactNode;
  pluginName: string;
}

type Listener = () => void;

class PluginRegistry {
  private plugins = new Map<string, PluginInfo>();
  private menuItems: PluginMenuItem[] = [];
  private routes: PluginRoute[] = [];
  private listeners = new Set<Listener>();
  private loadingPlugins = new Set<string>();

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    for (const fn of this.listeners) fn();
  }

  registerPlugin(plugin: PluginInfo): void {
    const isNew = !this.plugins.has(plugin.name);
    this.plugins.set(plugin.name, plugin);

    if (isNew && plugin.status === 'enabled' && plugin.frontend_entry) {
      this.loadPluginFrontend(plugin);
    } else {
      this.notify();
    }
  }

  private async loadPluginFrontend(plugin: PluginInfo): Promise<void> {
    if (this.loadingPlugins.has(plugin.name)) return;
    this.loadingPlugins.add(plugin.name);

    try {
      const bundleUrl = `/api/plugins/${plugin.name}/assets/index.js`;
      const module = await import(/* @vite-ignore */ bundleUrl);

      if (typeof module.registerPlugin === 'function') {
        const instance = module.registerPlugin();
        this.registerPluginInstance(instance);
      }
    } catch (err) {
      console.warn(`插件 ${plugin.name} 前端加载失败:`, err);
    } finally {
      this.loadingPlugins.delete(plugin.name);
      this.notify();
    }
  }

  private registerPluginInstance(instance: any): void {
    if (typeof instance.getRoutes === 'function') {
      for (const route of instance.getRoutes()) {
        this.registerRoute(route);
      }
    }

    if (typeof instance.getMenuItems === 'function') {
      for (const item of instance.getMenuItems()) {
        this.registerMenu(item);
      }
    }
  }

  unregisterPlugin(name: string): void {
    this.plugins.delete(name);
    this.menuItems = this.menuItems.filter((m) => m.pluginName !== name);
    this.routes = this.routes.filter((r) => r.pluginName !== name);
    this.notify();
  }

  registerMenu(item: PluginMenuItem): void {
    if (!this.menuItems.some((m) => m.key === item.key)) {
      this.menuItems.push(item);
      this.notify();
    }
  }

  registerRoute(route: PluginRoute): void {
    if (!this.routes.some((r) => r.path === route.path)) {
      this.routes.push(route);
      this.notify();
    }
  }

  getPlugin(name: string): PluginInfo | undefined {
    return this.plugins.get(name);
  }

  getAllPlugins(): PluginInfo[] {
    return [...this.plugins.values()];
  }

  getMenuItems(): PluginMenuItem[] {
    return [...this.menuItems];
  }

  getRoutes(): PluginRoute[] {
    return [...this.routes];
  }
}

export const pluginRegistry = new PluginRegistry();
