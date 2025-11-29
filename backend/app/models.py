from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
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
    telegram_id: Optional[int] = None
    name: Optional[str] = None
    apellido: Optional[str] = None
    codigo: Optional[str] = None
    condiciones_limitantes: Optional[str] = None
    condicion_limitante_detalle: Optional[str] = None
    genero: Optional[str] = None
    edad: Optional[int] = None
    weight: Optional[float] = None
    sport_preference: Optional[str] = None
    fitness_level: Optional[str] = None
    objetivo_deportivo: Optional[str] = None
    grado_exigencia: Optional[str] = None
    frecuencia_entrenamiento: Optional[int] = None
    tiempo_dedicable_diario: Optional[int] = None
    equipamiento: Optional[str] = None
    sistema_recompensas: Optional[str] = None
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

    @field_validator('codigo')
    @classmethod
    def validate_codigo(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 4:
            raise ValueError('El código debe ser un PIN de 4 dígitos numéricos')
        return v

    condiciones_limitantes: str
    genero: str
    edad: int
    peso: float
    sport_preference: str
    fitness_level: str
    objetivo_deportivo: str
    grado_exigencia: str
    frecuencia_entrenamiento: int
    tiempo_dedicable_diario: int
    equipamiento: str
    sistema_recompensas: str

class SensorReading(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    spo2: float
    co2: float
    heart_rate: int
    ecg_data: Optional[List[float]] = None
    temperature: Optional[float] = None
    respiratory_rate: Optional[float] = None
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class Exercise(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str
    description: str
    duration_minutes: int
    intensity: str
    category: str
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
    exercises: List[dict]
    total_duration: int
    difficulty: str
    target_goals: List[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class AIRecommendation(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId
    recommendation_type: str
    message: str
    confidence_score: float
    based_on_metrics: dict
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_applied: bool = False
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class Medicion(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    idUsuario: str
    valores: Dict[str, Any]
    fecha: datetime = Field(default_factory=datetime.utcnow)
    quien_realizo: Optional[str] = None
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class ExerciseInRoutine(BaseModel):
    name: str
    description: str
    duration: int
    intensity: str
    id_ejercicio: Optional[str] = None

class RoutineResponse(BaseModel):
    name: str
    total_duration: int
    difficulty: str
    dias_semana: List[str]
    exercises: List[ExerciseInRoutine]

class RoutineRequest(BaseModel):
    goals: Optional[List[str]] = None
