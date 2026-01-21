import { join } from 'path';

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

// Serve static file
async function serveStaticFile(path: string): Promise<Response | null> {
  try {
    // Try public directory first
    let filePath = join(PUBLIC_DIR, path);
    
    // If file doesn't exist in public, try src directory
    if (!(await Bun.file(filePath).exists())) {
      filePath = join(SRC_DIR, path);
    }
    
    // If file still doesn't exist, return null
    if (!(await Bun.file(filePath).exists())) {
      return null;
    }
    
    // Read file content
    const content = await Bun.file(filePath).bytes();
    
    // Return response with appropriate MIME type
    return new Response(content, {
      headers: {
        'Content-Type': getMimeType(filePath),
        'Cache-Control': 'no-cache',
      },
    });
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
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;
    
    // Handle API proxy
    if (path.startsWith('/api')) {
      return await proxyApiRequest(request);
    }
    
    // Handle root path
    if (path === '/' || path === '/index.html') {
      try {
        const indexHtmlPath = join(PUBLIC_DIR, 'index.html');
        if (await Bun.file(indexHtmlPath).exists()) {
          const content = await Bun.file(indexHtmlPath).text();
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
    }
    
    // Handle static files
    const staticResponse = await serveStaticFile(path);
    if (staticResponse) {
      return staticResponse;
    }
    
    // Handle 404
    return new Response('Not Found', { status: 404 });
  },
  error(error: Error): Response {
    console.error('Server error:', error);
    return new Response('Internal Server Error', { status: 500 });
  },
});

console.log(`Bun HTTP server started on port ${PORT}`);
console.log(`Server URL: http://localhost:${PORT}`);
console.log(`Serving files from:`);
console.log(`- Public directory: ${PUBLIC_DIR}`);
console.log(`- Source directory: ${SRC_DIR}`);
console.log(`API proxy configured to: http://localhost:8000`);
