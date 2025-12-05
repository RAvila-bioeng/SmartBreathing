import sys
import os
import argparse
import time
import datetime
import logging
import random
from typing import Optional, List, Dict, Any
from bson import ObjectId

# Add parent directory to sys.path to access backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from backend.app.db import get_database
except ImportError:
    # Fallback if backend imports fail
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv()
    
    def get_database():
        mongo_uri = os.getenv("MONGODB_URI", "mongodb://root:example@localhost:27017")
        db_name = os.getenv("MONGODB_DB", "SmartBreathing")
        client = MongoClient(mongo_uri)
        return client[db_name]

import serial

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser(description="Ingest CO2 and Humidity data from SCD30 via Arduino")
    parser.add_argument("--user-id", required=True, help="User ID for the session")
    parser.add_argument(
        "--port",
        default=os.getenv("CO2_SERIAL_PORT", "COM4"),
        help="Serial port (e.g. COM4 on Windows or /dev/ttyACM0 on Linux)"
    )
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate")
    parser.add_argument("--mock", action="store_true", help="Generate dummy data instead of reading from serial")
    parser.add_argument("--session", action="store_true", help="Run in session mode (detect stabilization points)")
    return parser.parse_args()

def process_line(line: str) -> Optional[tuple[float, float]]:
    """Parses 'CO2,Hum' line. Returns (co2, hum) or None."""
    try:
        parts = line.strip().split(',')
        if len(parts) != 2:
            return None
        co2 = float(parts[0])
        hum = float(parts[1])
        return co2, hum
    except ValueError:
        return None

class DataProcessor:
    def process(self, co2: float, hum: float):
        pass
        
    def finish(self):
        pass

class StreamingProcessor(DataProcessor):
    def __init__(self, db, user_id):
        self.db = db
        # Convert user_id to ObjectId if possible
        try:
            self.user_oid = ObjectId(user_id)
        except Exception:
            self.user_oid = user_id
            
    def process(self, co2: float, hum: float):
        # Only log to console, NO database updates.
        timestamp = datetime.datetime.now(datetime.timezone.utc)
        logger.info(f"[STREAM] Timestamp: {timestamp}, CO2={co2}, Hum={hum}")

    def finish(self):
        # Nothing to do for streaming
        pass

