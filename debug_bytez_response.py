import os
from dotenv import load_dotenv
from bytez import Bytez
from config.default_config import BYTEZ_MODEL

load_dotenv()
key = os.getenv("BYTEZ_API_KEY")
client = Bytez(key)
# Use the centralized model constant
model = client.model(BYTEZ_MODEL)

print("Running model...")
resp = model.run("Hello")
print(f"Type: {type(resp)}")
print(f"Dir: {dir(resp)}")
print(f"Response: {resp}")
