#!/usr/bin/env python3
"""Quick-start script — runs the backend in development mode."""

import uvicorn
import pathlib

HERE = pathlib.Path(__file__).parent.resolve()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(HERE)],
    )
