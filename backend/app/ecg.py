from fastapi import APIRouter
from .db import get_database
from .models import ECGMeasurementIn
import logging

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/ecg-measurements")
async def create_ecg_measurement(measurement: ECGMeasurementIn):
    """
    Recibe una medición de ECG y BPM (aprox 5s) desde MATLAB/Simulink.
    Guarda los datos en la colección 'ecg_measurements'.
    """
    db = get_database()

    # Convert Pydantic model to dict
    data = measurement.dict()

    # Insert into database
    result = db.ecg_measurements.insert_one(data)

    inserted_id = str(result.inserted_id)
    logger.info(f"Received ECG measurement for user {measurement.user_id}, saved with ID: {inserted_id}")

    return {"inserted_id": inserted_id}
