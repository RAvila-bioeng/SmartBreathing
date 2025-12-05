from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import datetime
import os
import sys
import subprocess
from bson import ObjectId
import logging

from .models import (
    UserProfile,
    SensorReading,
    WorkoutRoutine,
    AIRecommendation,
    UserCreate,
    RoutineResponse,
    RoutineRequest,
    ExerciseInRoutine,
)
from .db import get_database
from .ai_engine import SmartBreathingAI
from . import ecg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Register routers
app.include_router(ecg.router, prefix="/api", tags=["ecg"])


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


@app.post("/api/users/check_duplicate")
async def check_duplicate_user(datos: dict = Body(...)):
    db = get_database()
    nombre = datos.get("nombre", "").strip()
    apellido = datos.get("apellido", "").strip()
    codigo = datos.get("codigo", "").strip()

    usuario = db.users.find_one(
        {
            "nombre": {"$regex": f"^{nombre}$", "$options": "i"},
            "apellido": {"$regex": f"^{apellido}$", "$options": "i"},
            "codigo": codigo,
        }
    )

    if usuario:
        return {"exists": True}
    return {"exists": False}


@app.post("/api/users/create")
async def create_new_user(user: UserCreate):
    db = get_database()
    # Se elimina la comprobación de unicidad del código
    new_user_data = user.dict()
    # Se mantiene 'peso' en new_user_data para guardarlo también en la colección users
    new_user_data["created_at"] = datetime.utcnow()
    new_user_data["updated_at"] = datetime.utcnow()
    if "genero" not in new_user_data or not new_user_data["genero"]:
        raise HTTPException(
            status_code=400, detail="El campo 'genero' es obligatorio."
        )
    result = db.users.insert_one(new_user_data)
    if not result.inserted_id:
        raise HTTPException(
            status_code=500, detail="No se pudo crear el usuario."
        )
    return {
        "status": "success",
        "message": "Usuario creado correctamente",
        "user_id": str(result.inserted_id),
    }


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
        raise HTTPException(
            status_code=500, detail=f"Error al obtener usuario: {str(e)}"
        )


