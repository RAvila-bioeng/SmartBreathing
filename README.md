# SmartBreathing: Personal Trainer Inteligente Basado en IA

## 🧘‍♂️ Asistente Personalizado de Fitness y Salud Impulsado por Inteligencia Artificial

SmartBreathing es un proyecto innovador centrado en el desarrollo de un sistema de **Inteligencia Artificial (IA)** personalizado que actúa como un entrenador de salud y fitness para atletas. Nuestro objetivo principal es crear un modelo de IA capaz de ofrecer asesoramiento y rutinas de ejercicio optimizadas en tiempo real, basándose en datos fisiológicos y métricos detallados del usuario.

El sistema se alimenta de una **base de datos propietaria** que combina información demográfica (edad, peso, género, deporte preferido) con **datos fisiológicos en tiempo real** capturados a través de sensores (niveles de $CO_2$, saturación de oxígeno en sangre ($SpO_2$), y electrocardiograma ($ECG$)).

---

## ✨ Características Principales

* **Asesoramiento Personalizado en Tiempo Real:** Generación de respuestas y consejos de fitness contextualmente conscientes y optimizados para las necesidades individuales del usuario.
* **Monitoreo Fisiológico Avanzado:** Seguimiento de métricas clave como $CO_2$, $SpO_2$ y $ECG$ para evaluar el rendimiento metabólico, la eficiencia respiratoria y la salud cardiovascular.
* **Interacción a Través de Telegram:** Interfaz principal amigable y accesible mediante un **chatbot de Telegram** para consultas, generación y modificación de rutinas.
* **Gestión de Rutinas:** Permite a los usuarios solicitar nuevas rutinas de ejercicio o modificar las existentes, asegurando una adherencia óptima a los objetivos de fitness.
* **Arquitectura Escalable:** Uso de **MongoDB** para un almacenamiento flexible y escalable de los datos de series de tiempo de los sensores y perfiles de usuario.

---

## 🛠️ Arquitectura del Sistema

La arquitectura de SmartBreathing está diseñada de forma **modular**, asegurando un flujo de datos continuo desde la recolección hasta la interacción con el usuario.



### Capas de la Arquitectura

1.  **Capa de Recolección de Datos:**
    * Sensores y hardware especializados recogen datos fisiológicos y ambientales en tiempo real.
2.  **Capa de Procesamiento (Core):**
    * Un **portátil personal** actúa como el centro de cómputo, realizando la agregación de datos, el entrenamiento del modelo de IA ($TensorFlow/PyTorch$), y la inferencia.
3.  **Capa de Almacenamiento:**
    * **MongoDB** es la base de datos NoSQL elegida para el almacenamiento persistente de perfiles de usuario, lecturas de sensores de series de tiempo y la biblioteca de rutinas de ejercicio.
4.  **Capa de Interacción (Interfaz de Usuario):**
    * El **Bot de Telegram** es la interfaz principal para la comunicación en lenguaje natural.
    * Un **Sitio Web complementario** ofrece visualización de datos y acceso administrativo.
5.  **Capa de Mejora de IA:**
    * Integración potencial con aplicaciones de **OpenAI** para asistir en el desarrollo inicial del modelo o el ajuste fino ($fine-tuning$) sobre el conjunto de datos personalizado.

### Flujo de Datos

El flujo comienza con los sensores conectados a una placa **Arduino UNO**. Los datos brutos se transmiten al portátil (Core de Procesamiento) para su procesamiento y se almacenan en **MongoDB**. El modelo de IA extrae información de esta base de datos para generar respuestas y consejos, que finalmente se entregan al usuario a través del Bot de Telegram o el Sitio Web.

---

## ⚙️ Componentes Detallados del Proyecto

