import shutil
import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.memory.vector_store import VectorStore

def test_vector_store_isolation():
    print("Testing Vector Store Isolation...")
    
    # Setup test DB path
    test_db_path = ".test_chroma_db"
    if os.path.exists(test_db_path):
        shutil.rmtree(test_db_path)
        
    try:
        store = VectorStore(persist_path=test_db_path)
        
        # Add data for Repo A
        store.add_document(
            text="Repo A secret function",
            metadata={"repo_id": "owner/repo-a", "type": "code"}
        )
        
        # Add data for Repo B
        store.add_document(
            text="Repo B secret function",
            metadata={"repo_id": "owner/repo-b", "type": "code"}
        )
        
        # Search in Repo A
        print("\nSearching in Repo A for 'secret'...")
        results_a = store.search("secret", repo_id="owner/repo-a")
        print(f"Found {len(results_a)} results")
        for r in results_a:
            print(f"- {r['content']} (Metadata: {r['metadata']})")
            assert r['metadata']['repo_id'] == "owner/repo-a"
            assert "Repo B" not in r['content']
            
        # Search in Repo B
        print("\nSearching in Repo B for 'secret'...")
        results_b = store.search("secret", repo_id="owner/repo-b")
        print(f"Found {len(results_b)} results")
        for r in results_b:
            print(f"- {r['content']} (Metadata: {r['metadata']})")
            assert r['metadata']['repo_id'] == "owner/repo-b"
            assert "Repo A" not in r['content']
            
        print("\n✅ Isolation Test Passed!")
        
    finally:
        # Cleanup
        if os.path.exists(test_db_path):
            shutil.rmtree(test_db_path)

if __name__ == "__main__":
    test_vector_store_isolation()
