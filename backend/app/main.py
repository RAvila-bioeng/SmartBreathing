from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from datetime import datetime
import os
from bson import ObjectId

from .models import UserProfile, SensorReading, WorkoutRoutine, AIRecommendation, UserCreate, RoutineResponse
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

# HTML Frontend
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
    # Se elimina la comprobación de unicidad del código
    new_user_data = user.dict()
    new_user_data.pop("peso", None)  # El peso se guarda en Mediciones, no aquí
    new_user_data["created_at"] = datetime.utcnow()
    new_user_data["updated_at"] = datetime.utcnow()
    if "genero" not in new_user_data or not new_user_data["genero"]:
        raise HTTPException(status_code=400, detail="El campo 'genero' es obligatorio.")
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

# --- MEDICIONES ---
@app.post("/api/mediciones")
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
        dict_actual.update(nuevos_valores)
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

@app.get("/api/mediciones")
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

# -------------- LOGIN --------------
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

# -------------- AI ROUTINE --------------
@app.post("/api/ai/generate-routine/{user_id}", response_model=RoutineResponse)
async def generate_routine_endpoint(user_id: str, goals: List[str] = Body(...)):
    # 1. Fetch User
    db = get_database()
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid user_id format")
    
    user_doc = db.users.find_one({"_id": obj_id})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_profile = UserProfile(**user_doc)
    
    # 2. Call AI Engine
    try:
        routine = ai_engine.generate_routine_from_db(user_profile, goals)
    except Exception as e:
        # Log error in production
        raise HTTPException(status_code=500, detail=f"Internal error generating routine: {str(e)}")
    
    # 3. Check if empty (should only happen if 422 desired)
    if not routine or not routine.exercises:
         raise HTTPException(status_code=422, detail="No suitable exercises found for this profile and constraints")
         
    return routine