| Componente | Función Principal | Rol en el Sistema |
| :--- | :--- | :--- |
| **Máscara, Tubo y Cinta Métrica** | Recolección de datos respiratorios y medidas físicas. | Integrado con el sensor de $CO_2$ para datos de volumen y patrón respiratorio. |
| **Sensor de $CO_2$** | Monitoreo de los niveles de dióxido de carbono en el aire exhalado. | Indica la actividad metabólica, la fatiga y la eficiencia respiratoria durante el ejercicio. |
| **Arduino UNO** | Microcontrolador de interfaz y recolección de datos brutos. | Recibe datos de los sensores ($CO_2$, Pulsioxímetro, $ECG$) y los transmite al portátil (vía serial/USB). |
| **Pulsioxímetro ($SpO_2$)** | Medición de la saturación de oxígeno en sangre y frecuencia cardíaca. | Esencial para monitorear el rendimiento aeróbico y la seguridad del usuario (detección de hipoxia). |
| **$ECG$ + Electrodos** | Captura de datos de electrocardiograma. | Seguimiento del ritmo cardíaco y evaluación de la salud cardiovascular durante el esfuerzo. |
| **Portátil Personal** | Núcleo de Computación y Procesamiento. | Ejecuta scripts de ingestión de datos, entrena el modelo de IA y aloja los servicios de API para el bot. |
| **MongoDB** | Almacenamiento NoSQL de datos persistentes. | Guarda perfiles de usuario, series de tiempo de sensores y la biblioteca de rutinas. |
| **Aplicación OpenAI** | Herramienta de Soporte y Mejora del Modelo de IA. | Se utiliza para el desarrollo inicial del modelo y el ajuste fino ($fine-tuning$) con datos personalizados. |

---

## 💻 Tecnologías Utilizadas

| Categoría | Tecnología/Herramienta |
| :--- | :--- |
| **Hardware/Microcontrolador** | Arduino UNO |
| **Base de Datos** | MongoDB (NoSQL) |
| **Frameworks de IA** | TensorFlow / PyTorch (Potencialmente) |
| **Plataforma de Interacción**| Telegram Bot API |
| **Soporte/Mejora de IA** | API de OpenAI |
| **Lenguajes de Programación**| Python (Probable para IA/Backend) |

---

## 🚀 Puesta en Marcha (Próximamente)

### Requisitos

- Docker Desktop instalado y corriendo
- Python 3.11+

### 1) Base de datos (MongoDB)

```bash
docker compose up -d
```

MongoDB expone `localhost:27017` con usuario `root` y password `example`.

### 2) Backend (FastAPI)

1. Crear entorno e instalar dependencias:
   ```bash
   make install-backend
   ```
2. Ejecutar API en desarrollo:
   ```bash
   make api
   ```
3. Probar salud:
   ```bash
   curl http://localhost:8000/health
   ```

Variables de entorno opcionales (crear `backend/.env`):

```
MONGODB_URI=mongodb://root:example@localhost:27017
MONGODB_DB=smartbreathing
```

### 3) Bot de Telegram

1. Crear bot y obtener `TELEGRAM_BOT_TOKEN` (BotFather).
2. Instalar dependencias:
   ```bash
   make install-bot
   ```
3. Crear archivo `bot/.env` con:
   ```
   TELEGRAM_BOT_TOKEN=xxxxxxxx:yyyyyyyy
   ```
4. Ejecutar bot:
   ```bash
   make bot
   ```

### 4) Frontend (Dashboard)

1. Ejecutar servidor de desarrollo:
   ```bash
   make frontend
   ```
2. Abrir http://localhost:3000 en el navegador

### 5) Ingesta desde Arduino (serial)

1. Instalar dependencias:
   ```bash
   make install-ingestion
   ```
2. Configurar `ingestion/.env` (opcional):
   ```
   SERIAL_PORT=COM3
   SERIAL_BAUD=9600
   SERIAL_TIMEOUT=1.0
   ```
3. Usar `ingestion/serial_reader.py` para pruebas de lectura.

### 6) Estructura del Proyecto

```
SmartBreathing/
├── backend/           # API FastAPI + IA
│   ├── app/
│   │   ├── main.py    # Endpoints principales
│   │   ├── models.py  # Modelos de datos
│   │   ├── ai_engine.py # Motor de IA
│   │   └── db.py      # Conexión MongoDB
│   └── requirements.txt
├── bot/               # Bot de Telegram
│   ├── bot.py
│   └── requirements.txt
├── frontend/          # Dashboard web
│   └── index.html
├── ingestion/         # Lectura de sensores Arduino
│   ├── serial_reader.py
│   └── requirements.txt
├── docker-compose.yml # MongoDB
└── Makefile          # Comandos de desarrollo
```

### 7) API Endpoints Principales

- `GET /` - Dashboard frontend
- `GET /health` - Estado del sistema
- `POST /api/users/` - Crear usuario
- `GET /api/users/{telegram_id}` - Obtener usuario
- `POST /api/sensors/reading` - Enviar datos de sensores
- `GET /api/sensors/readings/{user_id}` - Obtener lecturas
- `GET /api/analysis/{user_id}` - Análisis fisiológico
- `GET /api/recommendations/{user_id}` - Recomendaciones IA

## 🤝 Contribución

* [Guía sobre cómo otros desarrolladores pueden contribuir al proyecto.]
* ...
