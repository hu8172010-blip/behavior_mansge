from fastapi import APIRouter

from app.api.v1.endpoints import alerts, auth, backups, behaviors, dashboard, devices, health, lab, logs, meta, persons, system, tracks, workorders, ws

api_router = APIRouter()
api_router.include_router(health.router, prefix="/system", tags=["system"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(workorders.router, prefix="/workorders", tags=["workorders"])
api_router.include_router(behaviors.router, prefix="/behaviors", tags=["behaviors"])
api_router.include_router(tracks.router, prefix="/tracks", tags=["tracks"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(persons.router, prefix="/persons", tags=["persons"])
api_router.include_router(logs.router, prefix="/logs", tags=["logs"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(ws.router, prefix="/ws", tags=["ws"])
api_router.include_router(lab.router, prefix="/lab", tags=["lab"])
api_router.include_router(backups.router, prefix="/backups", tags=["backups"])
