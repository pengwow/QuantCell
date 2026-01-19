import React from 'react';

// 菜单项类型定义
export interface MenuItem {
  path: string;
  name: string;
  icon?: React.ReactNode;
}

// 菜单组类型定义
export interface MenuGroup {
  group: string;
  items: MenuItem[];
}

// 路由配置类型定义
export interface RouteConfig {
  path: string;
  element: React.ReactNode;
}

// 系统配置项类型定义
export interface SystemConfigItem {
  key: string;
  value: string;
  description: string;
  type: 'string' | 'number' | 'boolean' | 'select';
  options?: string[]; // 当type为select时的选项
}

// 插件信息类型定义
export interface PluginInfo {
  name: string;
  version: string;
  description?: string;
  author?: string;
}

export class PluginBase {
  /** 插件名称 */
  public name: string;
  /** 插件版本 */
  public version: string;
  /** 插件描述 */
  public description?: string;
  /** 插件作者 */
  public author?: string;
  /** 插件是否激活 */
  public isActive: boolean;
  /** 插件注册的菜单 */
  protected menus: MenuGroup[];
  /** 插件注册的路由 */
  protected routes: RouteConfig[];
  /** 插件注册的系统配置 */
  protected systemConfigs: SystemConfigItem[];
  /** 插件配置子菜单名称 */
  protected configMenuName: string;

  constructor(name: string, version: string, description?: string, author?: string) {
    this.name = name;
    this.version = version;
    this.description = description;
    this.author = author;
    this.isActive = false;
    this.menus = [];
    this.routes = [];
    this.systemConfigs = [];
    this.configMenuName = `${name} ${'settings'}`;
  }

  /**
   * 注册插件
   */
  public register(): void {
    this.isActive = true;
    console.log(`插件 ${this.name} 注册成功`);
  }

  /**
   * 启动插件
   */
  public start(): void {
    this.isActive = true;
    console.log(`插件 ${this.name} 启动成功`);
  }

  /**
   * 停止插件
   */
  public stop(): void {
    this.isActive = false;
    console.log(`插件 ${this.name} 停止成功`);
  }

  /**
   * 添加菜单
   * @param menuGroup 菜单组配置
   */
  public addMenu(menuGroup: MenuGroup): void {
    this.menus.push(menuGroup);
  }

  /**
   * 添加路由
   * @param route 路由配置
   */
  public addRoute(route: RouteConfig): void {
    this.routes.push(route);
  }

  /**
   * 获取插件信息
   * @returns 插件信息
   */
  public getInfo(): PluginInfo {
    return {
      name: this.name,
      version: this.version,
      description: this.description,
      author: this.author
    };
  }

  /**
   * 获取插件菜单
   * @returns 菜单数组
   */
  public getMenus(): MenuGroup[] {
    return this.menus;
  }

  /**
   * 获取插件路由
   * @returns 路由数组
   */
  public getRoutes(): RouteConfig[] {
    return this.routes;
  }

  /**
   * 添加系统配置项
   * @param config 系统配置项
   */
  public addSystemConfig(config: SystemConfigItem): void {
    this.systemConfigs.push(config);
  }

  /**
   * 获取插件系统配置
   * @returns 系统配置数组
   */
  public getSystemConfigs(): SystemConfigItem[] {
    return this.systemConfigs;
  }

  /**
   * 设置配置菜单名称
   * @param name 菜单名称
   */
  public setConfigMenuName(name: string): void {
    this.configMenuName = name;
  }

  /**
   * 获取配置菜单名称
   * @returns 菜单名称
   */
  public getConfigMenuName(): string {
    return this.configMenuName;
  }

  /**
   * 获取插件配置值
   * @param key 配置键名
   * @returns 配置值
   */
  public getConfig(key: string): any {
    const config = this.systemConfigs.find(config => config.key === key);
    return config ? config.value : undefined;
  }

  /**
   * 设置插件配置值
   * @param key 配置键名
   * @param value 配置值
   */
  public setConfig(key: string, value: any): void {
    const config = this.systemConfigs.find(config => config.key === key);
    if (config) {
      config.value = value;
    }
  }
}