class SessionProcessor(DataProcessor):
    def __init__(self, db, user_id):
        self.db = db
        try:
            self.user_oid = ObjectId(user_id)
        except Exception:
            self.user_oid = user_id
        
        # State for stabilization
        self.co2_buffer: List[float] = []
        self.hum_buffer: List[float] = []
        self.stable_co2: List[float] = []
        self.stable_hum: List[float] = []
        self.stable_indices: List[int] = []
        self.samples_since_last_plateau = 0
        self.completed = False
        self.baseline_taken = False

        # Parámetros de afinado para la detección de plateaus
        # Número mínimo de muestras en la ventana de comparación (3 previas + 3 recientes)
        self.MIN_BUFFER = 6

        # Separación mínima (en nº de muestras) entre plateaus normales
        self.MIN_GAP_BETWEEN = 6

        # Separación mínima extra tras el baseline (primer punto)
        # para dar tiempo a que la persona empiece a respirar.
        self.MIN_GAP_AFTER_BASELINE = 12

        # Umbral de estabilidad en ppm: más laxo que antes (10 → 40)
        self.THRESHOLD = 40.0

        # Diferencia mínima de CO2 entre plateaus consecutivos para considerarlos "distintos"
        self.MIN_DELTA_CO2 = 150.0
        
        # Raw data accumulation
        self.raw_samples: List[Dict[str, Any]] = []
        self.start_time: Optional[datetime.datetime] = None

    def process(self, co2: float, hum: float):
        if self.completed:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        if self.start_time is None:
            self.start_time = now
            
        self.raw_samples.append({
            "timestamp": now,
            "co2_ppm": co2,
            "humidity_rel": hum
        })
        
        # NEW: baseline logic (Point #1)
        if not self.baseline_taken:
            self.baseline_taken = True
            self.stable_co2.append(co2)
            self.stable_hum.append(hum)
            # Save index of this baseline sample
            self.stable_indices.append(len(self.raw_samples) - 1)
            logger.info(f"Baseline stabilized point #1 at index {self.stable_indices[-1]}: CO2={co2:.2f}, Hum={hum:.2f}")

            # Reset buffers so this sample is NOT reused for window comparison
            self.co2_buffer = []
            self.hum_buffer = []
            self.samples_since_last_plateau = 0

            # We don't want stabilization detection to run on this first sample
            return
        
        self.co2_buffer.append(co2)
        self.hum_buffer.append(hum)
        self.samples_since_last_plateau += 1

        # Elegimos la separación mínima según el número de plateaus ya detectados
        # - Tras el baseline (1er punto), exigimos más separación
        # - Para los siguientes, usamos la separación normal
        required_gap = (
            self.MIN_GAP_AFTER_BASELINE if len(self.stable_co2) == 1
            else self.MIN_GAP_BETWEEN
        )

        # Necesitamos suficientes muestras en buffer y separación desde el último plateau
        if len(self.co2_buffer) >= self.MIN_BUFFER and self.samples_since_last_plateau >= required_gap:
            # Comparamos las últimas 3 muestras con las 3 anteriores
            mean_prev3 = sum(self.co2_buffer[-6:-3]) / 3.0
            mean_last3 = sum(self.co2_buffer[-3:]) / 3.0
            diff = abs(mean_last3 - mean_prev3)

            # Condición de estabilidad: diferencia por debajo de THRESHOLD
            if diff < self.THRESHOLD:
                stable_co2_val = mean_last3
                stable_hum_val = sum(self.hum_buffer[-3:]) / 3.0

                # Filtro adicional: que este plateau sea realmente distinto del anterior
                if self.stable_co2:
                    last_stable = self.stable_co2[-1]
                    if abs(stable_co2_val - last_stable) < self.MIN_DELTA_CO2:
                        logger.info(
                            f"Ignoring plateau candidate (ΔCO2<{self.MIN_DELTA_CO2} ppm) "
                            f"CO2={stable_co2_val:.2f}, last={last_stable:.2f}"
                        )
                        return

                self.stable_co2.append(stable_co2_val)
                self.stable_hum.append(stable_hum_val)

                # Índice del último sample en raw_samples
                current_idx = len(self.raw_samples) - 1
                self.stable_indices.append(current_idx)

                logger.info(
                    f"Detected stabilized point #{len(self.stable_co2)} "
                    f"at index {current_idx}: CO2={stable_co2_val:.2f}, Hum={stable_hum_val:.2f}"
                )

                # Reiniciamos buffers y contador desde el último plateau
                self.co2_buffer = []
                self.hum_buffer = []
                self.samples_since_last_plateau = 0

                # Condición de parada: baseline + 3 plateaus válidos (total 5 puntos)
                # IMPORTANTE: mantén el resto de la lógica intacta
                if len(self.stable_co2) >= 5:
                    logger.info("Reached 5 stabilized points (including baseline). Session complete.")
                    self.completed = True

    def finish(self):
        if not self.raw_samples:
            logger.warning("No data collected in session.")
            return

        end_time = datetime.datetime.now(datetime.timezone.utc)
        
        # 1. Insert Session Document into 'co2' collection (ECG-like schema)
        session_doc = {
            "idUsuario": self.user_oid,
            "fecha": self.start_time,
            "fs": 0.5, # 1 sample every 2 seconds
            "senal": [sample["co2_ppm"] for sample in self.raw_samples],
            "humedad": [sample["humidity_rel"] for sample in self.raw_samples],
            "origen": "scd30_bolsa_v1",
            "co2_estabilizado": self.stable_co2,
            "hum_estabilizada": self.stable_hum,
            "indices_estabilizados": self.stable_indices,
            "num_puntos": len(self.stable_co2)
        }
        
        try:
            self.db.co2.insert_one(session_doc)
            logger.info(f"Saved session document with {len(self.raw_samples)} raw samples and {len(self.stable_co2)} stable points.")
        except Exception as e:
            logger.error(f"Error inserting session document: {e}")
            
        # 2. Update Mediciones with stable points ONLY (no instantaneous values)
        if self.stable_co2:
            update_fields = {"co2_updated_at": end_time}
            for i in range(len(self.stable_co2)):
                # 1-based index: co2_1, co2_2...
                idx = i + 1
                update_fields[f"valores.co2_{idx}"] = self.stable_co2[i]
                update_fields[f"valores.hum_{idx}"] = self.stable_hum[i]
                
            try:
                # Find latest measurement for user or create one
                self.db.Mediciones.update_one(
                    {"idUsuario": self.user_oid},
                    {"$set": update_fields},
                    upsert=True
                )
                logger.info("Updated Mediciones with stabilized values.")
            except Exception as e:
                logger.error(f"Error updating Mediciones in session mode: {e}")
        else:
            logger.warning("No stabilized points found. Mediciones not updated.")

