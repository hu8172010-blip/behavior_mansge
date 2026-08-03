$ErrorActionPreference = "Stop"
python -m pip install --upgrade `
  torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 `
  --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r requirements-training.txt
python scripts/verify_cuda.py
