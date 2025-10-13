from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from bson import ObjectId


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


class UserProfile(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    telegram_id: int
    name: str
    age: int
    weight: float
    gender: str  # "male", "female", "other"
    sport_preference: str
    fitness_level: str  # "beginner", "intermediate", "advanced"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class SensorReading(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    spo2: float  # Saturación de oxígeno (%)
    co2: float   # Nivel de CO2 (ppm)
    heart_rate: int  # Frecuencia cardíaca (bpm)
    ecg_data: Optional[List[float]] = None  # Datos de ECG si disponibles
    temperature: Optional[float] = None  # Temperatura corporal (°C)
    respiratory_rate: Optional[float] = None  # Frecuencia respiratoria (rpm)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class Exercise(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str
    description: str
    duration_minutes: int
    intensity: str  # "low", "moderate", "high"
    category: str  # "cardio", "strength", "flexibility", "breathing"
    target_muscles: List[str]
    instructions: List[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class WorkoutRoutine(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId
    name: str
    description: str
    exercises: List[dict]  # Lista de ejercicios con duración y orden
    total_duration: int  # Duración total en minutos
    difficulty: str  # "beginner", "intermediate", "advanced"
    target_goals: List[str]  # ["weight_loss", "muscle_gain", "endurance", etc.]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class AIRecommendation(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId
    recommendation_type: str  # "exercise", "rest", "intensity_adjustment", "warning"
    message: str
    confidence_score: float  # 0.0 to 1.0
    based_on_metrics: dict  # Qué métricas se usaron para la recomendación
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_applied: bool = False

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
