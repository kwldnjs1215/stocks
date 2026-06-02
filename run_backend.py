import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=int(os.environ.get("BACKEND_PORT", "8001")),
        reload=True,
        reload_dirs=["."],
        reload_includes=["*.py"],
        reload_excludes=[
            ".venv/*",
            "frontend/*",
            "data/*",
            "*.log",
            "__pycache__/*",
        ],
    )
