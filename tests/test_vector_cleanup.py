import shutil
import os
import sys
import time
import json
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.memory.vector_store import VectorStore

def test_cleanup_logic():
    print("Testing Vector Store Cleanup Logic...")
    
    # Setup test DB path
    test_db_path = ".test_cleanup_db"
    if os.path.exists(test_db_path):
        shutil.rmtree(test_db_path)
        
    try:
        store = VectorStore(persist_path=test_db_path)
        
        # Add data for Repo A (Active)
        print("Adding data for Repo A...")
        store.add_document(
            text="Repo A data",
            metadata={"repo_id": "owner/repo-a", "type": "code"}
        )
        
        # Add data for Repo B (Inactive)
        print("Adding data for Repo B...")
        store.add_document(
            text="Repo B data",
            metadata={"repo_id": "owner/repo-b", "type": "code"}
        )
        
        # Manually manipulate activity file to make Repo B old
        activity_file = Path(test_db_path) / "repo_activity.json"
        with open(activity_file, "r") as f:
            activity = json.load(f)
            
        # Set Repo B to be 25 hours old
        activity["owner/repo-b"] = time.time() - (25 * 3600)
        # Set Repo A to be 1 hour old
        activity["owner/repo-a"] = time.time() - (1 * 3600)
        
        with open(activity_file, "w") as f:
            json.dump(activity, f)
            
        print("Simulated time passed. Running cleanup (retention=24h)...")
        cleaned = store.cleanup_inactive_repos(retention_hours=24)
        print(f"Cleaned {cleaned} repos")
        
        # Verify Repo A still exists
        results_a = store.search("data", repo_id="owner/repo-a")
        assert len(results_a) > 0, "Repo A should still exist"
        print("✅ Repo A preserved")
        
        # Verify Repo B is gone
        results_b = store.search("data", repo_id="owner/repo-b")
        assert len(results_b) == 0, "Repo B should be deleted"
        print("✅ Repo B deleted")
        
    finally:
        # Cleanup
        if os.path.exists(test_db_path):
            shutil.rmtree(test_db_path)

if __name__ == "__main__":
    test_cleanup_logic()
