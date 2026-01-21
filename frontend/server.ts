import { join } from 'path';
import * as ts from 'typescript';

// Get port from environment variable or use default
let PORT = process.env.PORT || 3000;

// Check if port is provided as command line argument
if (process.argv[2]) {
  try {
    const argPort = parseInt(process.argv[2], 10);
    if (!isNaN(argPort)) {
      PORT = argPort;
    }
  } catch (e) {
    console.warn('Invalid port argument, using default port 3000');
  }
}

// Base directory for static files
const BASE_DIR = process.cwd();
const DIST_DIR = join(BASE_DIR, 'dist');
const PUBLIC_DIR = join(BASE_DIR, 'public');
const SRC_DIR = join(BASE_DIR, 'src');

// MIME types for common file extensions
const MIME_TYPES: Record<string, string> = {
  '.js': 'application/javascript',
  '.jsx': 'application/javascript',
  '.ts': 'application/javascript',
  '.tsx': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.html': 'text/html',
  '.txt': 'text/plain',
};

// Get MIME type based on file extension
function getMimeType(filename: string): string {
  const ext = filename.substring(filename.lastIndexOf('.')).toLowerCase();
  return MIME_TYPES[ext] || 'application/octet-stream';
}
// 模块映射表
const moduleMap: Record<string, string> = {
  'react': '/node_modules/react/index.js',
  'react-dom': '/node_modules/react-dom/index.js',
  'react-dom/client': '/node_modules/react-dom/client.js',
  'react-router-dom': '/node_modules/react-router-dom/index.js',
  'antd': '/node_modules/antd/index.js',
  'antd/dist/reset.css': '/node_modules/antd/dist/reset.css',
  'axios': '/node_modules/axios/index.js',
  'i18next': '/node_modules/i18next/index.js',
  'react-i18next': '/node_modules/react-i18next/index.js',
  'zustand': '/node_modules/zustand/index.js'
};

// 特殊模块处理（需要异步加载的模块）
const asyncModules = [
  '@web3icons/react/dynamic'
];

