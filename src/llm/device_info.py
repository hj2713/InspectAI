"""GPU/Device diagnostics for LLM."""
import torch

def print_device_info():
    """Print detailed information about available compute devices."""
    print("\nDevice Information:")
    print("-" * 50)
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    
    if torch.cuda.is_available():
        print("\nGPU Information:")
        print(f"Current device: {torch.cuda.current_device()}")
        print(f"Device name: {torch.cuda.get_device_name()}")
        print(f"Device memory (GB): {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f}")
        print(f"CUDA version: {torch.version.cuda}")
    else:
        print("\nNo GPU detected - will use CPU")
        
    print("\nWill use device:", "cuda" if torch.cuda.is_available() else "cpu")
    print("-" * 50)
    
if __name__ == "__main__":
    print_device_info()