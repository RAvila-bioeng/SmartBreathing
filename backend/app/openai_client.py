import os
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import openai
from openai import OpenAI
from .db import get_database
from .models import SensorReading, UserProfile


class SmartBreathingOpenAI:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.db = get_database()
        
    def analyze_user_physiology(self, user_id: str, time_window_hours: int = 2) -> Dict:
        """
        Analiza los datos fisiológicos de un usuario usando ChatGPT
        """
        # Obtener datos del usuario
        user_data = self._get_user_data(user_id, time_window_hours)
        
        if not user_data["readings"]:
            return {
                "status": "no_data",
                "message": "No hay datos suficientes para análisis",
                "recommendations": []
            }
        
        # Crear prompt contextual
        prompt = self._create_analysis_prompt(user_data)
        
        try:
            # Llamar a ChatGPT
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": """Eres un experto fisiólogo deportivo y entrenador personal especializado en análisis de datos de sensores biomédicos. 
                        Tu trabajo es analizar datos fisiológicos en tiempo real y proporcionar recomendaciones precisas y seguras para atletas.
                        
                        IMPORTANTE: 
                        - Si detectas valores peligrosos (SpO2 < 90%, FC > 200 bpm, CO2 > 1000 ppm), recomienda detener el ejercicio inmediatamente
                        - Siempre prioriza la seguridad del usuario
                        - Proporciona recomendaciones específicas y accionables
                        - Considera el contexto del usuario (nivel de fitness, deporte, etc.)
                        """
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Respuestas más consistentes
                max_tokens=1000
            )
            
            # Parsear respuesta
            analysis_result = self._parse_chatgpt_response(response.choices[0].message.content)
            
            # Guardar análisis en la base de datos
            self._save_analysis(user_id, analysis_result, user_data)
            
            return analysis_result
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error en análisis de IA: {str(e)}",
                "recommendations": []
            }
    
    def generate_workout_recommendation(self, user_id: str, current_routine: Optional[Dict] = None) -> Dict:
        """
        Genera recomendaciones de entrenamiento personalizadas usando ChatGPT
        """
        user_data = self._get_user_data(user_id, 24)  # Últimas 24 horas
        
        prompt = self._create_workout_prompt(user_data, current_routine)
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": """Eres un entrenador personal experto que crea rutinas de ejercicio personalizadas basadas en datos fisiológicos reales.
                        Debes considerar:
                        - El perfil del usuario (edad, peso, nivel de fitness, deporte preferido)
                        - Los datos fisiológicos recientes (SpO2, CO2, frecuencia cardíaca)
                        - Las tendencias y patrones en los datos
                        - Los objetivos de fitness del usuario
                        
                        Proporciona rutinas específicas, seguras y progresivas.
                        """
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.4,
                max_tokens=1200
            )
            
            recommendation = self._parse_workout_response(response.choices[0].message.content)
            
            # Guardar recomendación
            self._save_workout_recommendation(user_id, recommendation)
            
            return recommendation
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error generando recomendación: {str(e)}",
                "routine": None
            }
    
    def _get_user_data(self, user_id: str, time_window_hours: int) -> Dict:
        """Obtiene datos del usuario desde MongoDB"""
        # Obtener perfil del usuario
        user_profile = self.db.users.find_one({"_id": user_id})
        
        # Obtener lecturas recientes
        since = datetime.utcnow() - timedelta(hours=time_window_hours)
        readings = list(self.db.sensor_readings.find(
            {"user_id": user_id, "timestamp": {"$gte": since}},
            sort=[("timestamp", -1)],
            limit=100
        ))
        
        # Obtener rutinas del usuario
        routines = list(self.db.routines.find(
            {"user_id": user_id, "is_active": True},
            sort=[("created_at", -1)],
            limit=5
        ))
        
        # Obtener recomendaciones recientes
        recent_recommendations = list(self.db.recommendations.find(
            {"user_id": user_id},
            sort=[("created_at", -1)],
            limit=10
        ))
        
        return {
            "user_profile": user_profile,
            "readings": readings,
            "routines": routines,
            "recent_recommendations": recent_recommendations,
            "time_window_hours": time_window_hours
        }
    
    def _create_analysis_prompt(self, user_data: Dict) -> str:
        """Crea un prompt contextual para análisis fisiológico"""
        user = user_data["user_profile"]
        readings = user_data["readings"]
        
        if not user or not readings:
            return "No hay datos suficientes para análisis."
        
        # Preparar datos de sensores
        sensor_data = []
        for reading in readings[:20]:  # Últimas 20 lecturas
            sensor_data.append({
                "timestamp": reading["timestamp"].isoformat(),
                "spo2": reading["spo2"],
                "co2": reading["co2"],
                "heart_rate": reading["heart_rate"],
                "respiratory_rate": reading.get("respiratory_rate"),
                "temperature": reading.get("temperature")
            })
        
        prompt = f"""
        Analiza los siguientes datos fisiológicos de un atleta:

        PERFIL DEL USUARIO:
        - Nombre: {user.get('name', 'N/A')}
        - Edad: {user.get('age', 'N/A')} años
        - Peso: {user.get('weight', 'N/A')} kg
        - Género: {user.get('gender', 'N/A')}
        - Deporte preferido: {user.get('sport_preference', 'N/A')}
        - Nivel de fitness: {user.get('fitness_level', 'N/A')}

        DATOS DE SENSORES (últimas {len(sensor_data)} lecturas):
        {json.dumps(sensor_data, indent=2, default=str)}

        Por favor proporciona:
        1. ANÁLISIS GENERAL: Resumen del estado fisiológico actual
        2. ALERTAS: Cualquier valor preocupante o peligroso
        3. TENDENCIAS: Patrones observados en los datos
        4. RECOMENDACIONES: Acciones específicas a tomar
        5. PRÓXIMOS PASOS: Qué hacer en la siguiente sesión

        Responde en formato JSON con esta estructura:
        {{
            "analysis_summary": "Resumen del análisis",
            "alerts": ["Lista de alertas si las hay"],
            "trends": ["Tendencias observadas"],
            "recommendations": [
                {{
                    "type": "exercise|rest|warning|medical",
                    "priority": "high|medium|low",
                    "message": "Mensaje específico",
                    "action": "Acción recomendada"
                }}
            ],
            "next_steps": "Qué hacer a continuación",
            "confidence_score": 0.85
        }}
        """
        
        return prompt
    
    def _create_workout_prompt(self, user_data: Dict, current_routine: Optional[Dict]) -> str:
        """Crea un prompt para recomendaciones de entrenamiento"""
        user = user_data["user_profile"]
        readings = user_data["readings"]
        
        # Calcular estadísticas básicas
        if readings:
            avg_spo2 = sum(r["spo2"] for r in readings) / len(readings)
            avg_co2 = sum(r["co2"] for r in readings) / len(readings)
            avg_hr = sum(r["heart_rate"] for r in readings) / len(readings)
        else:
            avg_spo2 = avg_co2 = avg_hr = 0
        
        prompt = f"""
        Crea una rutina de entrenamiento personalizada basada en estos datos:

        PERFIL DEL USUARIO:
        - Nombre: {user.get('name', 'N/A')}
        - Edad: {user.get('age', 'N/A')} años
        - Peso: {user.get('weight', 'N/A')} kg
        - Deporte preferido: {user.get('sport_preference', 'N/A')}
        - Nivel de fitness: {user.get('fitness_level', 'N/A')}

        MÉTRICAS FISIOLÓGICAS PROMEDIO:
        - SpO2: {avg_spo2:.1f}%
        - CO2: {avg_co2:.0f} ppm
        - Frecuencia cardíaca: {avg_hr:.0f} bpm

        RUTINA ACTUAL: {json.dumps(current_routine, default=str) if current_routine else "Ninguna"}

        Crea una rutina que:
        1. Sea apropiada para el nivel de fitness del usuario
        2. Considere las métricas fisiológicas actuales
        3. Incluya ejercicios específicos para su deporte preferido
        4. Sea progresiva y segura
        5. Incluya tiempos de descanso apropiados

        Responde en formato JSON:
        {{
            "routine_name": "Nombre de la rutina",
            "duration_minutes": 30,
            "difficulty": "beginner|intermediate|advanced",
            "exercises": [
                {{
                    "name": "Nombre del ejercicio",
                    "duration_minutes": 5,
                    "intensity": "low|moderate|high",
                    "description": "Descripción detallada",
                    "target_muscles": ["músculos objetivo"],
                    "instructions": ["paso 1", "paso 2"]
                }}
            ],
            "warmup": "Instrucciones de calentamiento",
            "cooldown": "Instrucciones de enfriamiento",
            "safety_notes": ["Notas de seguridad importantes"],
            "progression_plan": "Cómo progresar esta rutina"
        }}
        """
        
        return prompt
    
    def _parse_chatgpt_response(self, response_text: str) -> Dict:
        """Parsea la respuesta de ChatGPT"""
        try:
            # Intentar parsear como JSON
            if response_text.strip().startswith('{'):
                return json.loads(response_text)
            else:
                # Si no es JSON válido, crear estructura básica
                return {
                    "analysis_summary": response_text,
                    "alerts": [],
                    "trends": [],
                    "recommendations": [{
                        "type": "general",
                        "priority": "medium",
                        "message": response_text,
                        "action": "Revisar datos"
                    }],
                    "next_steps": "Continuar monitoreo",
                    "confidence_score": 0.5
                }
        except json.JSONDecodeError:
            return {
                "analysis_summary": response_text,
                "alerts": [],
                "trends": [],
                "recommendations": [],
                "next_steps": "Revisar análisis manualmente",
                "confidence_score": 0.3
            }
    
    def _parse_workout_response(self, response_text: str) -> Dict:
        """Parsea la respuesta de recomendación de entrenamiento"""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            return {
                "status": "error",
                "message": "Error parseando recomendación de entrenamiento",
                "routine": None
            }
    
    def _save_analysis(self, user_id: str, analysis: Dict, user_data: Dict):
        """Guarda el análisis en la base de datos"""
        analysis_doc = {
            "user_id": user_id,
            "analysis_type": "physiological",
            "analysis_data": analysis,
            "data_points_analyzed": len(user_data["readings"]),
            "time_window_hours": user_data["time_window_hours"],
            "created_at": datetime.utcnow(),
            "ai_model": "gpt-4"
        }
        
        self.db.analyses.insert_one(analysis_doc)
    
    def _save_workout_recommendation(self, user_id: str, recommendation: Dict):
        """Guarda la recomendación de entrenamiento"""
        recommendation_doc = {
            "user_id": user_id,
            "recommendation_type": "workout",
            "recommendation_data": recommendation,
            "created_at": datetime.utcnow(),
            "ai_model": "gpt-4"
        }
        
        self.db.workout_recommendations.insert_one(recommendation_doc)
