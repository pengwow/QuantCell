# Get the absolute path to the project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$FRONTEND_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"

cd $FRONTEND_DIR/src-tauri
mkdir -p binaries
ARCH=$(uname -m)
echo "Current runner architecture: $ARCH"

for UV_ARCH in aarch64-apple-darwin x86_64-apple-darwin; do
	echo "Downloading uv for $UV_ARCH..."
	curl -L -f -o uv-${UV_ARCH}.tar.gz "https://github.com/astral-sh/uv/releases/download/0.9.9/uv-${UV_ARCH}.tar.gz"
	# Extract tar.gz file to temporary directory
	mkdir -p temp_${UV_ARCH}
	tar -xzf uv-${UV_ARCH}.tar.gz -C temp_${UV_ARCH}
	# Find uv executable file after extraction
	UV_PATH=$(find temp_${UV_ARCH} -name "uv" -type f | head -1)
	if [ -z "$UV_PATH" ]; then
	  echo "Error: uv executable not found for $UV_ARCH after extraction"
	  echo "Contents of temp_${UV_ARCH}:"
	  ls -la temp_${UV_ARCH}/
	  exit 1
	fi
	echo "Found uv at: $UV_PATH"
	# Move uv to binaries directory with architecture suffix
	mv "$UV_PATH" "binaries/uv-${UV_ARCH}"
	chmod +x "binaries/uv-${UV_ARCH}"
	# Clean up
	rm -rf temp_${UV_ARCH} uv-${UV_ARCH}.tar.gz
  done
  
  # Debug: List all files in binaries directory
  echo "Contents of binaries directory:"
  ls -lah binaries/
  echo "Verifying uv executables:"
  file binaries/uv-* || echo "No uv files found"