class MockDataGenerator:
    def __init__(self, session_mode=False):
        self.session_mode = session_mode
        self.counter = 0
        self.state = "rising" # rising, stable
        self.stable_value = 0.0
        self.state_duration = 0
    
    def next_sample(self):
        if not self.session_mode:
            # Simple random
            co2 = round(random.uniform(400, 1200), 2)
            hum = round(random.uniform(30, 60), 2)
            return co2, hum
        else:
            # State machine for session
            # Rise for X steps, then Stable for Y steps
            # Sample every 2s, need 6 samples for stability (12s).
            
            if self.state == "rising":
                self.state_duration += 1
                base = 400 + (self.counter * 10) # Linear rise
                noise = random.uniform(-2, 2)
                co2 = base + noise
                
                # Switch to stable after some time (e.g., 20 samples = 40s)
                if self.state_duration > 15:
                    self.state = "stable"
                    self.state_duration = 0
                    self.stable_value = co2
            else:
                # Stable
                self.state_duration += 1
                noise = random.uniform(-1, 1) # Small noise to be within threshold (10ppm)
                co2 = self.stable_value + noise
                
                # Switch back to rising after stabilization should be detected
                # We need ~6-10 samples to be sure detection happens
                if self.state_duration > 10:
                    self.state = "rising"
                    self.state_duration = 0
                    # Jump counter to simulate next breath block start
                    self.counter += 50 
            
            self.counter += 1
            hum = 45.0 + random.uniform(-0.5, 0.5)
            return round(co2, 2), round(hum, 2)

def run_loop(processor: DataProcessor, args):
    if args.mock:
        logger.info("Starting MOCK ingestion.")
        generator = MockDataGenerator(session_mode=args.session)
        while True:
            try:
                co2, hum = generator.next_sample()
                logger.info(f"MOCK Read: {co2},{hum}")
                processor.process(co2, hum)
                
                # Check for completion in session mode
                if isinstance(processor, SessionProcessor) and processor.completed:
                    break
                
                time.sleep(2) # SCD30 interval
            except KeyboardInterrupt:
                logger.info("Stopping mock ingestion...")
                break
            except Exception as e:
                logger.error(f"Error in mock loop: {e}")
                time.sleep(1)
    else:
        # Serial Mode
        logger.info(f"Connecting to serial port {args.port} at {args.baud} baud...")
        try:
            ser = serial.Serial(args.port, args.baud, timeout=1)
            time.sleep(2) # Wait for connection
            logger.info("Serial connected.")
        except serial.SerialException as e:
            logger.error(f"Failed to connect to serial port: {e}")
            return

        while True:
            try:
                if ser.in_waiting > 0:
                    line_bytes = ser.readline()
                    try:
                        line = line_bytes.decode('utf-8').strip()
                    except UnicodeDecodeError:
                        logger.warning(f"Decode error: {line_bytes}")
                        continue
                    
                    if not line:
                        continue
                        
                    result = process_line(line)
                    if result:
                        co2, hum = result
                        logger.info(f"Read: {co2},{hum}")
                        processor.process(co2, hum)
                        
                        if isinstance(processor, SessionProcessor) and processor.completed:
                            logger.info("Session targets reached. Stopping.")
                            break
                    else:
                        logger.warning(f"Invalid format: {line}")
                
                time.sleep(0.1) 
                
            except KeyboardInterrupt:
                logger.info("Stopping serial ingestion...")
                break
            except Exception as e:
                logger.error(f"Error in serial loop: {e}")
                time.sleep(1)
        
        ser.close()

    # Finish processing
    processor.finish()

def main():
    args = parse_args()
    db = get_database()
    
    logger.info(f"Starting CO2 ingestion for user: {args.user_id}")
    if args.session:
        logger.info("Mode: SESSION (Stabilization Detection)")
        processor = SessionProcessor(db, args.user_id)
    else:
        logger.info("Mode: STREAMING (Continuous Update)")
        processor = StreamingProcessor(db, args.user_id)
    
    run_loop(processor, args)

if __name__ == "__main__":
    main()
