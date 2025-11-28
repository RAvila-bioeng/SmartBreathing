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
        
        # 1. Prepare Mappings
        # Level Mapping: Map user profile level to Excel/DB 'nivel_detallado'
        user_level = (user_profile.fitness_level or "intermedio").lower()
        if "principiante" in user_level or "beginner" in user_level:
            target_level = "Principiante"
        elif "avanzado" in user_level or "advanced" in user_level:
            target_level = "Avanzado"
        else:
            target_level = "Intermedio"

        # Intensity Mapping: Map user 'grado_exigencia' to Excel/DB 'intensidad_relativa'
        user_intensity = (user_profile.grado_exigencia or "moderado").lower()
        if "bajo" in user_intensity:
            target_intensity = "Bajo"
        elif "exigente" in user_intensity:
            target_intensity = "Alto"
        else:
            target_intensity = "Medio"

        # Equipment Check
        user_equipment = (user_profile.equipamiento or "").lower()
        has_facilities = any(x in user_equipment for x in ["instalaciones", "gimnasio", "gym", "piscina"])

        # Sport Preference Mapping to 'modalidad' regex
        sport_pref = (user_profile.sport_preference or "").lower()
        sport_regex = None
        if "natacion" in sport_pref or "natación" in sport_pref or "swimming" in sport_pref:
            sport_regex = "Natación|Piscina|Agua"
        elif "gimnasio" in sport_pref or "gym" in sport_pref or "pesas" in sport_pref:
            sport_regex = "Gimnasio|Musculación|Fuerza"
        elif "atletismo" in sport_pref or "running" in sport_pref or "correr" in sport_pref:
            sport_regex = "Atletismo|Carrera|Pista|Running"
        elif "calistenia" in sport_pref:
            sport_regex = "Calistenia|Peso corporal"
        
        # 2. Build Queries based on Routine Type
        routine_type = goals[0].lower() if goals else "mixto"
        
        # Base Exclusion Query (Safety & Equipment)
        base_query = {}
        if not has_facilities:
            # Exclude items requiring heavy machinery if no facilities
            # We look for keywords in 'modalidad', 'material_utilizado', 'superficie'
            base_query["$and"] = [
                {"modalidad": {"$not": {"$regex": "Gimnasio|Piscina|Natación", "$options": "i"}}},
                {"material_utilizado": {"$not": {"$regex": "Máquina|Prensa|Barra olímpica|Polea", "$options": "i"}}},
                {"superficie": {"$not": {"$regex": "Pista atletismo|Piscina", "$options": "i"}}}
            ]

        # Block Type Queries
        # Note: Excel fields are exact, but we use regex for safety
        q_warmup = base_query.copy()
        q_warmup["tipo_bloque"] = {"$regex": "Calentamiento|Movilidad|Técnica", "$options": "i"}
        
        q_cooldown = base_query.copy()
        q_cooldown["tipo_bloque"] = {"$regex": "Vuelta a la calma|Recuperación|Estiramientos", "$options": "i"}
        
        q_main = base_query.copy()
        q_main["tipo_bloque"] = {"$regex": "Principal|Núcleo|Trabajo|Complementario", "$options": "i"}

        # Add Routine Type constraints to Main Block
        if routine_type == "aerobico":
            q_main["$or"] = [
                {"objetivo_fisiológico": {"$regex": "Aeróbico", "$options": "i"}},
                {"tags_ia": {"$regex": "cardio|aeróbico|resistencia", "$options": "i"}},
                {"modalidad": {"$regex": "Atletismo|Natación|Carrera", "$options": "i"}}
            ]
        elif routine_type == "anaerobico":
            q_main["$or"] = [
                {"objetivo_fisiológico": {"$regex": "Anaeróbico", "$options": "i"}},
                {"tags_ia": {"$regex": "sprint|potencia|anaeróbico", "$options": "i"}}
            ]
        elif routine_type == "fuerza":
            q_main["$or"] = [
                {"objetivo_entrenamiento": {"$regex": "Fuerza|Hipertrofia", "$options": "i"}},
                {"tags_ia": {"$regex": "fuerza|pesas|musculación", "$options": "i"}},
                {"modalidad": {"$regex": "Gimnasio|Calistenia", "$options": "i"}}
            ]
        elif routine_type == "respiracion":
            q_main["$or"] = [
                {"tags_ia": {"$regex": "respiración|relajación", "$options": "i"}},
                {"objetivo_entrenamiento": {"$regex": "Respiración", "$options": "i"}}
            ]
            # Breathing often overlaps with cooldown or technique
            q_main["tipo_bloque"] = {"$regex": "Técnica|Vuelta a la calma|Recuperación", "$options": "i"}
        
        # 3. Helper to Fetch Exercises with Progressive Relaxation
        def fetch_exercises(query_base, limit=10, prioritize_sport=True):
            # Stage 1: Strict (Sport + Level + Intensity)
            q1 = query_base.copy()
            q1["nivel_detallado"] = {"$regex": f"^{target_level}$", "$options": "i"}
            q1["intensidad_relativa"] = {"$regex": f"^{target_intensity}$", "$options": "i"}
            if prioritize_sport and sport_regex:
                q1["modalidad"] = {"$regex": sport_regex, "$options": "i"}
            
            exercises = list(self.db.Ejercicios.find(q1).limit(limit))
            if len(exercises) >= 2: return exercises
            
            # Stage 2: Relax Sport (keep Level + Intensity)
            # If we didn't find specific sport exercises, try generic but matching level/intensity
            # Only do this if we were filtering by sport
            if prioritize_sport and sport_regex:
                q2 = query_base.copy()
                q2["nivel_detallado"] = {"$regex": f"^{target_level}$", "$options": "i"}
                q2["intensidad_relativa"] = {"$regex": f"^{target_intensity}$", "$options": "i"}
                # Exclude specific sport filter
                exercises = list(self.db.Ejercicios.find(q2).limit(limit))
                if len(exercises) >= 2: return exercises

            # Stage 3: Relax Intensity (keep Level)
            q3 = query_base.copy()
            q3["nivel_detallado"] = {"$regex": f"^{target_level}$", "$options": "i"}
            if prioritize_sport and sport_regex:
                 q3["modalidad"] = {"$regex": sport_regex, "$options": "i"}
            
            exercises = list(self.db.Ejercicios.find(q3).limit(limit))
            if len(exercises) >= 2: return exercises

            # Stage 4: Relax Level (Allow neighbor levels)
            q4 = query_base.copy()
            # Allow any level, basically just matching base criteria
            if prioritize_sport and sport_regex:
                 q4["modalidad"] = {"$regex": sport_regex, "$options": "i"}
            
            exercises = list(self.db.Ejercicios.find(q4).limit(limit))
            
            # Stage 5: "Hail Mary" - just the base query
            if len(exercises) < 1:
                exercises = list(self.db.Ejercicios.find(query_base).limit(limit))
                
            return exercises

        # 4. Fetch blocks
        warmups = fetch_exercises(q_warmup, limit=5, prioritize_sport=True)
        cooldowns = fetch_exercises(q_cooldown, limit=5, prioritize_sport=True)
        
        main_block = []
        if routine_type == "mixto":
            # For mixed, fetch cardio and strength separately
            q_cardio = q_main.copy()
            q_cardio["$or"] = [{"tags_ia": {"$regex": "cardio|aeróbico", "$options": "i"}}]
            cardio_ex = fetch_exercises(q_cardio, limit=5, prioritize_sport=True)
            
            q_str = q_main.copy()
            q_str["$or"] = [{"tags_ia": {"$regex": "fuerza|musculación", "$options": "i"}}]
            str_ex = fetch_exercises(q_str, limit=5, prioritize_sport=True)
            
            main_block = cardio_ex + str_ex
        else:
            main_block = fetch_exercises(q_main, limit=20, prioritize_sport=True)

        # 5. Safety Filter (Condiciones Limitantes)
        limiting_details = (user_profile.condicion_limitante_detalle or "").lower()
        if not limiting_details and user_profile.condiciones_limitantes and len(user_profile.condiciones_limitantes) > 4:
            limiting_details = user_profile.condiciones_limitantes.lower()

        def is_safe(ex):
            if not limiting_details: return True
            # Build text to check
            check_text = " ".join([
                str(ex.get("ejercicio", "")),
                str(ex.get("caracteristicas_especiales", "")),
                str(ex.get("notas_entrenador", ""))
            ]).lower()
            
            # Simple keyword matching rules
            if ("rodilla" in limiting_details or "knee" in limiting_details) and \
               ("salto" in check_text or "jump" in check_text or "impacto" in check_text):
                return False
            if ("espalda" in limiting_details or "back" in limiting_details) and \
               ("peso muerto" in check_text or "deadlift" in check_text or "overhead" in check_text):
                return False
            if ("hombro" in limiting_details or "shoulder" in limiting_details) and \
               ("press militar" in check_text or "overhead" in check_text):
                return False
            return True

        warmups = [e for e in warmups if is_safe(e)]
        main_block = [e for e in main_block if is_safe(e)]
        cooldowns = [e for e in cooldowns if is_safe(e)]

        # 6. Assemble Routine
        final_selection = []
        
        # Add Warmup
        if warmups:
            final_selection.append(random.choice(warmups))
        
        # Add Main Exercises
        # Determine how many based on time
        target_time = user_profile.tiempo_dedicable_diario or 45
        current_time = sum([int(float(e.get("duracion_aprox_min", 5))) for e in final_selection])
        
        random.shuffle(main_block)
        
        for ex in main_block:
            # Avoid duplicates (by ID)
            if any(str(item.get("_id")) == str(ex.get("_id")) for item in final_selection):
                continue
                
            dur = int(float(ex.get("duracion_aprox_min", 10)))
            if current_time + dur > target_time + 5: # Small buffer
                break
            
            final_selection.append(ex)
            current_time += dur
            
            # Max 6 exercises in main block to avoid overwhelm
            if len(final_selection) >= 6:
                break
        
        # Add Cooldown if time permits or strictly at least one
        if cooldowns and current_time < target_time + 10:
             # Try to pick one different from what we have
             cd = random.choice(cooldowns)
             if not any(str(item.get("_id")) == str(cd.get("_id")) for item in final_selection):
                 final_selection.append(cd)
                 current_time += int(float(cd.get("duracion_aprox_min", 5)))

        # 7. Format Response
        routine_exercises = []
        for ex in final_selection:
            dur = int(float(ex.get("duracion_aprox_min", 10)))
            routine_exercises.append(ExerciseInRoutine(
                name=ex.get("ejercicio", "Ejercicio"),
                description=ex.get("notas_entrenador") or ex.get("objetivo_entrenamiento") or "",
                duration=dur,
                intensity=ex.get("intensidad_relativa", "Media"),
                id_ejercicio=str(ex.get("_id"))
            ))
            
        # Frequency Days
        freq = user_profile.frecuencia_entrenamiento or 3
        days_map = {
            1: ["Lunes"],
            2: ["Lunes", "Jueves"],
            3: ["Lunes", "Miércoles", "Viernes"],
            4: ["Lunes", "Martes", "Jueves", "Viernes"],
            5: ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
        }
        days = days_map.get(freq, ["Lunes", "Miércoles", "Viernes"])
        if freq > 5: days = days_map[5]

        return RoutineResponse(
            name=f"Rutina {routine_type.capitalize()} ({target_level})",
            total_duration=current_time,
            difficulty=target_level,
            dias_semana=days,
            exercises=routine_exercises
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
