from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from datetime import datetime
import os
from bson import ObjectId

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

# SIRVE ARCHIVOS ESTÁTICOS (CSS, JS, imágenes...) DESDE /static
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# RUTAS PARA CADA HTML DEL FRONTEND
@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open(os.path.join(frontend_dir, "menu.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/menu.html", response_class=HTMLResponse)
async def read_menu():
    with open(os.path.join(frontend_dir, "menu.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/login.html", response_class=HTMLResponse)
async def read_login():
    with open(os.path.join(frontend_dir, "login.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/index.html", response_class=HTMLResponse)
async def read_index():
    with open(os.path.join(frontend_dir, "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/nuevo_usuario_paso1.html", response_class=HTMLResponse)
async def read_nuevo_usuario_paso1():
    with open(os.path.join(frontend_dir, "nuevo_usuario_paso1.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/nuevo_usuario_paso2.html", response_class=HTMLResponse)
async def read_nuevo_usuario_paso2():
    with open(os.path.join(frontend_dir, "nuevo_usuario_paso2.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# ========== Resto de tu API tal y como la tienes ==========

ai_engine = SmartBreathingAI()

@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}

# --- USERS ---
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
    user_data["_id"] = str(user_data["_id"])
    return user_data

@app.post("/api/users/create")
async def create_new_user(user: UserCreate):
    db = get_database()
    existing_user = db.users.find_one({"codigo": user.codigo})
    if existing_user:
        raise HTTPException(status_code=400, detail="El código de usuario ya existe.")
    new_user_data = user.dict()
    new_user_data.pop("peso", None)
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

@app.get("/api/users/by_id/{user_id}")
async def get_user_by_id(user_id: str):
    try:
        db = get_database()
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        user["_id"] = str(user["_id"])
        return user
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener usuario: {str(e)}")

# --- SENSORS ---
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

@app.get("/api/mediciones")
async def get_mediciones(user_id: str, limit: int = 50):
    try:
        db = get_database()
        readings = list(db.sensor_readings.find(
            {"user_id": user_id},
            sort=[("timestamp", -1)],
            limit=limit
        ))
        mediciones = []
        for r in readings:
            medicion = {
                "spo2": r.get("spo2"),
                "co2": r.get("co2"),
                "hr": r.get("hr"),
                "grasa_porc": r.get("grasa_porc"),
                "timestamp": r.get("timestamp")
            }
            mediciones.append(medicion)
        return mediciones
    except Exception:
        return []

# --- MEDICIONES: ObjectId + LOGS ---
@app.post("/api/Mediciones")
async def create_or_update_medicion(request: Request):
    db = get_database()
    data = await request.json()

    idUsuario = data.get("idUsuario")
    nuevos_valores = data.get("valores", {})
    fecha = data.get("fecha", datetime.utcnow().isoformat())
    quien_realizo = data.get("quien_realizo", idUsuario)

    if not idUsuario or not isinstance(nuevos_valores, dict):
        raise HTTPException(status_code=400, detail="Faltan campos obligatorios (idUsuario, valores diccionario)")

    try:
        obj_idUsuario = ObjectId(idUsuario)
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de idUsuario incorrecto")

    existing = db.Mediciones.find_one({"idUsuario": obj_idUsuario})

    if existing:
        dict_actual = existing.get("valores", {})

        # LOGS DE DEPURACIÓN
        print(">>> BACKEND - idUsuario:", obj_idUsuario)
        print(">>> BACKEND - valores que había antes:", dict_actual)
        print(">>> BACKEND - valores que llegan en el POST:", nuevos_valores)

        dict_actual.update(nuevos_valores)

        print(">>> BACKEND - valores que se van a guardar:", dict_actual)

        db.Mediciones.update_one(
            {"_id": existing["_id"]},
            {"$set": {"valores": dict_actual, "fecha": fecha, "quien_realizo": quien_realizo}}
        )
        resultado = db.Mediciones.find_one({"_id": existing["_id"]})
        resultado["_id"] = str(resultado["_id"])
        if "idUsuario" in resultado:
            resultado["idUsuario"] = str(resultado["idUsuario"])
        if "quien_realizo" in resultado and isinstance(resultado["quien_realizo"], ObjectId):
            resultado["quien_realizo"] = str(resultado["quien_realizo"])
        return resultado
    else:
        medicion = {
            "idUsuario": obj_idUsuario,
            "valores": nuevos_valores,
            "fecha": fecha,
            "quien_realizo": obj_idUsuario
        }
        result = db.Mediciones.insert_one(medicion)
        medicion["_id"] = str(result.inserted_id)
        medicion["idUsuario"] = str(medicion["idUsuario"])
        if isinstance(medicion.get("quien_realizo"), ObjectId):
            medicion["quien_realizo"] = str(medicion["quien_realizo"])
        return medicion

@app.get("/api/Mediciones")
async def get_all_mediciones(user_id: str, limit: int = 100):
    db = get_database()
    try:
        obj_user_id = ObjectId(user_id)
    except Exception:
        return []
    mediciones = list(db.Mediciones.find(
        {"idUsuario": obj_user_id},
        sort=[("fecha", -1)],
        limit=limit
    ))
    for m in mediciones:
        m["_id"] = str(m["_id"])
        if "idUsuario" in m:
            m["idUsuario"] = str(m["idUsuario"])
        if "quien_realizo" in m and isinstance(m["quien_realizo"], ObjectId):
            m["quien_realizo"] = str(m["quien_realizo"])
    return mediciones

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
        # IMPORTANTE: si user_id es un _id de Mongo, conviértelo a ObjectId
        try:
            obj_user_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(status_code=400, detail="user_id inválido")

        user_data = db.users.find_one({"_id": obj_user_id})
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

# ----------------- LOGIN -----------------
@app.post("/api/check_user")
async def check_user(datos: dict = Body(...)):
    db = get_database()
    nombre = datos.get("nombre", "").strip()
    apellido = datos.get("apellido", "").strip()
    codigo = datos.get("codigo", "").strip()
    usuario = db.users.find_one({
        "nombre": {"$regex": f"^{nombre}$", "$options": "i"},
        "apellido": {"$regex": f"^{apellido}$", "$options": "i"},
        "codigo": codigo
    })
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no existente, regístrese")
    return {"user_id": str(usuario["_id"])}

















