from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from bson import ObjectId
from pydantic_core import core_schema

class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: Any
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            python_schema=core_schema.with_info_plain_validator_function(cls.validate),
            json_schema=core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(lambda x: str(x)),
        )

    @classmethod
    def validate(cls, v: Any, *args, **kwargs) -> ObjectId:
        if ObjectId.is_valid(v):
            return ObjectId(v)
        raise ValueError("Invalid ObjectId")

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
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class UserCreate(BaseModel):
    nombre: str
    apellido: str
    codigo: str
    condiciones_limitantes: str
    edad: int
    peso: float
    sport_preference: str
    fitness_level: str
    objetivo_deportivo: str
    grado_exigencia: str
    frecuencia_entrenamiento: int
    tiempo_dedicable_diario: int
    equipamiento: str
    sistema_recompensas: str  # <-- campo añadido

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
        populate_by_name = True
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
        populate_by_name = True
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
        populate_by_name = True
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
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# NUEVO MODELO PARA "Mediciones"
class Medicion(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    idUsuario: str
    valores: Dict[str, Any]  # Diccionario tipo {"peso":67, "spo2":99, "grasa_porc":14, ...}
    fecha: datetime = Field(default_factory=datetime.utcnow)
    quien_realizo: Optional[str] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


