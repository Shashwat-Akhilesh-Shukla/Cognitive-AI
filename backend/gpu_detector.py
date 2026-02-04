"""
GPU Detection and Configuration Utility

Detects GPU availability and provides optimal configuration for PyTorch models.
Supports automatic fallback to CPU when GPU is not available.
"""

import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def detect_gpu() -> Dict[str, any]:
    """
    Detect GPU availability and determine optimal compute configuration.
    
    Returns:
        dict: {
            'has_gpu': bool,
            'device': str,  # 'cuda' or 'cpu'
            'compute_type': str,  # 'float16' for GPU, 'int8' for CPU
            'gpu_name': str,  # GPU name if available
            'gpu_count': int,  # Number of GPUs
            'cuda_available': bool  # PyTorch CUDA availability
        }
    """
    result = {
        'has_gpu': False,
        'device': 'cpu',
        'compute_type': 'int8',
        'gpu_name': 'N/A',
        'gpu_count': 0,
        'cuda_available': False
    }
    
    # Check for NVIDIA GPU using nvidia-smi
    try:
        import subprocess
        nvidia_smi = subprocess.run(
            ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if nvidia_smi.returncode == 0:
            gpu_names = nvidia_smi.stdout.strip().split('\n')
            if gpu_names and gpu_names[0]:
                result['has_gpu'] = True
                result['gpu_name'] = gpu_names[0].strip()
                result['gpu_count'] = len(gpu_names)
                logger.info(f"✓ NVIDIA GPU detected: {result['gpu_name']}")
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"nvidia-smi not available or failed: {e}")
    
    # Check PyTorch CUDA availability
    try:
        import torch
        if torch.cuda.is_available():
            result['cuda_available'] = True
            result['device'] = 'cuda'
            result['compute_type'] = 'float16'
            
            # Get GPU info from PyTorch
            if not result['has_gpu']:  # nvidia-smi failed but CUDA available
                result['has_gpu'] = True
                result['gpu_name'] = torch.cuda.get_device_name(0)
                result['gpu_count'] = torch.cuda.device_count()
            
            logger.info(f"✓ PyTorch CUDA available: {result['gpu_count']} GPU(s)")
            logger.info(f"  Device: {result['device']}, Compute type: {result['compute_type']}")
        else:
            logger.info("ℹ PyTorch CUDA not available, using CPU")
    except ImportError:
        logger.warning("PyTorch not installed yet, cannot check CUDA availability")
    except Exception as e:
        logger.warning(f"Error checking PyTorch CUDA: {e}")
    
    return result


def get_pytorch_install_command() -> str:
    """
    Get the appropriate pip install command for PyTorch based on GPU availability.
    
    Returns:
        str: pip install command for PyTorch
    """
    gpu_info = detect_gpu()
    
    if gpu_info['has_gpu']:
        # Install CUDA-enabled PyTorch (CUDA 11.8 for broad compatibility)
        return "pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118"
    else:
        # Install CPU-only PyTorch
        return "pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu"


def get_whisper_config() -> Dict[str, str]:
    """
    Get optimal Whisper configuration based on GPU availability.
    
    Returns:
        dict: {
            'device': str,
            'compute_type': str
        }
    """
    gpu_info = detect_gpu()
    return {
        'device': gpu_info['device'],
        'compute_type': gpu_info['compute_type']
    }


def get_tts_config() -> Dict[str, bool]:
    """
    Get optimal TTS configuration based on GPU availability.
    
    Returns:
        dict: {
            'gpu': bool
        }
    """
    gpu_info = detect_gpu()
    return {
        'gpu': gpu_info['cuda_available']
    }


def log_gpu_status():
    """
    Log detailed GPU status information.
    Useful for debugging and monitoring.
    """
    logger.info("=" * 60)
    logger.info("GPU Detection Status")
    logger.info("=" * 60)
    
    gpu_info = detect_gpu()
    
    logger.info(f"GPU Available: {gpu_info['has_gpu']}")
    logger.info(f"GPU Name: {gpu_info['gpu_name']}")
    logger.info(f"GPU Count: {gpu_info['gpu_count']}")
    logger.info(f"PyTorch CUDA: {gpu_info['cuda_available']}")
    logger.info(f"Device: {gpu_info['device']}")
    logger.info(f"Compute Type: {gpu_info['compute_type']}")
    
    logger.info("=" * 60)
    
    return gpu_info


# Environment variable overrides
def get_device_override() -> Optional[str]:
    """
    Check for manual device override via environment variable.
    
    Returns:
        str or None: Device override ('cpu' or 'cuda') or None
    """
    override = os.getenv('FORCE_DEVICE', '').lower()
    if override in ['cpu', 'cuda']:
        logger.warning(f"⚠ Device manually overridden to: {override}")
        return override
    return None


def get_optimal_device() -> str:
    """
    Get optimal device considering both auto-detection and manual overrides.
    
    Returns:
        str: 'cuda' or 'cpu'
    """
    # Check for manual override first
    override = get_device_override()
    if override:
        return override
    
    # Auto-detect
    gpu_info = detect_gpu()
    return gpu_info['device']


if __name__ == "__main__":
    # CLI tool for GPU detection
    import json
    
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "=" * 60)
    print("AI Therapist - GPU Detection Utility")
    print("=" * 60 + "\n")
    
    gpu_info = log_gpu_status()
    
    print("\nConfiguration JSON:")
    print(json.dumps(gpu_info, indent=2))
    
    print("\nRecommended PyTorch Install Command:")
    print(get_pytorch_install_command())
    
    print("\nWhisper Config:")
    print(json.dumps(get_whisper_config(), indent=2))
    
    print("\nTTS Config:")
    print(json.dumps(get_tts_config(), indent=2))
    print()
