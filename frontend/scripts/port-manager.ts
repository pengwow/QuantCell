/**
 * 端口管理工具
 *
 * 提供端口占用检测、可用端口查找、端口信息持久化等功能。
 *
 * 使用示例:
 *   import { PortManager } from './port-manager';
 *
 *   const portManager = new PortManager();
 *   const availablePort = await portManager.findAvailablePort(5173, 5183);
 *   if (availablePort) {
 *     portManager.savePortInfo(availablePort, 'frontend');
 *   }
 */

import * as net from 'net';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { fileURLToPath } from 'url';

export interface PortInfo {
  port: number;
  pid: number;
  startedAt: string;
  service: string;
}

export interface PortConfig {
  backend: {
    default: number;
    range: [number, number];
  };
  frontend: {
    default: number;
    range: [number, number];
  };
}

export class PortManager {
  // 默认端口配置
  static readonly DEFAULT_BACKEND_PORT = 8000;
  static readonly DEFAULT_BACKEND_RANGE: [number, number] = [8000, 8010];
  static readonly DEFAULT_FRONTEND_PORT = 5173;
  static readonly DEFAULT_FRONTEND_RANGE: [number, number] = [5173, 5183];

  private projectRoot: string;
  private portsFile: string;

  constructor(projectRoot?: string) {
    if (projectRoot) {
      this.projectRoot = projectRoot;
    } else {
      // 从当前文件位置推断项目根目录 (ESM 兼容方式)
      const __filename = fileURLToPath(import.meta.url);
      const __dirname = path.dirname(__filename);
      this.projectRoot = path.resolve(__dirname, '..', '..');
    }

    this.portsFile = path.join(this.projectRoot, '.quantcell', 'ports.json');
    this.ensurePortsDir();
  }

  /**
   * 确保端口信息目录存在
   */
  private ensurePortsDir(): void {
    const portsDir = path.dirname(this.portsFile);
    if (!fs.existsSync(portsDir)) {
      fs.mkdirSync(portsDir, { recursive: true });
    }
  }

  /**
   * 检查端口是否可用
   */
  async checkPortAvailable(port: number, host: string = '127.0.0.1'): Promise<boolean> {
    return new Promise((resolve) => {
      const server = net.createServer();
      server.once('error', () => {
        resolve(false);
      });
      server.once('listening', () => {
        server.close();
        resolve(true);
      });
      server.listen(port, host);
    });
  }

  /**
   * 在指定范围内查找可用端口
   */
  async findAvailablePort(
    startPort: number,
    endPort: number,
    host: string = '127.0.0.1'
  ): Promise<number | null> {
    for (let port = startPort; port <= endPort; port++) {
      const isAvailable = await this.checkPortAvailable(port, host);
      if (isAvailable) {
        console.log(`[PortManager] 找到可用端口: ${port}`);
        return port;
      } else {
        console.log(`[PortManager] 端口 ${port} 已被占用`);
      }
    }
    return null;
  }

  /**
   * 获取默认端口范围配置
   */
  getDefaultPortRanges(): PortConfig {
    return {
      backend: {
        default: PortManager.DEFAULT_BACKEND_PORT,
        range: PortManager.DEFAULT_BACKEND_RANGE,
      },
      frontend: {
        default: PortManager.DEFAULT_FRONTEND_PORT,
        range: PortManager.DEFAULT_FRONTEND_RANGE,
      },
    };
  }

  /**
   * 保存端口信息到文件
   */
  savePortInfo(port: number, service: string): void {
    const portInfo: PortInfo = {
      port,
      pid: process.pid,
      startedAt: new Date().toISOString(),
      service,
    };

    // 读取现有配置
    const portsData = this.loadPortsFile();

    // 更新配置
    portsData[service] = portInfo;

    // 保存配置
    this.savePortsFile(portsData);
    console.log(`[PortManager] 已保存 ${service} 端口信息: ${port}`);
  }

  /**
   * 从文件加载端口信息
   */
  loadPortInfo(service: string): number | null {
    const portsData = this.loadPortsFile();
    const serviceInfo = portsData[service];
    if (serviceInfo) {
      return serviceInfo.port;
    }
    return null;
  }

  /**
   * 获取所有端口信息
   */
  getAllPortInfo(): Record<string, PortInfo> {
    return this.loadPortsFile();
  }

  /**
   * 清除端口信息
   */
  clearPortInfo(service?: string): void {
    if (service === undefined) {
      if (fs.existsSync(this.portsFile)) {
        fs.unlinkSync(this.portsFile);
        console.log('[PortManager] 已清除所有端口信息');
      }
    } else {
      const portsData = this.loadPortsFile();
      if (portsData[service]) {
        delete portsData[service];
        this.savePortsFile(portsData);
        console.log(`[PortManager] 已清除 ${service} 端口信息`);
      }
    }
  }

