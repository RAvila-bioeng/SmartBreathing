from fastapi import APIRouter, HTTPException
from .db import get_database
from .models import ECGMeasurementIn
from bson import ObjectId
from pydantic import BaseModel
from datetime import datetime
import logging

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

class CurrentUserRequest(BaseModel):
    user_id: str

@router.post("/ecg/current-user")
async def set_current_ecg_user(request: CurrentUserRequest):
    """
    Sets the current user for ECG measurement.
    Called by frontend when user enters the measurement screen.
    """
    try:
        user_oid = ObjectId(request.user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user_id format")

    db = get_database()
    
    # Upsert document with _id="current" in ecg_state collection
    db.ecg_state.update_one(
        {"_id": "current"},
        {
            "$set": {
                "user_id": user_oid,
                "updated_at": datetime.utcnow()
            }
        },
        upsert=True
    )
    
    return {"status": "ok", "user_id": str(user_oid)}

@router.get("/ecg/current-user")
async def get_current_ecg_user():
    """
    Gets the current user selected for ECG measurement.
    Called by external MATLAB client.
    """
    db = get_database()
    
    state = db.ecg_state.find_one({"_id": "current"})
    
    if not state or "user_id" not in state:
        raise HTTPException(status_code=404, detail="ECG current user not set")
        
    return {"user_id": str(state["user_id"])}

@router.get("/ecg/latest/{user_id}")
async def get_latest_ecg(user_id: str):
    """
    Gets the latest ECG measurement for the given user.
    Returns the signal array, sampling frequency, and timestamp.
    """
    try:
        user_oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user_id format")

    db = get_database()
    
    # Find the most recent ECG document for this user
    ecg_doc = db.ecg.find_one(
        {"idUsuario": user_oid},
        sort=[("fecha", -1)]
    )
    
    if not ecg_doc:
        raise HTTPException(status_code=404, detail="No ECG data for this user")
        
    return {
        "user_id": str(ecg_doc["idUsuario"]),
        "fs": ecg_doc.get("fs", 200),
        "signal": ecg_doc.get("senal", []),
        "fecha": ecg_doc.get("fecha").isoformat() if ecg_doc.get("fecha") else None
    }

@router.post("/ecg-measurements")
async def create_ecg_measurement(measurement: ECGMeasurementIn):
    """
    Recibe una medición de ECG y BPM (aprox 5s) desde MATLAB/Simulink.
    Guarda los datos en DOS colecciones:
      1) 'ecg' -> Señal cruda (siempre inserta nuevo)
      2) 'Mediciones' -> BPM medio (actualiza el más reciente o inserta nuevo)
    """
    db = get_database()
    
    # 1. Preparar datos comunes
    try:
        user_oid = ObjectId(measurement.user_id)
    except Exception:
        # Asumimos que es válido según instrucciones
        user_oid = ObjectId(measurement.user_id)
        
    ts = measurement.timestamp

    # 2. Documento para colección 'ecg' (siempre inserta)
    ecg_doc = {
        "idUsuario": user_oid,
        "fecha": ts,
        "fs": measurement.fs,
        "senal": measurement.ecg_segment,
        "origen": "simulink"
    }
    res_ecg = db.ecg.insert_one(ecg_doc)
    ecg_id = str(res_ecg.inserted_id)

    # 3. Lógica para colección 'Mediciones' (Upsert logic manual)
    # Buscar el documento más reciente para este usuario
    latest_medicion = db.Mediciones.find_one(
        {"idUsuario": user_oid},
        sort=[("fecha", -1)]
    )

    if latest_medicion:
        # Actualizar existente
        medicion_id = str(latest_medicion["_id"])
        db.Mediciones.update_one(
            {"_id": latest_medicion["_id"]},
            {"$set": {"valores.bpm": measurement.bpm_mean}}
        )
        logger.info(f"Updated existing Medicion {medicion_id} with BPM: {measurement.bpm_mean}")
    else:
        # Crear nuevo
        medicion_doc = {
            "idUsuario": user_oid,
            "valores": {
                "bpm": measurement.bpm_mean
            },
            "fecha": ts,
            "quien_realizo": user_oid
        }
        res_med = db.Mediciones.insert_one(medicion_doc)
        medicion_id = str(res_med.inserted_id)
        logger.info(f"Created new Medicion {medicion_id} with BPM: {measurement.bpm_mean}")

    logger.info(f"ECG measurement processed. ECG ID: {ecg_id}, Medicion ID: {medicion_id}, User: {measurement.user_id}")
    
    return {
        "ecg_id": ecg_id,
        "medicion_id": medicion_id
    }
