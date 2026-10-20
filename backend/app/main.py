from fastapi import FastAPI

app = FastAPI(title="Meeting Intelligence System API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
