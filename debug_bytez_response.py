import os
from dotenv import load_dotenv
from bytez import Bytez

load_dotenv()
key = os.getenv("BYTEZ_API_KEY")
client = Bytez(key)
# Use a model known to exist in Bytez docs
model = client.model("Qwen/Qwen3-0.6B")

print("Running model...")
resp = model.run("Hello")
print(f"Type: {type(resp)}")
print(f"Dir: {dir(resp)}")
print(f"Response: {resp}")
