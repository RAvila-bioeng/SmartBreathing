from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import statistics
import random
import logging

from .models import (
    SensorReading, UserProfile, AIRecommendation, WorkoutRoutine,
    RoutineResponse, ExerciseInRoutine
)
from .db import get_database

logger = logging.getLogger(__name__)


class SmartBreathingAI:
    def __init__(self):
        self.db = get_database()

    # -------------------------------------------------------------------------
    # RUTINA A PARTIR DE LA DB
    # -------------------------------------------------------------------------
    def generate_routine_from_db(self, user_profile: UserProfile, goals: List[str]) -> RoutineResponse:
        """
        Genera una rutina personalizada consultando la colección Ejercicios.
        Da prioridad al deporte preferido del usuario (campo 'deporte' en la DB).
        Hace un enfoque de "best effort": primero filtros estrictos, luego relaja.
        """
        user_id_log = str(user_profile.id) if user_profile.id else "unknown"
        logger.info(
            f"Generating routine for user {user_id_log} - Profile: "
            f"{user_profile.model_dump_json()}"
        )

        # --------------------- 1. NORMALIZACIONES DE PERFIL -------------------
        # Nivel
        user_level = (user_profile.fitness_level or "").lower()
        if "prin" in user_level or "beginner" in user_level:
            target_level = "principiante"
        elif "avan" in user_level or "advanced" in user_level:
            target_level = "avanzado"
        else:
            target_level = "intermedio"

        # Intensidad: en la DB tienes "Bajo", "Moderado", "Exigente"
        user_intensity = (user_profile.grado_exigencia or "").lower()
        if "bajo" in user_intensity:
            target_intensity = "bajo"
        elif "alto" in user_intensity or "exig" in user_intensity or "intens" in user_intensity:
            target_intensity = "exigente"
        else:
            target_intensity = "moderado"

        # Equipamiento
        user_equipment = (user_profile.equipamiento or "").lower()
        has_facilities = any(
            x in user_equipment
            for x in ["instalaciones", "gimnasio", "gym", "piscina", "club"]
        )

        # Deporte preferido
        sport_pref_raw = (user_profile.sport_preference or "").strip().lower()
        main_deporte = sport_pref_raw or None

        # Palabras clave según el deporte
        sport_keywords = None
        if main_deporte:
            if "natacion" in main_deporte or "natación" in main_deporte or "swim" in main_deporte:
                sport_keywords = "natacion|natación|piscina|nado|nadar|agua|swim"
            elif "gimnasio" in main_deporte or "gym" in main_deporte or "pesas" in main_deporte or "crossfit" in main_deporte:
                sport_keywords = "gimnasio|gym|pesas|musculación|fuerza|crossfit"
            elif "atletismo" in main_deporte or "running" in main_deporte or "correr" in main_deporte:
                sport_keywords = "atletismo|carrera|running|pista|series|fondo"
            elif "calistenia" in main_deporte:
                sport_keywords = "calistenia|peso corporal|barras|street workout"
            elif "ciclismo" in main_deporte or "bici" in main_deporte:
                sport_keywords = "ciclismo|bicicleta|rodillo|bici"

        # ---------------------- 2. QUERY BASE (SEGURIDAD) ---------------------
        base_query: Dict[str, Any] = {}

        if not has_facilities:
            # Sin instalaciones: evitar máquinas y pesas pesadas, etc.
            base_query["$and"] = [
                {
                    "material_utilizado": {
                        "$not": {
                            "$regex": "Máquina|Prensa|Barra olímpica|Polea|Multipower",
                            "$options": "i",
                        }
                    }
                },
                {
                    "superficie": {
                        "$not": {
                            "$regex": "Sala de pesas|Gimnasio",
                            "$options": "i",
                        }
                    }
                },
            ]

        # ----------------- 3. FILTRO DEPORTE / PALABRAS CLAVE -----------------
        def get_sport_query_part():
            """
            Construye la parte del filtro que prioriza el deporte del usuario.

            - Primero intenta 'deporte' == sport_pref del usuario.
            - También usa keywords en modalidad/superficie/tags/ejercicio.
            """
            conditions = []

            if main_deporte:
                # Campo 'deporte' en la colección Ejercicios (natacion, gimnasio, atletismo, mixto…)
                conditions.append(
                    {"deporte": {"$regex": main_deporte, "$options": "i"}}
                )

            if sport_keywords:
                conditions.extend(
                    [
                        {"modalidad": {"$regex": sport_keywords, "$options": "i"}},
                        {"superficie": {"$regex": sport_keywords, "$options": "i"}},
                        {"tags_ia": {"$regex": sport_keywords, "$options": "i"}},
                        {"ejercicio": {"$regex": sport_keywords, "$options": "i"}},
                    ]
                )

            if not conditions:
                return {}

            return {"$or": conditions}

        # ------------------ 4. FILTRO POR OBJETIVO (GOALS) --------------------
        routine_type = goals[0].lower() if goals else "mixto"

        def get_goal_query_part(rtype: str) -> Dict[str, Any]:
            q: Dict[str, Any] = {}
            if rtype == "aerobico":
                q["$or"] = [
                    {
                        "objetivo_fisiológico": {
                            "$regex": "Aeróbico|Resistencia",
                            "$options": "i",
                        }
                    },
                    {
                        "tags_ia": {
                            "$regex": "cardio|aeróbico|resistencia|fondo",
                            "$options": "i",
                        }
                    },
                    {
                        "objetivo_entrenamiento": {
                            "$regex": "Resistencia",
                            "$options": "i",
                        }
                    },
                ]
            elif rtype == "anaerobico":
                q["$or"] = [
                    {
                        "objetivo_fisiológico": {
                            "$regex": "Anaeróbico",
                            "$options": "i",
                        }
                    },
                    {
                        "tags_ia": {
                            "$regex": "sprint|potencia|anaeróbico|hiit",
                            "$options": "i",
                        }
                    },
                    {
                        "objetivo_entrenamiento": {
                            "$regex": "Potencia|Velocidad",
                            "$options": "i",
                        }
                    },
                ]
            elif rtype == "fuerza":
                q["$or"] = [
                    {
                        "objetivo_entrenamiento": {
                            "$regex": "Fuerza|Hipertrofia|Tono",
                            "$options": "i",
                        }
                    },
                    {
                        "tags_ia": {
                            "$regex": "fuerza|pesas|musculación",
                            "$options": "i",
                        }
                    },
                    {
                        "modalidad": {
                            "$regex": "Gimnasio|Calistenia",
                            "$options": "i",
                        }
                    },
                ]
            elif rtype == "respiracion":
                q["$or"] = [
                    {
                        "tags_ia": {
                            "$regex": "respiración|relajación|apnea",
                            "$options": "i",
                        }
                    },
                    {
                        "objetivo_entrenamiento": {
                            "$regex": "Respiración|Control",
                            "$options": "i",
                        }
                    },
                ]
            return q

        # Filtros de nivel e intensidad
        c_level = {
            "nivel_detallado": {
                # 'intermedio', 'principiante', 'avanzado' en la DB
                "$regex": target_level,
                "$options": "i",
            }
        }
        c_intensity = {
            "intensidad_relativa": {
                # 'Bajo', 'Moderado', 'Exigente' en la DB
                "$regex": target_intensity,
                "$options": "i",
            }
        }

        # ------------------ 5. ESTRATEGIA DE BÚSQUEDA POR BLOQUE --------------
        def fetch_block_exercises(block_regex: str, limit: int = 10, is_main: bool = False) -> List[Dict]:
            """
            Devuelve hasta 'limit' ejercicios para un tipo de bloque (Calentamiento, Principal, etc.)
            Priorizando SIEMPRE el deporte del usuario; luego, si no hay nada, abre a otros deportes.
            """
            sport_filter = get_sport_query_part()
            goal_filter = get_goal_query_part(routine_type) if is_main and routine_type != "mixto" else {}

            def build_steps(prefer_sport: bool):
                """
                Construye las distintas "capas" de filtros para ir relajando condiciones.
                Si prefer_sport=True, incluye el filtro de deporte; si False, no lo incluye.
                """
                steps_local = []

                # Base: tipo_bloque + seguridad/equipamiento
                q_base: Dict[str, Any] = base_query.copy()
                if "$and" not in q_base:
                    q_base["$and"] = []
                q_base["$and"].append(
                    {"tipo_bloque": {"$regex": block_regex, "$options": "i"}}
                )

                def add_if(condition: Dict[str, Any]):
                    if condition:
                        q_base["$and"].append(condition)

                # PASO 1: deporte + nivel + intensidad + objetivo
                q1 = {"$and": list(q_base["$and"])}
                if prefer_sport and sport_filter:
                    q1["$and"].append(sport_filter)
                q1["$and"].append(c_level)
                q1["$and"].append(c_intensity)
                if goal_filter:
                    q1["$and"].append(goal_filter)
                steps_local.append(("Strict: sport+level+int+goal", q1))

                # PASO 2: deporte + nivel + intensidad (sin objetivo)
                q2 = {"$and": list(q_base["$and"])}
                if prefer_sport and sport_filter:
                    q2["$and"].append(sport_filter)
                q2["$and"].append(c_level)
                q2["$and"].append(c_intensity)
                steps_local.append(("Relax goal: sport+level+int", q2))

                # PASO 3: deporte + nivel (sin intensidad ni objetivo)
                q3 = {"$and": list(q_base["$and"])}
                if prefer_sport and sport_filter:
                    q3["$and"].append(sport_filter)
                q3["$and"].append(c_level)
                steps_local.append(("Relax int+goal: sport+level", q3))

                # PASO 4: solo deporte (sin nivel, sin intensidad, sin objetivo)
                q4 = {"$and": list(q_base["$and"])}
                if prefer_sport and sport_filter:
                    q4["$and"].append(sport_filter)
                steps_local.append(("Only sport", q4))

                # PASO 5 (solo cuando prefer_sport=False): sin deporte, con nivel
                if not prefer_sport:
                    q5 = {"$and": list(q_base["$and"])}
                    q5["$and"].append(c_level)
                    if goal_filter:
                        q5["$and"].append(goal_filter)
                    steps_local.append(("Fallback no sport: level(+goal)", q5))

                return steps_local

            seen_ids = set()
            results: List[Dict] = []

            # 1º: Intentar SIEMPRE con el deporte del usuario
            for prefer_sport in [True, False]:
                steps = build_steps(prefer_sport=prefer_sport)

                for step_name, query in steps:
                    if len(results) >= limit:
                        break

                    # Limpiar $and vacío
                    if not query.get("$and"):
                        query.pop("$and", None)

                    try:
                        logger.debug(
                            f"[Fetch {block_regex}] Step '{step_name}' "
                            f"prefer_sport={prefer_sport} - Filter: {query}"
                        )
                        found = list(
                            self.db.Ejercicios.find(query).limit(limit * 3)
                        )

                        valid_batch = []
                        for ex in found:
                            ex_id = str(ex.get("_id"))
                            if ex_id in seen_ids:
                                continue
                            if not self._is_safe(user_profile, ex):
                                continue
                            valid_batch.append(ex)
                            seen_ids.add(ex_id)

                        if valid_batch:
                            logger.info(
                                f"[Fetch {block_regex}] Step '{step_name}' "
                                f"prefer_sport={prefer_sport} -> {len(valid_batch)} exercises"
                            )
                            results.extend(valid_batch)
                        else:
                            logger.debug(
                                f"[Fetch {block_regex}] Step '{step_name}' "
                                f"prefer_sport={prefer_sport} -> 0 exercises"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error executing query step '{step_name}' "
                            f"prefer_sport={prefer_sport}: {e}"
                        )

                if results:
                    # Si ya hemos encontrado algo con prefer_sport=True, no
                    # tiene sentido seguir; si prefer_sport=False, también salimos.
                    break

            return results[:limit]

        # ----------------------- 6. OBTENER BLOQUES ---------------------------
        warmups = fetch_block_exercises("Calentamiento|Movilidad|Técnica", limit=5)
        cooldowns = fetch_block_exercises("Vuelta a la calma|Recuperación|Estiramientos", limit=5)

        # Bloque principal
        main_block: List[Dict] = []
        if routine_type == "mixto":
            # Mezcla de cardio + fuerza
            backup_type = routine_type

            routine_type = "aerobico"
            cardio = fetch_block_exercises("Principal|Núcleo|Trabajo|Complementario", limit=8, is_main=True)

            routine_type = "fuerza"
            strength = fetch_block_exercises("Principal|Núcleo|Trabajo|Complementario", limit=8, is_main=True)

            routine_type = backup_type
            main_block = cardio + strength
        else:
            main_block = fetch_block_exercises("Principal|Núcleo|Trabajo|Complementario", limit=15, is_main=True)

        # ----------------------- 7. ENSAMBLAR RUTINA --------------------------
        final_selection: List[Dict] = []
        target_time = user_profile.tiempo_dedicable_diario or 45
        current_time = 0

        # 7.1. Calentamiento (1 ejercicio si hay)
        if warmups:
            w = random.choice(warmups)
            final_selection.append(w)
            try:
                current_time += int(float(w.get("duracion_aprox_min", 5)))
            except Exception:
                current_time += 5

        # 7.2. Bloque principal (mezclado)
        random.shuffle(main_block)
        for ex in main_block:
            if any(str(e["_id"]) == str(ex["_id"]) for e in final_selection):
                continue

            try:
                dur = int(float(ex.get("duracion_aprox_min", 10)))
            except Exception:
                dur = 10

            # Deja margen para vuelta a la calma
            if current_time + dur > target_time - 5:
                continue

            final_selection.append(ex)
            current_time += dur

            if len(final_selection) >= 6:  # máx. 6 ejercicios en total
                break

        # 7.3. Vuelta a la calma
        if cooldowns and current_time < target_time:
            c = random.choice(cooldowns)
            if not any(str(e["_id"]) == str(c["_id"]) for e in final_selection):
                final_selection.append(c)
                try:
                    current_time += int(float(c.get("duracion_aprox_min", 5)))
                except Exception:
                    current_time += 5

        # Si a pesar de todo no hay nada, lanza error para que el endpoint lo trate
        if not final_selection:
            raise ValueError("No exercises selected for routine")

        # ----------------------- 8. CONSTRUIR RESPONSE ------------------------
        routine_exercises: List[ExerciseInRoutine] = []
        for ex in final_selection:
            logger.info(
                f"Selected: {ex.get('ejercicio')} | Mod: {ex.get('modalidad')} "
                f"| Block: {ex.get('tipo_bloque')} | Deporte: {ex.get('deporte')}"
            )
            try:
                dur = int(float(ex.get("duracion_aprox_min", 10)))
            except Exception:
                dur = 10

            routine_exercises.append(
                ExerciseInRoutine(
                    name=ex.get("ejercicio", "Ejercicio"),
                    description=(
                        ex.get("notas_entrenador")
                        or ex.get("descripcion")
                        or ex.get("objetivo_entrenamiento")
                        or ""
                    ),
                    duration=dur,
                    intensity=ex.get("intensidad_relativa", "Moderado"),
                    id_ejercicio=str(ex.get("_id")),
                )
            )

        freq = user_profile.frecuencia_entrenamiento or 3
        days_map = {
            1: ["Lunes"],
            2: ["Lunes", "Jueves"],
            3: ["Lunes", "Miércoles", "Viernes"],
            4: ["Lunes", "Martes", "Jueves", "Viernes"],
            5: ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"],
        }
        days = days_map.get(freq, ["Lunes", "Miércoles", "Viernes"])
        if freq > 5:
            days = days_map[5]

        r_name = f"Rutina {routine_type.capitalize()} ({target_level.capitalize()})"

        return RoutineResponse(
            name=r_name,
            total_duration=current_time,
            difficulty=target_level.capitalize(),
            dias_semana=days,
            exercises=routine_exercises,
        )

    # -------------------------------------------------------------------------
    #   SEGURIDAD DE EJERCICIO
    # -------------------------------------------------------------------------
    def _is_safe(self, user_profile: UserProfile, ex: Dict) -> bool:
        """Checks if exercise is safe for user conditions"""
        details = (user_profile.condicion_limitante_detalle or "").lower()
        if not details and user_profile.condiciones_limitantes and len(user_profile.condiciones_limitantes) > 4:
            details = user_profile.condiciones_limitantes.lower()

        if not details:
            return True

        check_text = " ".join(
            [
                str(ex.get("ejercicio", "")),
                str(ex.get("caracteristicas_especiales", "")),
                str(ex.get("notas_entrenador", "")),
            ]
        ).lower()

        if ("rodilla" in details or "knee" in details) and (
            "salto" in check_text or "jump" in check_text or "impacto" in check_text
        ):
            return False
        if ("espalda" in details or "back" in details) and (
            "peso muerto" in check_text or "deadlift" in check_text or "overhead" in check_text
        ):
            return False
        if ("hombro" in details or "shoulder" in details) and (
            "press militar" in check_text or "overhead" in check_text
        ):
            return False
        if ("asma" in details or "asthma" in details) and "sprint" in check_text:
            return False

        return True

    # -------------------------------------------------------------------------
    #   ANÁLISIS FISIOLÓGICO Y RECOMENDACIONES (SIN CAMBIOS IMPORTANTES)
    # -------------------------------------------------------------------------
    def analyze_physiological_data(self, user_id: str, recent_readings: List[SensorReading] = None) -> Dict:
        """Analiza los datos fisiológicos directamente de MongoDB (sin IA)"""
        return self._fallback_analysis(user_id, recent_readings)

    def _fallback_analysis(self, user_id: str, recent_readings: List[SensorReading] = None) -> Dict:
        """Análisis básico de respaldo solo con base de datos"""
        if not recent_readings:
            since = datetime.utcnow() - timedelta(hours=2)
            readings_data = list(
                self.db.sensor_readings.find(
                    {"user_id": user_id, "timestamp": {"$gte": since}},
                    sort=[("timestamp", -1)],
                    limit=50,
                )
            )
            recent_readings = [SensorReading(**r) for r in readings_data]

        if not recent_readings:
            return {
                "status": "insufficient_data",
                "message": "No hay datos suficientes para análisis",
            }

        spo2_values = [r.spo2 for r in recent_readings]
        co2_values = [r.co2 for r in recent_readings]
        hr_values = [r.heart_rate for r in recent_readings]

        analysis = {
            "status": "success",
            "analysis_summary": (
                f"Análisis básico: SpO2 {statistics.mean(spo2_values):.1f}%, "
                f"CO2 {statistics.mean(co2_values):.0f}ppm, "
                f"FC {statistics.mean(hr_values):.0f}bpm"
            ),
            "alerts": [],
            "trends": [
                f"SpO2: {self._calculate_trend(spo2_values)}",
                f"CO2: {self._calculate_trend(co2_values)}",
                f"FC: {self._calculate_trend(hr_values)}",
            ],
            "recommendations": [
                {
                    "type": "general",
                    "priority": "medium",
                    "message": "Análisis básico completado",
                    "action": "Revisar métricas",
                }
            ],
            "next_steps": "Continuar monitoreo",
            "confidence_score": 0.6,
            "avg_spo2": statistics.mean(spo2_values),
            "avg_co2": statistics.mean(co2_values),
            "avg_heart_rate": statistics.mean(hr_values),
            "data_quality": self._assess_data_quality(recent_readings),
            "timestamp": datetime.utcnow(),
        }
        return analysis

    def generate_recommendation(self, user_id: str, analysis: Dict) -> AIRecommendation:
        """Genera una recomendación basada en el análisis de datos"""
        recommendation_type = "exercise"
        message = "Continúa con tu rutina actual"
        confidence = 0.5
        based_on_metrics: Dict[str, float] = {}

        if analysis["avg_spo2"] < 95:
            recommendation_type = "warning"
            message = (
                "⚠️ Nivel de oxígeno bajo. Considera reducir la intensidad o tomar un descanso."
            )
            confidence = 0.9
            based_on_metrics["spo2"] = analysis["avg_spo2"]
        elif analysis["avg_spo2"] > 98:
            recommendation_type = "exercise"
            message = "💪 Excelente oxigenación. Puedes aumentar la intensidad del ejercicio."
            confidence = 0.8
            based_on_metrics["spo2"] = analysis["avg_spo2"]

        if analysis["avg_co2"] > 600:
            recommendation_type = "rest"
            message = (
                "😮‍💨 Nivel de CO2 elevado. Toma un descanso y practica respiración profunda."
            )
            confidence = 0.85
            based_on_metrics["co2"] = analysis["avg_co2"]
        elif analysis["avg_co2"] < 400:
            recommendation_type = "exercise"
            message = "✅ Niveles de CO2 normales. Continúa con tu rutina."
            confidence = 0.7
            based_on_metrics["co2"] = analysis["avg_co2"]

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

        if len(based_on_metrics) > 1:
            if "spo2" in based_on_metrics and "co2" in based_on_metrics:
                recommendation_type = "warning"
                message = (
                    "🚨 Múltiples alertas fisiológicas. Detén el ejercicio y consulta un médico."
                )
                confidence = 0.95

        return AIRecommendation(
            user_id=user_id,
            recommendation_type=recommendation_type,
            message=message,
            confidence_score=confidence,
            based_on_metrics=based_on_metrics,
        )

    def suggest_workout_adjustment(
        self, user_id: str, current_routine: WorkoutRoutine, analysis: Dict
    ) -> Dict:
        """Sugiere ajustes a la rutina de ejercicio basado en datos fisiológicos"""
        adjustments: Dict[str, Any] = {
            "intensity_change": 0,
            "duration_change": 0,
            "rest_recommended": False,
            "exercise_skip": False,
            "reasoning": [],
        }

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

        if (
            analysis["avg_spo2"] > 98
            and analysis["avg_co2"] < 400
            and analysis["avg_heart_rate"] < 150
        ):
            adjustments["intensity_change"] = 1
            adjustments["reasoning"].append("Métricas excelentes")

        return adjustments

    # -------------------------------------------------------------------------
    #   UTILIDADES PRIVADAS
    # -------------------------------------------------------------------------
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
            gap = (readings[i].timestamp - readings[i - 1].timestamp).total_seconds()
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