// TypeScript transpile options
const transpileOptions: ts.TranspileOptions = {
  compilerOptions: {
    jsx: 'react',
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ESNext,
    moduleResolution: ts.ModuleResolutionKind.NodeNext,
    allowJs: true,
    esModuleInterop: true,
    strict: true,
    skipLibCheck: true,
    forceConsistentCasingInFileNames: true,
    jsxFactory: 'React.createElement',
    jsxFragmentFactory: 'React.Fragment'
  }
};
// Serve static file
async function serveStaticFile(path: string): Promise<Response | null> {
  try {
    // Remove leading slash from path
    const cleanPath = path.startsWith('/') ? path.slice(1) : path;
    
    // Try different path variations
    let filePath: string;
    
    // Variation 1: First check dist directory (built files)
    filePath = join(DIST_DIR, cleanPath);
    if (await Bun.file(filePath).exists()) {
      const content = await Bun.file(filePath).bytes();
      return new Response(content, {
        headers: {
          'Content-Type': getMimeType(filePath),
          'Cache-Control': 'no-cache',
        },
      });
    }
    
    // Variation 2: Directly in public directory
    filePath = join(PUBLIC_DIR, cleanPath);
    if (await Bun.file(filePath).exists()) {
      const content = await Bun.file(filePath).bytes();
      return new Response(content, {
        headers: {
          'Content-Type': getMimeType(filePath),
          'Cache-Control': 'no-cache',
        },
      });
    }
    
    // Variation 3: For paths starting with 'src/', use the path without 'src/' prefix in src directory
    if (cleanPath.startsWith('src/')) {
      const relativePath = cleanPath.slice(4); // Remove 'src/' prefix
      filePath = join(SRC_DIR, relativePath);
      if (await Bun.file(filePath).exists()) {
        // For TypeScript/JSX/JS files, transpile to JavaScript
if (filePath.endsWith('.ts') || filePath.endsWith('.tsx') || filePath.endsWith('.jsx') || filePath.endsWith('.js')) {
          try {
            const content = await Bun.file(filePath).text();
            const transpiled = ts.transpileModule(content, transpileOptions);
            
            // Process transpiled code to replace bare module imports
let transpiledCode = transpiled.outputText;
// Replace bare module imports with relative paths
for (const [moduleName, modulePath] of Object.entries(moduleMap)) {
  const regex = new RegExp(`from ['"]${moduleName}['"]`, 'g');
  transpiledCode = transpiledCode.replace(regex, `from '${modulePath}'`);
}

// 处理需要异步加载的模块
for (const asyncModule of asyncModules) {
  const regex = new RegExp(`from ['"]${asyncModule}['"]`, 'g');
  // 保持原始导入语句，不进行映射，确保它们被异步加载
  // 这里我们不替换，让浏览器保持原始的动态导入
}

// 处理需要异步加载的模块
for (const asyncModule of asyncModules) {
  const regex = new RegExp(`from ['"]${asyncModule}['"]`, 'g');
  // 保持原始导入语句，不进行映射，确保它们被异步加载
  // 这里我们不替换，让浏览器保持原始的动态导入
}
            
            return new Response(transpiledCode, {
              headers: {
                'Content-Type': 'application/javascript',
                'Cache-Control': 'no-cache',
              },
            });
          } catch (transpileError) {
            console.error('Error transpiling TypeScript/JSX file:', transpileError);
            // Fallback to serving the original file
            const content = await Bun.file(filePath).bytes();
            return new Response(content, {
              headers: {
                'Content-Type': 'application/javascript',
                'Cache-Control': 'no-cache',
              },
            });
          }
        }
        
        // For other files, serve with proper MIME type
        const content = await Bun.file(filePath).bytes();
        return new Response(content, {
          headers: {
            'Content-Type': getMimeType(filePath),
            'Cache-Control': 'no-cache',
          },
        });
      }
    }
    
    // Variation 4: Directly in src directory
    filePath = join(SRC_DIR, cleanPath);
    if (await Bun.file(filePath).exists()) {
      // For TypeScript/JSX/JS files, transpile to JavaScript
if (filePath.endsWith('.ts') || filePath.endsWith('.tsx') || filePath.endsWith('.jsx') || filePath.endsWith('.js')) {
          try {
            const content = await Bun.file(filePath).text();
            const transpiled = ts.transpileModule(content, transpileOptions);
            
            // Process transpiled code to replace bare module imports
            let transpiledCode = transpiled.outputText;
            // Replace bare module imports with relative paths
            for (const [moduleName, modulePath] of Object.entries(moduleMap)) {
              const regex = new RegExp(`from ['"]${moduleName}['"]`, 'g');
              transpiledCode = transpiledCode.replace(regex, `from '${modulePath}'`);
            }
            
            // 处理需要异步加载的模块
            for (const asyncModule of asyncModules) {
              const regex = new RegExp(`from ['"]${asyncModule}['"]`, 'g');
              // 保持原始导入语句，不进行映射，确保它们被异步加载
              // 这里我们不替换，让浏览器保持原始的动态导入
            }
            
            return new Response(transpiledCode, {
              headers: {
                'Content-Type': 'application/javascript',
                'Cache-Control': 'no-cache',
              },
            });
          } catch (transpileError) {
            console.error('Error transpiling TypeScript/JSX file:', transpileError);
            // Fallback to serving the original file
            const content = await Bun.file(filePath).bytes();
            return new Response(content, {
              headers: {
                'Content-Type': 'application/javascript',
                'Cache-Control': 'no-cache',
              },
            });
          }
        }
      
      // For other files, serve with proper MIME type
      const content = await Bun.file(filePath).bytes();
      return new Response(content, {
        headers: {
          'Content-Type': getMimeType(filePath),
          'Cache-Control': 'no-cache',
        },
      });
    }
    
    // Variation 5: Check node_modules directory for external dependencies
    if (cleanPath.startsWith('node_modules/')) {
      const nodeModulesPath = join(BASE_DIR, cleanPath);
      if (await Bun.file(nodeModulesPath).exists()) {
        const content = await Bun.file(nodeModulesPath).bytes();
        return new Response(content, {
          headers: {
            'Content-Type': getMimeType(nodeModulesPath),
            'Cache-Control': 'no-cache',
          },
        });
      }
    }
    
    // If file still doesn't exist, return null
    return null;
  } catch (error) {
    console.error('Error serving static file:', error);
    return null;
  }
}

