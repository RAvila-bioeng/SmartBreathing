from datetime import datetime, timedelta
from typing import List, Dict, Optional
import statistics
from .models import SensorReading, UserProfile, AIRecommendation, WorkoutRoutine
from .db import get_database

class SmartBreathingAI:
    def __init__(self):
        self.db = get_database()

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
