"""Modal deployment entrypoint for the Rebutio FastAPI backend."""

import modal


app = modal.App("rebutio-backend")

backend_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_pyproject("backend/pyproject.toml")
    .add_local_dir("backend/app", remote_path="/root/backend/app", copy=True)
)

backend_secret = modal.Secret.from_name("rebutio-backend")


@app.function(
    image=backend_image,
    secrets=[backend_secret],
    cpu=1.0,
    memory=1024,
    min_containers=0,
    max_containers=20,
    scaledown_window=300,
    timeout=300,
)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def fastapi_app():
    from backend.app.main import app as web_app

    return web_app