# --- CO2 SESSION DATA ---
@app.get("/api/co2/last-session/{user_id}")
async def get_last_co2_session(user_id: str):
    db = get_database()
    try:
        # Try to find user by string id or ObjectId
        query = {"idUsuario": user_id}
        # Ideally we should match the format stored. 
        # In ingestion/read_co2_scd30.py, it attempts to store ObjectId if possible, else string.
        # We can try both.
        
        # Check if there is any doc with string id
        doc = db.co2.find_one({"idUsuario": user_id}, sort=[("fecha", -1)])
        
        if not doc:
            # Try ObjectId
            try:
                oid = ObjectId(user_id)
                doc = db.co2.find_one({"idUsuario": oid}, sort=[("fecha", -1)])
            except Exception:
                pass
        
        if not doc:
            # Return empty structure or 404? 
            # Frontend expects JSON to plot. returning 404 might be easier to handle "No data".
            raise HTTPException(status_code=404, detail="No CO2 session found")

        # Convert doc to JSON-safe
        doc["_id"] = str(doc["_id"])
        doc["idUsuario"] = str(doc["idUsuario"])
        if "fecha" in doc and isinstance(doc["fecha"], datetime):
             doc["fecha"] = doc["fecha"].isoformat()

        # Ensure indices_estabilizados is present (null if missing in legacy data)
        if "indices_estabilizados" not in doc:
             doc["indices_estabilizados"] = None

        return doc

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching CO2 session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(
            status_code=400,
            detail="Faltan campos obligatorios (idUsuario, valores diccionario)",
        )

    try:
        obj_idUsuario = ObjectId(idUsuario)
    except Exception:
        raise HTTPException(
            status_code=400, detail="Formato de idUsuario incorrecto"
        )

    existing = db.Mediciones.find_one({"idUsuario": obj_idUsuario})

    if existing:
        # Prevent overwriting CO2/Humidity fields from automated ingestion
        forbidden_keys = [f"co2_{i}" for i in range(1, 6)] + [f"hum_{i}" for i in range(1, 6)]
        for k in forbidden_keys:
            nuevos_valores.pop(k, None)

        dict_actual = existing.get("valores", {})
        dict_actual.update(nuevos_valores)
        db.Mediciones.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "valores": dict_actual,
                    "fecha": fecha,
                    "quien_realizo": quien_realizo,
                }
            },
        )
        resultado = db.Mediciones.find_one({"_id": existing["_id"]})
        resultado["_id"] = str(resultado["_id"])
        if "idUsuario" in resultado:
            resultado["idUsuario"] = str(resultado["idUsuario"])
        if "quien_realizo" in resultado and isinstance(
            resultado["quien_realizo"], ObjectId
        ):
            resultado["quien_realizo"] = str(resultado["quien_realizo"])
        return resultado
    else:
        medicion = {
            "idUsuario": obj_idUsuario,
            "valores": nuevos_valores,
            "fecha": fecha,
            "quien_realizo": obj_idUsuario,
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
    mediciones = list(
        db.Mediciones.find(
            {"idUsuario": obj_user_id}, sort=[("fecha", -1)], limit=limit
        )
    )
    for m in mediciones:
        m["_id"] = str(m["_id"])
        if "idUsuario" in m:
            m["idUsuario"] = str(m["idUsuario"])
        if "quien_realizo" in m and isinstance(
            m["quien_realizo"], ObjectId
        ):
            m["quien_realizo"] = str(m["quien_realizo"])
    return mediciones


# -------------- LOGIN --------------
@app.post("/api/check_user")
async def check_user(datos: dict = Body(...)):
    db = get_database()
    nombre = datos.get("nombre", "").strip()
    apellido = datos.get("apellido", "").strip()
    codigo = datos.get("codigo", "").strip()
    usuario = db.users.find_one(
        {
            "nombre": {"$regex": f"^{nombre}$", "$options": "i"},
            "apellido": {"$regex": f"^{apellido}$", "$options": "i"},
            "codigo": codigo,
        }
    )
    if not usuario:
        raise HTTPException(
            status_code=404, detail="Usuario no existente, regístrese"
        )
    
    # Start CO2 measurement session in background
    try:
        user_id_str = str(usuario["_id"])
        ingestion_script = os.path.join(project_root, "ingestion", "read_co2_scd30.py")
        
        # Ensure the script exists before trying to run it
        if os.path.exists(ingestion_script):
            logger.info(f"Starting CO2 session for user {user_id_str}")
            cmd = [sys.executable, ingestion_script, "--user-id", user_id_str, "--session"]
            logger.info(f"Launching CO2 session command: {cmd}")
            subprocess.Popen(
                cmd,
                stdout=None,   # hereda stdout/stderr → veo logs en la consola
                stderr=None,
                start_new_session=True
            )
        else:
            logger.error(f"Ingestion script not found at {ingestion_script}")
    except Exception as e:
        logger.error(f"Failed to start CO2 session: {e}")

    return {"user_id": str(usuario["_id"])}


# -------------- AI ROUTINE --------------
@app.post(
    "/api/ai/alternative-exercise/{user_id}", response_model=Optional[ExerciseInRoutine]
)
async def get_alternative_exercise_endpoint(
    user_id: str,
    raw_request: Request,
    request: dict = Body(...), # expects {"exercise_id": "..."}
):
    """
    Returns an alternative exercise for a given exercise ID, matching properties.
    """
    try:
        exercise_id = request.get("exercise_id")
        if not exercise_id:
            raise HTTPException(status_code=400, detail="Missing exercise_id")

        # 1. Fetch User
        db = get_database()
        try:
            obj_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid user_id format")

        user_doc = db.users.find_one({"_id": obj_id})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")

        user_profile = UserProfile(**user_doc)

        # 2. Get Alternative
        alt_exercise = ai_engine.get_alternative_exercise(user_profile, exercise_id)
        
        if not alt_exercise:
            # Fallback or just 404/Null? Let's return null/none to indicate no alternative found
            # But client might expect JSON. 
            # Returning 404 might be handled as error. 
            # Returning None (200 OK with null body) is often safer for logic.
            return None

        return alt_exercise

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alternative exercise: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/ai/generate-routine/{user_id}", response_model=RoutineResponse
)
async def generate_routine_endpoint(
    user_id: str,
    raw_request: Request,
    request: RoutineRequest | None = Body(None),
):
    """
    Genera una rutina para un usuario dado.
    - Usa goals del body si vienen, si no, por defecto ["mixto"].
    - NUNCA devuelve 422 solo porque no haya ejercicios exactos:
      en ese caso intenta un fallback con ["mixto"] y, si sigue sin haber nada,
      lanza un 500 con mensaje claro.
    """
    try:
        # Debug del body crudo para ver exactamente qué llega
        body_bytes = await raw_request.body()
        logger.info(
            "DEBUG generate-routine raw body: %s",
            body_bytes.decode("utf-8") if body_bytes else "<empty>",
        )

        goals = request.goals if request and request.goals else ["mixto"]
        logger.info("generate-routine goals: %s", goals)

        # 1. Fetch User
        db = get_database()
        try:
            obj_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=400, detail="Invalid user_id format"
            )

        user_doc = db.users.find_one({"_id": obj_id})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")

        user_profile = UserProfile(**user_doc)

        # 2. Intento principal: goals tal cual vienen
        try:
            routine = ai_engine.generate_routine_from_db(
                user_profile, goals
            )
        except Exception as e_gen:
            logger.error(
                "Error generating routine from DB (goals=%s): %s",
                goals,
                str(e_gen),
                exc_info=True,
            )
            routine = None

        # 3. Si no hay ejercicios, intentamos fallback con ["mixto"]
        if not routine or not getattr(routine, "exercises", None):
            if goals != ["mixto"]:
                logger.warning(
                    "No exercises found with goals=%s, trying fallback ['mixto']",
                    goals,
                )
                try:
                    fallback_routine = ai_engine.generate_routine_from_db(
                        user_profile, ["mixto"]
                    )
                    if fallback_routine and getattr(
                        fallback_routine, "exercises", None
                    ):
                        routine = fallback_routine
                except Exception as e_fallback:
                    logger.error(
                        "Error generating fallback routine (['mixto']): %s",
                        str(e_fallback),
                        exc_info=True,
                    )

        # 4. Si aun así no hay ejercicios, esto ya es un problema interno
        if not routine or not getattr(routine, "exercises", None):
            logger.error(
                "No exercises available even after fallback for user %s",
                user_id,
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    "No hay ejercicios disponibles en la base de datos "
                    "para generar una rutina con los filtros actuales."
                ),
            )

        return routine

    except HTTPException:
        # Re-lanzamos HTTPException tal cual
        raise
    except Exception as e:
        logger.error(
            "Error in generate_routine_endpoint: %s", str(e), exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Internal error: {str(e)}"
        )
