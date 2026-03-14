#!/usr/bin/env node
/**
 * 前端开发服务器启动脚本
 *
 * 支持自动端口检测和切换功能，自动识别后端端口。
 *
 * 使用示例:
 *   # 使用默认端口或自动查找可用端口
 *   bun run server
 *
 *   # 指定前端端口
 *   bun run server -- --port 3000
 *
 *   # 指定后端端口
 *   bun run server -- --backend-port 9000
 *
 *   # 指定端口范围
 *   bun run server -- --port-range 5173 5183
 */

import { createServer, ViteDevServer, InlineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { parseArgs } from 'util';
import { PortManager } from './port-manager';
import * as path from 'path';
import { fileURLToPath } from 'url';
import * as fs from 'fs';

interface ServerOptions {
  port?: number;
  backendPort?: number;
  portRange?: [number, number];
  host?: string;
}

/**
 * 解析命令行参数
 */
function parseOptions(): ServerOptions {
  const { values } = parseArgs({
    args: process.argv.slice(2),
    options: {
      port: {
        type: 'string',
        short: 'p',
      },
      'backend-port': {
        type: 'string',
        short: 'b',
      },
      'port-range': {
        type: 'string',
        multiple: true,
      },
      host: {
        type: 'string',
        short: 'h',
        default: 'localhost',
      },
    },
    strict: false,
  });

  const options: ServerOptions = {
    host: values.host as string,
  };

  if (values.port) {
    options.port = parseInt(values.port, 10);
  }

  if (values['backend-port']) {
    options.backendPort = parseInt(values['backend-port'], 10);
  }

  if (values['port-range'] && Array.isArray(values['port-range']) && values['port-range'].length >= 2) {
    options.portRange = [
      parseInt(values['port-range'][0], 10),
      parseInt(values['port-range'][1], 10),
    ];
  }

  return options;
}

/**
 * 打印启动横幅
 */
function printBanner(frontendPort: number, backendPort: number, host: string): void {
  const banner = `
╔══════════════════════════════════════════════════════════════╗
║                    QuantCell 前端服务                          ║
╠══════════════════════════════════════════════════════════════╣
║  前端地址: http://${host}:${frontendPort.toString().padEnd(5)}                          ║
║  后端代理: http://localhost:${backendPort.toString().padEnd(5)}                          ║
║  API 地址: http://${host}:${frontendPort}/api                 ║
╚══════════════════════════════════════════════════════════════╝
  `;
  console.log(banner);
}

/**
 * 获取后端端口
 */
async function getBackendPort(options: ServerOptions, portManager: PortManager): Promise<number> {
  // 如果命令行指定了后端端口，直接使用
  if (options.backendPort) {
    console.log(`[Server] 使用命令行指定的后端端口: ${options.backendPort}`);
    return options.backendPort;
  }

  // 尝试从端口信息文件读取
  const savedBackendPort = portManager.loadPortInfo('backend');
  if (savedBackendPort !== null) {
    // 检查端口是否仍然可用
    const isAvailable = await portManager.checkPortAvailable(savedBackendPort, '127.0.0.1');
    if (isAvailable) {
      console.log(`[Server] 使用已保存的后端端口: ${savedBackendPort}`);
      return savedBackendPort;
    } else {
      console.log(`[Server] 已保存的后端端口 ${savedBackendPort} 不可用`);
    }
  }

  // 使用默认后端端口
  console.log(`[Server] 使用默认后端端口: ${PortManager.DEFAULT_BACKEND_PORT}`);
  return PortManager.DEFAULT_BACKEND_PORT;
}

/**
 * 查找前端可用端口
 */
async function findFrontendPort(
  options: ServerOptions,
  portManager: PortManager
): Promise<number> {
  // 如果指定了端口，先尝试使用
  if (options.port !== undefined) {
    console.log(`[Server] 尝试使用指定端口: ${options.port}`);
    const isAvailable = await portManager.checkPortAvailable(options.port);
    if (isAvailable) {
      console.log(`[Server] 指定端口 ${options.port} 可用`);
      return options.port;
    } else {
      console.log(`[Server] 指定端口 ${options.port} 已被占用`);
    }
  }

  // 如果指定了端口范围，在范围内查找
  if (options.portRange) {
    const [start, end] = options.portRange;
    console.log(`[Server] 在指定范围 ${start}-${end} 内查找可用端口...`);
    const availablePort = await portManager.findAvailablePort(start, end);
    if (availablePort) {
      return availablePort;
    }
    throw new Error(`在端口范围 ${start}-${end} 内未找到可用端口`);
  }

  // 使用默认逻辑查找
  const { port } = await portManager.findFrontendPort(options.port);
  return port;
}

/**
 * 读取 package.json 版本号
 */
function getAppVersion(): string {
  try {
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = path.dirname(__filename);
    const packageJson = JSON.parse(fs.readFileSync(path.resolve(__dirname, '..', 'package.json'), 'utf-8'));
    return packageJson.version || '0.0.0';
  } catch {
    return '0.0.0';
  }
}

/**
 * 启动开发服务器
 */
async function startServer(): Promise<void> {
  console.log('='.repeat(60));
  console.log('QuantCell 前端服务启动');
  console.log('='.repeat(60));

  const options = parseOptions();
  const portManager = new PortManager();

  try {
    // 获取后端端口
    const backendPort = await getBackendPort(options, portManager);

    // 查找前端端口
    const frontendPort = await findFrontendPort(options, portManager);

    // 保存前端端口信息
    portManager.savePortInfo(frontendPort, 'frontend');

    console.log(`[Server] 最终配置:`);
    console.log(`[Server]   前端端口: ${frontendPort}`);
    console.log(`[Server]   后端端口: ${backendPort}`);
    console.log(`[Server]   主机地址: ${options.host}`);

    // 获取项目根目录
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = path.dirname(__filename);
    const projectRoot = path.resolve(__dirname, '..');

    // 创建 Vite 服务器配置（内联配置，避免动态导入问题）
    const serverConfig: InlineConfig = {
      root: projectRoot,
      plugins: [
        react({
          // 禁用 Fast Refresh 以避免重复声明问题
          fastRefresh: false,
        }),
        tailwindcss()
      ],
      define: {
        __APP_VERSION__: JSON.stringify(getAppVersion()),
        __BACKEND_PORT__: backendPort,
      },
      resolve: {
        alias: {
          '@': path.resolve(projectRoot, './src'),
        },
      },
      server: {
        port: frontendPort,
        host: options.host,
        strictPort: false,
        proxy: {
          '/api': {
            target: `http://localhost:${backendPort}`,
            changeOrigin: true,
          },
          '/ws': {
            target: `ws://localhost:${backendPort}`,
            ws: true,
          },
        },
      },
    };

    // 打印横幅
    printBanner(frontendPort, backendPort, options.host!);

    // 启动 Vite 服务器
    console.log('[Server] 正在启动 Vite 开发服务器...');
    const server: ViteDevServer = await createServer(serverConfig);

    await server.listen();

    console.log('[Server] 服务启动成功！');
    console.log('[Server] 按 Ctrl+C 停止服务');

    // 设置进程退出处理
    process.on('SIGINT', async () => {
      console.log('\n[Server] 接收到中断信号，正在关闭服务...');
      await server.close();
      portManager.clearPortInfo('frontend');
      process.exit(0);
    });

    process.on('SIGTERM', async () => {
      console.log('\n[Server] 接收到终止信号，正在关闭服务...');
      await server.close();
      portManager.clearPortInfo('frontend');
      process.exit(0);
    });

  } catch (error) {
    console.error('[Server] 启动失败:', error);
    portManager.clearPortInfo('frontend');
    process.exit(1);
  }
}

// 启动服务器
startServer().catch((error) => {
  console.error('[Server] 未处理的错误:', error);
  process.exit(1);
});
