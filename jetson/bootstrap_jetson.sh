#!/usr/bin/env bash
set -euo pipefail

export PYTHONNOUSERSITE=1

echo ">> Installing system packages (Jetson / TRT / build deps)…"
sudo apt-get update
sudo apt-get install -y \
  build-essential python3-dev cmake pkg-config \
  libv4l-dev ffmpeg \
  libboost-all-dev || true
sudo apt-get install -y python3-tensorrt || true
sudo apt-get install -y python3-libnvinfer python3-libnvinfer-dev tensorrt nvidia-tensorrt-dev || true

echo ">> Creating venv with system site-packages…"
if [ ! -d .venv ]; then
  uv venv --system-site-packages .venv
fi
. .venv/bin/activate

PY="python"
PIP="$PY -m pip"

echo ">> Ensure venv sees system dist-packages via .pth…"
$PY - <<'PY'
import sys, site, os
sp = site.getsitepackages()[0]
ver = f"{sys.version_info.major}.{sys.version_info.minor}"
pth = os.path.join(sp, "_add_dist_packages.pth")
candidates = [
    f"/usr/lib/python{ver}/dist-packages",
    f"/usr/local/lib/python{ver}/dist-packages",
    "/usr/lib/python3/dist-packages",
    "/usr/local/lib/python3/dist-packages",
]
with open(pth, "w") as f:
    for c in candidates:
        if os.path.isdir(c):
            f.write(c + "\n")
print("Wrote .pth:", pth)
PY

echo ">> Sync project deps (no extras by default)…"
uv sync

echo ">> Check TensorRT…"
if ! $PY -c "import tensorrt as trt; print('TensorRT:', trt.__version__)"; then
  echo "!! tensorrt not importable; verify python3-tensorrt or python3-libnvinfer installed and path is in _add_dist_packages.pth"
fi

echo ">> Check PyCUDA…"
if ! $PY - <<'PY'
import pycuda.driver as cuda
cuda.init()
print("PyCUDA OK. CUDA devices:", cuda.Device.count())
PY
then
  echo ">> Preparing toolchain for PyCUDA build…"
  export CUDA_ROOT=${CUDA_ROOT:-/usr/local/cuda}
  export PATH="$CUDA_ROOT/bin:$PATH"
  export LD_LIBRARY_PATH="$CUDA_ROOT/lib64:${LD_LIBRARY_PATH:-}"

  # Upgrade build tooling INSIDE the venv
  $PIP install -U pip setuptools wheel packaging

  # Preinstall build backend for sdists we’ll build without isolation
  $PIP install -U hatchling hatch-vcs

  # Ensure pure-python deps available before pycuda (so pip won’t try to sdist-build them during pycuda step)
  $PIP install -U "pytools>=2024.1" 

  # Add NumPy headers to CFLAGS (helps pycuda find array API)
  NUMPY_INC="$($PY -c 'import numpy; import sys; print(numpy.get_include())' 2>/dev/null || true)"
  if [ -n "${NUMPY_INC:-}" ]; then
    export CFLAGS="${CFLAGS:-} -I${NUMPY_INC}"
  fi

  # Clean any previous partial installs and build pycuda from source w/o isolation
  $PIP uninstall -y pycuda || true
  $PIP install --no-cache-dir --no-binary=:all: --no-build-isolation "pycuda>=2024.1"

  $PY - <<'PY'
import numpy as np, pycuda.driver as cuda
cuda.init()
print("PyCUDA rebuilt OK. NumPy:", np.__version__, "| CUDA devices:", cuda.Device.count())
PY
fi

echo ">> Final check:"
$PY - <<'PY'
try:
    import tensorrt as trt
    print("TensorRT:", trt.__version__)
except Exception as e:
    print("TensorRT not available:", e)
try:
    import numpy as np, pycuda.driver as cuda
    cuda.init()
    print("PyCUDA OK. NumPy:", np.__version__, "| CUDA devices:", cuda.Device.count())
except Exception as e:
    print("PyCUDA not available:", e)
PY

cat <<'TXT'

Bootstrap finished.

TXT
