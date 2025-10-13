from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import List, Optional
from datetime import datetime, timedelta
import os

from .models import UserProfile, SensorReading, WorkoutRoutine, AIRecommendation
from .db import get_database
from .ai_engine import SmartBreathingAI

app = FastAPI(title="SmartBreathing API", version="0.1.0")

# Montar archivos estáticos para el frontend
app.mount("/static", StaticFiles(directory="../frontend"), name="static")

# Inicializar AI engine
ai_engine = SmartBreathingAI()

@app.get("/")
async def serve_frontend():
    """Sirve el frontend principal"""
    return FileResponse("../frontend/index.html")

@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}

# Endpoints de usuarios
@app.post("/api/users/", response_model=UserProfile)
async def create_user(user: UserProfile):
    """Crear un nuevo perfil de usuario"""
    db = get_database()
    result = db.users.insert_one(user.dict(by_alias=True))
    user.id = result.inserted_id
    return user

@app.get("/api/users/{telegram_id}", response_model=UserProfile)
async def get_user_by_telegram(telegram_id: int):
    """Obtener usuario por ID de Telegram"""
    db = get_database()
    user_data = db.users.find_one({"telegram_id": telegram_id})
    if not user_data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return UserProfile(**user_data)

# Endpoints de datos de sensores
@app.post("/api/sensors/reading", response_model=SensorReading)
async def create_sensor_reading(reading: SensorReading):
    """Crear una nueva lectura de sensor"""
    db = get_database()
    result = db.sensor_readings.insert_one(reading.dict(by_alias=True))
    reading.id = result.inserted_id
    
    # Generar recomendación automática
    recent_readings = list(db.sensor_readings.find(
        {"user_id": reading.user_id},
        sort=[("timestamp", -1)],
        limit=10
    ))
    recent_readings = [SensorReading(**r) for r in recent_readings]
    
    if len(recent_readings) >= 3:  # Mínimo 3 lecturas para análisis
        analysis = ai_engine.analyze_physiological_data(str(reading.user_id), recent_readings)
        recommendation = ai_engine.generate_recommendation(str(reading.user_id), analysis)
        
        # Guardar recomendación
        db.recommendations.insert_one(recommendation.dict(by_alias=True))
    
    return reading

@app.get("/api/sensors/readings/{user_id}", response_model=List[SensorReading])
async def get_user_readings(user_id: str, limit: int = 50):
    """Obtener lecturas recientes de un usuario"""
    db = get_database()
    readings = list(db.sensor_readings.find(
        {"user_id": user_id},
        sort=[("timestamp", -1)],
        limit=limit
    ))
    return [SensorReading(**r) for r in readings]

# Endpoints de rutinas
@app.post("/api/routines/", response_model=WorkoutRoutine)
async def create_routine(routine: WorkoutRoutine):
    """Crear una nueva rutina de ejercicio"""
    db = get_database()
    result = db.routines.insert_one(routine.dict(by_alias=True))
    routine.id = result.inserted_id
    return routine

@app.get("/api/routines/user/{user_id}", response_model=List[WorkoutRoutine])
async def get_user_routines(user_id: str):
    """Obtener rutinas de un usuario"""
    db = get_database()
    routines = list(db.routines.find({"user_id": user_id}))
    return [WorkoutRoutine(**r) for r in routines]

@app.get("/api/routine/current")
async def get_current_routine():
    """Obtener rutina actual (para el frontend)"""
    # Por ahora retorna una rutina de ejemplo
    return {
        "name": "Rutina de Respiración Inteligente",
        "duration": 30,
        "intensity": "Moderada",
        "nextExercise": "Respiración profunda - 5 min"
    }

# Endpoints de análisis y recomendaciones
@app.get("/api/analysis/{user_id}")
async def get_user_analysis(user_id: str):
    """Obtener análisis fisiológico del usuario"""
    db = get_database()
    
    # Obtener lecturas recientes (últimas 2 horas)
    since = datetime.utcnow() - timedelta(hours=2)
    recent_readings = list(db.sensor_readings.find(
        {"user_id": user_id, "timestamp": {"$gte": since}},
        sort=[("timestamp", -1)],
        limit=100
    ))
    recent_readings = [SensorReading(**r) for r in recent_readings]
    
    if not recent_readings:
        return {"status": "no_data", "message": "No hay datos recientes"}
    
    analysis = ai_engine.analyze_physiological_data(user_id, recent_readings)
    return analysis

@app.get("/api/recommendations/{user_id}", response_model=List[AIRecommendation])
async def get_user_recommendations(user_id: str, limit: int = 10):
    """Obtener recomendaciones recientes del usuario"""
    db = get_database()
    recommendations = list(db.recommendations.find(
        {"user_id": user_id},
        sort=[("created_at", -1)],
        limit=limit
    ))
    return [AIRecommendation(**r) for r in recommendations]


