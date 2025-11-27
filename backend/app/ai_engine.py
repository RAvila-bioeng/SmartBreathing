from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import statistics
import random
from .models import (
    SensorReading, UserProfile, AIRecommendation, WorkoutRoutine,
    RoutineResponse, ExerciseInRoutine
)
from .db import get_database

class SmartBreathingAI:
    def __init__(self):
        self.db = get_database()

    def generate_routine_from_db(self, user_profile: UserProfile, goals: List[str]) -> RoutineResponse:
        """
        Generates a personalized routine by querying the Ejercicios collection.
        Follows a 'best effort' approach: strict filters first, then relaxed.
        """
        
        # 1. Prepare base filters from UserProfile
        # Mappings
        # sport_preference mapping (simple text match for now)
        # We can try to match 'modalidad' with user_profile.sport_preference
        
        # Fitness level mapping
        level_map = {
            "principiante": "principiante",
            "intermedio": "intermedio",
            "avanzado": "avanzado",
            # Fallbacks or english versions if needed
            "beginner": "principiante",
            "intermediate": "intermedio",
            "advanced": "avanzado"
        }
        target_level = level_map.get(str(user_profile.fitness_level).lower(), "intermedio")

        # Intensity mapping
        intensity_map = {
            "bajo": "Bajo",
            "moderado": "Medio",
            "exigente": "Alto"
        }
        target_intensity = intensity_map.get(str(user_profile.grado_exigencia).lower(), "Medio")

        # Equipment
        has_facilities = str(user_profile.equipamiento).lower() in ["instalaciones", "gimnasio", "gym"]
        
        # Base query
        query: Dict[str, Any] = {}

        # 2. Build Query - Attempt 1: Strict
        # Filter by modality if possible (using regex for flexibility)
        if user_profile.sport_preference:
            # Try to match the sport preference in modality or tags
            # Construct a regex that matches the sport name
            sport_regex = {"$regex": user_profile.sport_preference, "$options": "i"}
            query["$or"] = [
                {"modalidad": sport_regex},
                {"tags_ia": sport_regex},
                {"objetivo_entrenamiento": sport_regex}
            ]

        # Filter by level
        query["nivel_detallado"] = target_level

        # Filter by intensity
        query["intensidad_relativa"] = target_intensity

        # Filter by equipment (exclusion logic)
        if not has_facilities:
            # If no facilities, exclude modalities that imply gym/pool
            # AND exclude exercises that require machines
            # Exclude modalities:
            exclude_modalities = ["Gimnasio", "Natación", "Natacion"]
            # But wait, if preference IS swimming, and no facilities, we probably shouldn't exclude swimming completely? 
            # Or assume swimming implies "I have access to a pool"?
            # Prompt says: "If equipamiento is 'instalaciones', allow exercises that require gym/pool/etc.
            # If not, exclude exercises that clearly require special facilities or equipment (machines, pool, heavy equipment)."
            # So if equipamiento != instalaciones, we MUST exclude pool/gym stuff.
            
            # We can use $nin for modalidad
            query["modalidad"] = {"$nin": exclude_modalities}
            
            # We could also filter out exercises that might require equipment via tags or text if we had better data.
            # For now, excluding broad modalities is the safest bet.

        # Execute Query
        exercises_cursor = self.db.Ejercicios.find(query)
        exercises = list(exercises_cursor)

        # 3. Fallback / Relaxing Filters
        if len(exercises) < 3:
            # Relax intensity
            if "intensidad_relativa" in query:
                del query["intensidad_relativa"]
            exercises = list(self.db.Ejercicios.find(query))
        
        if len(exercises) < 3:
            # Relax level
            if "nivel_detallado" in query:
                del query["nivel_detallado"]
            exercises = list(self.db.Ejercicios.find(query))

        if len(exercises) < 3:
            # Relax sport preference (fetch generic exercises)
            # Re-build query with just equipment constraint
            query = {} 
            if not has_facilities:
                 query["modalidad"] = {"$nin": ["Gimnasio", "Natación", "Natacion"]}
            exercises = list(self.db.Ejercicios.find(query))

        # 4. Filter for Limiting Conditions (In Memory)
        # Using condicion_limitante_detalle if available, or fallback to condiciones_limitantes if string details are there
        details = (user_profile.condicion_limitante_detalle or "").lower()
        
        # If detail is empty, maybe check conditions_limitantes in case it was stored there
        if not details and user_profile.condiciones_limitantes and len(user_profile.condiciones_limitantes) > 5:
             details = user_profile.condiciones_limitantes.lower()
        
        if details:
            # Simple keyword exclusion
            risky_keywords = []
            if "rodilla" in details or "knee" in details:
                risky_keywords.extend(["salto", "jump", "impacto", "sentadilla profunda", "deep squat"])
            if "espalda" in details or "back" in details:
                risky_keywords.extend(["peso muerto", "deadlift", "hipertextensión", "overhead", "militar"])
            if "hombro" in details or "shoulder" in details:
                risky_keywords.extend(["overhead", "press militar", "dominadas", "pull up"])
            
            if risky_keywords:
                safe_exercises = []
                for ex in exercises:
                    is_safe = True
                    # Check description/notes for risky keywords
                    text_to_check = (
                        str(ex.get("ejercicio", "")) + " " + 
                        str(ex.get("caracteristicas_especiales", "")) + " " + 
                        str(ex.get("notas_entrenador", ""))
                    ).lower()
                    
                    for kw in risky_keywords:
                        if kw in text_to_check:
                            is_safe = False
                            break
                    if is_safe:
                        safe_exercises.append(ex)
                exercises = safe_exercises

        # If we filtered everything out, go back to raw exercises (risky is better than empty? or return empty?)
        # Prompt says "avoid obviously risky". If nothing left, we might fail or return basics.
        # Let's keep what we have.

        # 5. Selection (Warm-up, Main, Cool-down)
        # Categorize
        warmups = []
        main_part = []
        cooldowns = []

        for ex in exercises:
            # Naive classification based on text
            name = str(ex.get("ejercicio", "")).lower()
            obj_ent = str(ex.get("objetivo_entrenamiento", "")).lower()
            tipo_bloque = str(ex.get("tipo_bloque", "")).lower()

            if "calentamiento" in name or "calentamiento" in obj_ent or "warm" in name or "complementario" in tipo_bloque:
                warmups.append(ex)
            elif "estiramiento" in name or "vuelta a la calma" in name or "respiracion" in name or "cool" in name:
                cooldowns.append(ex)
            else:
                main_part.append(ex)

        selected_routine = []
        
        # Select 1 Warmup
        if warmups:
            selected_routine.append(random.choice(warmups))
        elif main_part:
             # Use a low intensity main exercise as warmup if forced
             pass 

        # Select 2-4 Main
        count_main = min(len(main_part), random.randint(2, 4))
        if count_main > 0:
            selected_routine.extend(random.sample(main_part, count_main))
        
        # Select 1 Cooldown
        if cooldowns:
            selected_routine.append(random.choice(cooldowns))
        
        # Fallback if routine is too short (fill with whatever)
        if len(selected_routine) < 3 and len(exercises) > len(selected_routine):
            needed = 3 - len(selected_routine)
            remaining = [e for e in exercises if e not in selected_routine]
            if remaining:
                selected_routine.extend(remaining[:needed])

        # 6. Build Response
        final_exercises = []
        total_time = 0
        
        for ex in selected_routine:
            # Duration parsing
            dur = 10 # default
            try:
                dur = int(float(ex.get("duracion_aprox_min", 10)))
            except:
                pass
            
            total_time += dur
            
            final_exercises.append(ExerciseInRoutine(
                name=ex.get("ejercicio", "Ejercicio sin nombre"),
                description=ex.get("notas_entrenador") or ex.get("descripcion") or ex.get("objetivo_entrenamiento") or "Realizar según indicaciones.",
                duration=dur,
                intensity=ex.get("intensidad_relativa", "Media")
            ))

        # Days of week logic
        freq = user_profile.frecuencia_entrenamiento or 3
        days = []
        if freq == 1:
            days = ["Monday"]
        elif freq == 2:
            days = ["Monday", "Thursday"]
        elif freq == 3:
            days = ["Monday", "Wednesday", "Friday"]
        elif freq >= 4:
            days = ["Monday", "Tuesday", "Thursday", "Friday"]
        else:
            days = ["Monday", "Wednesday", "Friday"] # Default

        routine_name = f"Rutina {user_profile.sport_preference or 'General'} - {user_profile.fitness_level or 'Intermedio'}"

        return RoutineResponse(
            name=routine_name,
            total_duration=total_time,
            difficulty=user_profile.fitness_level or "intermedio",
            dias_semana=days,
            exercises=final_exercises
        )

    def analyze_physiological_data(self, user_id: str, recent_readings: List[SensorReading] = None) -> Dict:
        """Analiza los datos fisiológicos directamente de MongoDB (sin IA)"""
        return self._fallback_analysis(user_id, recent_readings)

    def _fallback_analysis(self, user_id: str, recent_readings: List[SensorReading] = None) -> Dict:
        """Análisis básico de respaldo solo con base de datos"""
        if not recent_readings:
            since = datetime.utcnow() - timedelta(hours=2)
            readings_data = list(self.db.sensor_readings.find(
                {"user_id": user_id, "timestamp": {"$gte": since}},
                sort=[("timestamp", -1)],
                limit=50
            ))
            recent_readings = [SensorReading(**r) for r in readings_data]

        if not recent_readings:
            return {"status": "insufficient_data", "message": "No hay datos suficientes para análisis"}
        
        # Calcular promedios y tendencias
        spo2_values = [r.spo2 for r in recent_readings]
        co2_values = [r.co2 for r in recent_readings]
        hr_values = [r.heart_rate for r in recent_readings]

        analysis = {
            "status": "success",
            "analysis_summary": f"Análisis básico: SpO2 {statistics.mean(spo2_values):.1f}%, CO2 {statistics.mean(co2_values):.0f}ppm, FC {statistics.mean(hr_values):.0f}bpm",
            "alerts": [],
            "trends": [
                f"SpO2: {self._calculate_trend(spo2_values)}",
                f"CO2: {self._calculate_trend(co2_values)}",
                f"FC: {self._calculate_trend(hr_values)}"
            ],
            "recommendations": [{
                "type": "general",
                "priority": "medium",
                "message": "Análisis básico completado",
                "action": "Revisar métricas"
            }],
            "next_steps": "Continuar monitoreo",
            "confidence_score": 0.6,
            "avg_spo2": statistics.mean(spo2_values),
            "avg_co2": statistics.mean(co2_values),
            "avg_heart_rate": statistics.mean(hr_values),
            "data_quality": self._assess_data_quality(recent_readings),
            "timestamp": datetime.utcnow()
        }
        return analysis

    def generate_recommendation(self, user_id: str, analysis: Dict) -> AIRecommendation:
        """Genera una recomendación basada en el análisis de datos"""
        recommendation_type = "exercise"
        message = "Continúa con tu rutina actual"
        confidence = 0.5
        based_on_metrics = {}

        # Evaluar SpO2
        if analysis["avg_spo2"] < 95:
            recommendation_type = "warning"
            message = "⚠️ Nivel de oxígeno bajo. Considera reducir la intensidad o tomar un descanso."
            confidence = 0.9
            based_on_metrics["spo2"] = analysis["avg_spo2"]
        elif analysis["avg_spo2"] > 98:
            recommendation_type = "exercise"
            message = "💪 Excelente oxigenación. Puedes aumentar la intensidad del ejercicio."
            confidence = 0.8
            based_on_metrics["spo2"] = analysis["avg_spo2"]

        # Evaluar CO2
        if analysis["avg_co2"] > 600:
            recommendation_type = "rest"
            message = "😮‍💨 Nivel de CO2 elevado. Toma un descanso y practica respiración profunda."
            confidence = 0.85
            based_on_metrics["co2"] = analysis["avg_co2"]
        elif analysis["avg_co2"] < 400:
            recommendation_type = "exercise"
            message = "✅ Niveles de CO2 normales. Continúa con tu rutina."
            confidence = 0.7
            based_on_metrics["co2"] = analysis["avg_co2"]

        # Evaluar frecuencia cardíaca
        if analysis["avg_heart_rate"] > 180:
            recommendation_type = "warning"
            message = "❤️ Frecuencia cardíaca muy alta. Reduce la intensidad inmediatamente."
            confidence = 0.95
            based_on_metrics["heart_rate"] = analysis["avg_heart_rate"]
        elif analysis["avg_heart_rate"] < 60:
            recommendation_type = "exercise"
            message = "💓 Frecuencia cardíaca en reposo. Puedes comenzar a calentar."
            confidence = 0.6
            based_on_metrics["heart_rate"] = analysis["avg_heart_rate"]

        # Combinar recomendaciones si hay múltiples alertas
        if len(based_on_metrics) > 1:
            if "spo2" in based_on_metrics and "co2" in based_on_metrics:
                recommendation_type = "warning"
                message = "🚨 Múltiples alertas fisiológicas. Detén el ejercicio y consulta un médico."
                confidence = 0.95

        return AIRecommendation(
            user_id=user_id,
            recommendation_type=recommendation_type,
            message=message,
            confidence_score=confidence,
            based_on_metrics=based_on_metrics
        )

    def suggest_workout_adjustment(self, user_id: str, current_routine: WorkoutRoutine, analysis: Dict) -> Dict:
        """Sugiere ajustes a la rutina de ejercicio basado en datos fisiológicos"""
        adjustments = {
            "intensity_change": 0,  # -1 (reducir), 0 (mantener), 1 (aumentar)
            "duration_change": 0,   # minutos a añadir/quitar
            "rest_recommended": False,
            "exercise_skip": False,
            "reasoning": []
        }

        # Lógica de ajuste basada en métricas
        if analysis["avg_spo2"] < 95:
            adjustments["intensity_change"] = -1
            adjustments["rest_recommended"] = True
            adjustments["reasoning"].append("Oxigenación baja")

        if analysis["avg_co2"] > 600:
            adjustments["intensity_change"] = -1
            adjustments["rest_recommended"] = True
            adjustments["reasoning"].append("CO2 elevado")

        if analysis["avg_heart_rate"] > 180:
            adjustments["intensity_change"] = -1
            adjustments["exercise_skip"] = True
            adjustments["reasoning"].append("Frecuencia cardíaca muy alta")

        if analysis["avg_spo2"] > 98 and analysis["avg_co2"] < 400 and analysis["avg_heart_rate"] < 150:
            adjustments["intensity_change"] = 1
            adjustments["reasoning"].append("Métricas excelentes")

        return adjustments

    def create_personalized_routine(self, user_profile: UserProfile, goals: List[str]) -> WorkoutRoutine:
        """Crea una rutina básica como fallback"""
        # Rutinas base por nivel de fitness
        base_routines = {
            "beginner": {
                "duration": 20,
                "exercises": [
                    {"name": "Calentamiento", "duration": 5, "intensity": "low"},
                    {"name": "Respiración profunda", "duration": 5, "intensity": "low"},
                    {"name": "Ejercicio cardiovascular suave", "duration": 10, "intensity": "moderate"}
                ]
            },
            "intermediate": {
                "duration": 30,
                "exercises": [
                    {"name": "Calentamiento dinámico", "duration": 5, "intensity": "low"},
                    {"name": "Ejercicio cardiovascular", "duration": 15, "intensity": "moderate"},
                    {"name": "Respiración controlada", "duration": 5, "intensity": "low"},
                    {"name": "Enfriamiento", "duration": 5, "intensity": "low"}
                ]
            },
            "advanced": {
                "duration": 45,
                "exercises": [
                    {"name": "Calentamiento intenso", "duration": 10, "intensity": "moderate"},
                    {"name": "HIIT", "duration": 20, "intensity": "high"},
                    {"name": "Respiración avanzada", "duration": 10, "intensity": "moderate"},
                    {"name": "Enfriamiento activo", "duration": 5, "intensity": "low"}
                ]
            }
        }

        routine_template = base_routines.get(user_profile.fitness_level, base_routines["beginner"])

        # Personalizar según deporte preferido
        if "running" in user_profile.sport_preference.lower():
            routine_template["exercises"].append({"name": "Técnica de carrera", "duration": 10, "intensity": "moderate"})
        elif "cycling" in user_profile.sport_preference.lower():
            routine_template["exercises"].append({"name": "Simulación de ciclismo", "duration": 15, "intensity": "moderate"})

        return WorkoutRoutine(
            user_id=user_profile.id,
            name=f"Rutina {user_profile.fitness_level.title()} - {user_profile.sport_preference}",
            description=f"Rutina personalizada para {user_profile.name}",
            exercises=routine_template["exercises"],
            total_duration=routine_template["duration"],
            difficulty=user_profile.fitness_level,
            target_goals=goals
        )

    def _calculate_trend(self, values: List[float]) -> str:
        """Calcula la tendencia de una serie de valores"""
        if len(values) < 2:
            return "stable"

        n = len(values)
        x = list(range(n))
        y = values

        x_mean = statistics.mean(x)
        y_mean = statistics.mean(y)

        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return "stable"

        slope = numerator / denominator

        if slope > 0.1:
            return "increasing"
        elif slope < -0.1:
            return "decreasing"
        else:
            return "stable"

    def _assess_data_quality(self, readings: List[SensorReading]) -> str:
        """Evalúa la calidad de los datos de sensores"""
        if not readings:
            return "poor"

        time_gaps = []
        for i in range(1, len(readings)):
            gap = (readings[i].timestamp - readings[i-1].timestamp).total_seconds()
            time_gaps.append(gap)

        avg_gap = statistics.mean(time_gaps) if time_gaps else 0

        if avg_gap < 5:
            return "excellent"
        elif avg_gap < 30:
            return "good"
        elif avg_gap < 60:
            return "fair"
        else:
            return "poor"
