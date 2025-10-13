import os
from typing import Optional

from dotenv import load_dotenv
import serial  # pyserial


load_dotenv()


def open_serial_port() -> serial.Serial:
    port = os.getenv("SERIAL_PORT", "COM3")
    baud = int(os.getenv("SERIAL_BAUD", "9600"))
    timeout = float(os.getenv("SERIAL_TIMEOUT", "1.0"))
    return serial.Serial(port=port, baudrate=baud, timeout=timeout)


def read_line(ser: Optional[serial.Serial] = None) -> Optional[str]:
    if ser is None:
        ser = open_serial_port()
    raw = ser.readline()
    try:
        return raw.decode("utf-8").strip()
    except Exception:
        return None


