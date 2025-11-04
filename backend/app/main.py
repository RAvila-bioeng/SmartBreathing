from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import datetime, timedelta
import os

from .models import UserProfile, SensorReading, WorkoutRoutine, AIRecommendation, UserCreate
from .db import get_database
from .ai_engine import SmartBreathingAI

app = FastAPI(title="SmartBreathing API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

main_py_path = os.path.abspath(__file__)
backend_app_dir = os.path.dirname(main_py_path)
project_root = os.path.dirname(os.path.dirname(backend_app_dir))
frontend_dir = os.path.join(project_root, "frontend")

app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

ai_engine = SmartBreathingAI()

@app.get("/")
async def serve_frontend():
    index_path = os.path.join(frontend_dir, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)

@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}

# Endpoints de usuarios
@app.post("/api/users/", response_model=UserProfile)
async def create_user(user: UserProfile):
    db = get_database()
    result = db.users.insert_one(user.dict(by_alias=True))
    user.id = result.inserted_id
    return user

@app.get("/api/users/{telegram_id}", response_model=UserProfile)
async def get_user_by_telegram(telegram_id: int):
    db = get_database()
    user_data = db.users.find_one({"telegram_id": telegram_id})
    if not user_data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return UserProfile(**user_data)

@app.post("/api/users/create")
async def create_new_user(user: UserCreate):
    db = get_database()
    existing_user = db.users.find_one({"codigo": user.codigo})
    if existing_user:
        raise HTTPException(status_code=400, detail="El código de usuario ya existe.")

    new_user_data = user.dict()
    new_user_data["created_at"] = datetime.utcnow()
    new_user_data["updated_at"] = datetime.utcnow()

    result = db.users.insert_one(new_user_data)
    if not result.inserted_id:
        raise HTTPException(status_code=500, detail="No se pudo crear el usuario.")

    return {"status": "success", "message": "Usuario creado correctamente", "user_id": str(result.inserted_id)}


@app.get("/api/users/list")
async def list_users():
    db = get_database()
    usuarios = list(db.users.find())
    for usuario in usuarios:
        usuario["_id"] = str(usuario["_id"])
    return usuarios

# Endpoints de datos de sensores
@app.post("/api/sensors/reading", response_model=SensorReading)
async def create_sensor_reading(reading: SensorReading):
    db = get_database()
    result = db.sensor_readings.insert_one(reading.dict(by_alias=True))
    reading.id = result.inserted_id
    if reading.user_id:
        analysis = ai_engine.analyze_physiological_data(str(reading.user_id))
        if analysis.get("recommendations"):
            for rec in analysis["recommendations"]:
                recommendation = AIRecommendation(
                    user_id=reading.user_id,
                    recommendation_type=rec.get("type", "general"),
                    message=rec.get("message", "Revisar métricas"),
                    confidence_score=analysis.get("confidence_score", 0.5),
                    based_on_metrics={"analysis": analysis}
                )
                db.recommendations.insert_one(recommendation.dict(by_alias=True))
    return reading

@app.get("/api/sensors/readings/{user_id}", response_model=List[SensorReading])
async def get_user_readings(user_id: str, limit: int = 50):
    db = get_database()
    readings = list(db.sensor_readings.find(
        {"user_id": user_id},
        sort=[("timestamp", -1)],
        limit=limit
    ))
    return [SensorReading(**r) for r in readings]

@app.post("/api/routines/", response_model=WorkoutRoutine)
async def create_routine(routine: WorkoutRoutine):
    db = get_database()
    result = db.routines.insert_one(routine.dict(by_alias=True))
    routine.id = result.inserted_id
    return routine

@app.get("/api/routines/user/{user_id}", response_model=List[WorkoutRoutine])
async def get_user_routines(user_id: str):
    db = get_database()
    routines = list(db.routines.find({"user_id": user_id}))
    return [WorkoutRoutine(**r) for r in routines]

@app.get("/api/routine/current")
async def get_current_routine():
    return {
        "name": "Rutina de Respiración Inteligente",
        "duration": 30,
        "intensity": "Moderada",
        "nextExercise": "Respiración profunda - 5 min"
    }

@app.get("/api/analysis/{user_id}")
async def get_user_analysis(user_id: str):
    try:
        analysis = ai_engine.analyze_physiological_data(user_id)
        return analysis
    except Exception as e:
        return {"status": "error", "message": f"Error en análisis: {str(e)}"}

@app.post("/api/ai/generate-routine/{user_id}")
async def generate_ai_routine(user_id: str, goals: List[str] = None):
    try:
        db = get_database()
        user_data = db.users.find_one({"_id": user_id})
        if not user_data:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        user_profile = UserProfile(**user_data)
        goals = goals or ["general_fitness"]
        routine = ai_engine.create_personalized_routine(user_profile, goals)
        result = db.routines.insert_one(routine.dict(by_alias=True))
        routine.id = result.inserted_id
        return routine
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando rutina: {str(e)}")

@app.get("/api/recommendations/{user_id}", response_model=List[AIRecommendation])
async def get_user_recommendations(user_id: str, limit: int = 10):
    db = get_database()
    recommendations = list(db.recommendations.find(
        {"user_id": user_id},
        sort=[("created_at", -1)],
        limit=limit
    ))
    return [AIRecommendation(**r) for r in recommendations]






