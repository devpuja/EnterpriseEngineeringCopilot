from pathlib import Path
import shutil

def delete_pycache(root_dir="."):
    """
    Recursively find and delete all __pycache__ directories.
    """
    root = Path(root_dir)

    for pycache_dir in root.rglob("__pycache__"):
        if pycache_dir.is_dir():
            try:
                shutil.rmtree(pycache_dir)
                print(f"Deleted: {pycache_dir}")
            except Exception as e:
                print(f"Failed to delete {pycache_dir}: {e}")

if __name__ == "__main__":
    delete_pycache()