// Proxy API request to backend
async function proxyApiRequest(request: Request): Promise<Response> {
  try {
    const url = new URL(request.url);
    const apiUrl = `http://localhost:8000${url.pathname}${url.search}`;
    
    const proxyRequest = new Request(apiUrl, {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });
    
    return await fetch(proxyRequest);
  } catch (error) {
    console.error('Error proxying API request:', error);
    return new Response(JSON.stringify({ error: 'Failed to proxy API request' }), {
      status: 500,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }
}

// Start the server
const server = Bun.serve({
  port: PORT,
  // Use routes configuration for better organization
  routes: {
    // API proxy route
    "/api/*": async (req) => {
      return await proxyApiRequest(req);
    },
    
    // Root path and index.html
    "/": async () => {
      try {
        // First check dist directory for built index.html
        const distIndexHtmlPath = join(DIST_DIR, 'index.html');
        if (await Bun.file(distIndexHtmlPath).exists()) {
          const content = await Bun.file(distIndexHtmlPath).text();
          return new Response(content, {
            headers: {
              'Content-Type': 'text/html',
            },
          });
        }
        
        // Then check public directory
        const publicIndexHtmlPath = join(PUBLIC_DIR, 'index.html');
        if (await Bun.file(publicIndexHtmlPath).exists()) {
          const content = await Bun.file(publicIndexHtmlPath).text();
          return new Response(content, {
            headers: {
              'Content-Type': 'text/html',
            },
          });
        } else {
          // If index.html doesn't exist in public, create a basic one
          const basicHtml = `
            <!DOCTYPE html>
            <html lang="en">
              <head>
                <meta charset="UTF-8">
                <link rel="icon" type="image/svg+xml" href="/qbot.svg">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Quantitative Trading System</title>
              </head>
              <body>
                <div id="root"></div>
                <script type="module" src="/src/main.tsx"></script>
              </body>
            </html>
          `;
          return new Response(basicHtml, {
            headers: {
              'Content-Type': 'text/html',
            },
          });
        }
      } catch (error) {
        console.error('Error serving index.html:', error);
        return new Response('Internal Server Error', { status: 500 });
      }
    },
    
    // Index.html route
    "/index.html": async () => {
      try {
        // First check dist directory for built index.html
        const distIndexHtmlPath = join(DIST_DIR, 'index.html');
        if (await Bun.file(distIndexHtmlPath).exists()) {
          const content = await Bun.file(distIndexHtmlPath).text();
          return new Response(content, {
            headers: {
              'Content-Type': 'text/html',
            },
          });
        }
        
        // Then check public directory
        const publicIndexHtmlPath = join(PUBLIC_DIR, 'index.html');
        if (await Bun.file(publicIndexHtmlPath).exists()) {
          const content = await Bun.file(publicIndexHtmlPath).text();
          return new Response(content, {
            headers: {
              'Content-Type': 'text/html',
            },
          });
        } else {
          // If index.html doesn't exist in public, create a basic one
          const basicHtml = `
            <!DOCTYPE html>
            <html lang="en">
              <head>
                <meta charset="UTF-8">
                <link rel="icon" type="image/svg+xml" href="/qbot.svg">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Quantitative Trading System</title>
              </head>
              <body>
                <div id="root"></div>
                <script type="module" src="/src/main.tsx"></script>
              </body>
            </html>
          `;
          return new Response(basicHtml, {
            headers: {
              'Content-Type': 'text/html',
            },
          });
        }
      } catch (error) {
        console.error('Error serving index.html:', error);
        return new Response('Internal Server Error', { status: 500 });
      }
    },
  },
  
  // Fallback for all other routes (static files)
  fetch: async (req) => {
    const url = new URL(req.url);
    const path = url.pathname;
    
    // Handle API routes first
    if (path.startsWith('/api/')) {
      return await proxyApiRequest(req);
    }
    
    // Handle static files
    const staticResponse = await serveStaticFile(path);
    if (staticResponse) {
      return staticResponse;
    }
    
    // Route fallback: return index.html for all other routes
    // This allows React Router to handle client-side routing
    try {
      // First check dist directory for built index.html
      const distIndexHtmlPath = join(DIST_DIR, 'index.html');
      if (await Bun.file(distIndexHtmlPath).exists()) {
        const content = await Bun.file(distIndexHtmlPath).text();
        return new Response(content, {
          headers: {
            'Content-Type': 'text/html',
          },
        });
      }
      
      // Then check public directory
      const publicIndexHtmlPath = join(PUBLIC_DIR, 'index.html');
      if (await Bun.file(publicIndexHtmlPath).exists()) {
        const content = await Bun.file(publicIndexHtmlPath).text();
        return new Response(content, {
          headers: {
            'Content-Type': 'text/html',
          },
        });
      } else {
        // If index.html doesn't exist in public, create a basic one
        const basicHtml = `
          <!DOCTYPE html>
          <html lang="en">
            <head>
              <meta charset="UTF-8">
              <link rel="icon" type="image/svg+xml" href="/qbot.svg">
              <meta name="viewport" content="width=device-width, initial-scale=1.0">
              <title>Quantitative Trading System</title>
            </head>
            <body>
              <div id="root"></div>
              <script type="module" src="/src/main.tsx"></script>
            </body>
          </html>
        `;
        return new Response(basicHtml, {
          headers: {
            'Content-Type': 'text/html',
          },
        });
      }
    } catch (error) {
      console.error('Error serving index.html for route fallback:', error);
      return new Response('Internal Server Error', { status: 500 });
    }
  },
  
  // Error handler
  error(error: Error): Response {
    console.error('Server error:', error);
    return new Response('Internal Server Error', { status: 500 });
  },
});

console.log(`Bun HTTP server started on port ${PORT}`);
console.log(`Server URL: http://localhost:${PORT}`);
console.log(`Serving files from:`);
console.log(`- Dist directory: ${DIST_DIR}`);
console.log(`- Public directory: ${PUBLIC_DIR}`);
console.log(`- Source directory: ${SRC_DIR}`);
console.log(`API proxy configured to: http://localhost:8000`);
