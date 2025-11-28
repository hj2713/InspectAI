import os
from dotenv import load_dotenv
from bytez import Bytez

load_dotenv()
key = os.getenv("BYTEZ_API_KEY")
client = Bytez(key)

try:
    # Try to access the private method if it exists, just for debugging
    if hasattr(client, '_list_models'):
        print("Listing models...")
        models = client._list_models()
        print(models[:5]) # Print first 5
    else:
        print("No _list_models method.")
except Exception as e:
    print(f"Error listing models: {e}")