  /**
   * 加载端口信息文件
   */
  private loadPortsFile(): Record<string, PortInfo> {
    if (!fs.existsSync(this.portsFile)) {
      return {};
    }

    try {
      const data = fs.readFileSync(this.portsFile, 'utf-8');
      return JSON.parse(data);
    } catch (error) {
      console.warn(`[PortManager] 读取端口信息文件失败: ${error}`);
      return {};
    }
  }

  /**
   * 保存端口信息文件
   */
  private savePortsFile(data: Record<string, PortInfo>): void {
    try {
      fs.writeFileSync(this.portsFile, JSON.stringify(data, null, 2), 'utf-8');
    } catch (error) {
      console.error(`[PortManager] 保存端口信息文件失败: ${error}`);
    }
  }

  /**
   * 查找后端端口
   */
  async findBackendPort(preferredPort?: number): Promise<{ port: number; isPreferred: boolean }> {
    const config = this.getDefaultPortRanges();

    // 如果指定了优先端口，先尝试使用
    if (preferredPort !== undefined) {
      const isAvailable = await this.checkPortAvailable(preferredPort);
      if (isAvailable) {
        console.log(`[PortManager] 优先端口 ${preferredPort} 可用`);
        return { port: preferredPort, isPreferred: true };
      } else {
        console.log(`[PortManager] 优先端口 ${preferredPort} 已被占用`);
      }
    }

    // 尝试默认端口
    const defaultPort = config.backend.default;
    const isDefaultAvailable = await this.checkPortAvailable(defaultPort);
    if (isDefaultAvailable) {
      console.log(`[PortManager] 默认端口 ${defaultPort} 可用`);
      return { port: defaultPort, isPreferred: false };
    }

    // 在范围内查找可用端口
    const [rangeStart, rangeEnd] = config.backend.range;
    console.log(`[PortManager] 在端口范围 ${rangeStart}-${rangeEnd} 内查找可用端口...`);

    const availablePort = await this.findAvailablePort(rangeStart, rangeEnd);
    if (availablePort) {
      console.log(`[PortManager] 找到可用端口: ${availablePort}`);
      return { port: availablePort, isPreferred: false };
    }

    // 如果没有找到，抛出错误
    throw new Error(
      `在端口范围 ${rangeStart}-${rangeEnd} 内未找到可用端口，` +
      '请关闭占用端口的进程或扩大端口范围'
    );
  }

  /**
   * 查找前端端口
   */
  async findFrontendPort(preferredPort?: number): Promise<{ port: number; isPreferred: boolean }> {
    const config = this.getDefaultPortRanges();

    // 如果指定了优先端口，先尝试使用
    if (preferredPort !== undefined) {
      const isAvailable = await this.checkPortAvailable(preferredPort);
      if (isAvailable) {
        console.log(`[PortManager] 优先端口 ${preferredPort} 可用`);
        return { port: preferredPort, isPreferred: true };
      } else {
        console.log(`[PortManager] 优先端口 ${preferredPort} 已被占用`);
      }
    }

    // 尝试默认端口
    const defaultPort = config.frontend.default;
    const isDefaultAvailable = await this.checkPortAvailable(defaultPort);
    if (isDefaultAvailable) {
      console.log(`[PortManager] 默认端口 ${defaultPort} 可用`);
      return { port: defaultPort, isPreferred: false };
    }

    // 在范围内查找可用端口
    const [rangeStart, rangeEnd] = config.frontend.range;
    console.log(`[PortManager] 在端口范围 ${rangeStart}-${rangeEnd} 内查找可用端口...`);

    const availablePort = await this.findAvailablePort(rangeStart, rangeEnd);
    if (availablePort) {
      console.log(`[PortManager] 找到可用端口: ${availablePort}`);
      return { port: availablePort, isPreferred: false };
    }

    // 如果没有找到，抛出错误
    throw new Error(
      `在端口范围 ${rangeStart}-${rangeEnd} 内未找到可用端口，` +
      '请关闭占用端口的进程或扩大端口范围'
    );
  }

  /**
   * 获取后端端口（从文件或查找）
   */
  async getBackendPort(): Promise<number> {
    // 首先尝试从文件读取
    const savedPort = this.loadPortInfo('backend');
    if (savedPort !== null) {
      const isAvailable = await this.checkPortAvailable(savedPort);
      if (isAvailable) {
        console.log(`[PortManager] 使用已保存的后端端口: ${savedPort}`);
        return savedPort;
      } else {
        console.log(`[PortManager] 已保存的后端端口 ${savedPort} 已被占用，重新查找`);
      }
    }

    // 查找新端口
    const { port } = await this.findBackendPort();
    this.savePortInfo(port, 'backend');
    return port;
  }
}

// 导出单例
let portManagerInstance: PortManager | null = null;

export function getPortManager(): PortManager {
  if (!portManagerInstance) {
    portManagerInstance = new PortManager();
  }
  return portManagerInstance;
}
