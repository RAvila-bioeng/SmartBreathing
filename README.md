# SmartBreathing – AI-Powered Personal Trainer & Physiological Dashboard

> **SmartBreathing** is a university prototype that combines **wearable sensing**, **AI-driven training plans** and a **clinical-style dashboard** to help athletes understand how their body responds to exercise.
> It is **not** a medical device and must not be used for diagnosis or clinical decision-making.

---

## 🚀 What the prototype does

### 1. AI-assisted training routines

* Central **exercise database** with metadata (muscle group, equipment, intensity, sport, level, “can be done at home”, etc.).
* A Python engine (`SmartBreathingAI`) builds **personalised routines** from that database using:

  * User profile (age, weight, sex, sport, level, limiting condition…)
  * User goals (gain muscle, lose weight, mixed, etc.).
* Endpoints used by both the web app and the Telegram bot:

  * `POST /api/ai/generate-routine/{user_id}` – generate a full routine.
  * `POST /api/ai/alternative-exercise/{user_id}` – swap one exercise for a compatible alternative (same muscle group / equipment / constraints).

### 2. Web dashboard for measurements

After logging into the **measurement panel**, each user can:

* See their **demographic profile** and latest measurements.
* Enter manual values (e.g. weight, resting heart rate, waist).
* Visualise:

  * Latest **ECG** trace and heart rate.
  * Latest **CO₂ session** with:

    * Full raw CO₂ curve (ppm).
    * Automatically detected **stabilised points** for each breathing plateau.
    * Linear regression line summarising the session.
  * Associated **humidity** curve from the SCD30.

Data comes from MongoDB collections like `users`, `Mediciones`, `ecg` and `co2`.

### 3. Automatic CO₂ session when a user logs in

When a user logs into the measurement dashboard:

1. The backend endpoint `POST /api/check_user` validates the user (name, surname, 4-digit code).

2. If the user exists, the backend:

   * Returns the user id to the frontend.
   * **Spawns a background process** that launches:

   ```bash
   python ingestion/read_co2_scd30.py --user-id <USER_ID> --session
   ```

3. The ingestion script:

   * Reads `CO2,Humidity` from an **Arduino Uno + SCD30** over serial.
   * Detects a **baseline** and then **3 stabilised plateaus** while the user breathes in a mask.
   * Stores:

     * Full raw signal + humidity in the `co2` collection.
     * Only the stabilised points (`co2_1…co2_n`, `hum_1…hum_n`) into the user’s latest document in `Mediciones`.

4. The frontend polls `GET /api/co2/last-session/{user_id}` and updates the graphs in real time.

---

##  High-level architecture

**Hardware & ingestion**

* Arduino Uno + **SCD30 CO₂ sensor** (and other sensors such as ECG and SpO₂ in the broader prototype).

* Arduino prints serial lines in the format:

  ```text
  CO2,Humidity
  865.0,42.6
  ...
  ```

* Python ingestion scripts:

  * `ingestion/read_co2_scd30.py` – session-based CO₂ + humidity ingestion with plateau detection.
  * (Additional helpers for serial testing.)

**Backend**

* **FastAPI** application in `backend/app`:

  * User management (`/api/users/*`, `/api/check_user`).
  * Measurement storage & retrieval (`/api/mediciones`, `/api/co2/last-session/{user_id}`).
  * ECG endpoints via a dedicated router (`/api/ecg/*`).
  * AI training endpoints (`/api/ai/*`).
  * Serves the static frontend HTML files (measurement dashboard, login, new user forms).

**Database**

* **MongoDB** (via Docker compose).
* Main collections:

  * `users` – demographic profile, limiting conditions, preferences, etc.
  * `Mediciones` – clinical-style measurement documents (weight, SpO₂, HR, CO₂ plateaus, etc.).
  * `ecg` – raw ECG signal and sampling info.
  * `co2` – raw CO₂ + humidity sessions with stabilised indices.
  * Exercise / routine collections for the AI engine.

**User interfaces**

1. **Telegram bot**

   * Guides the user through registration and profile questions.
   * Talks to the backend AI engine to generate and adapt routines.
2. **Web dashboard**

   * Static HTML/JS frontend (`frontend/`) served by FastAPI.
   * Designed for coaches / parents / clinicians to view measurements and graphs.

---

## 📂 Repository structure

```text
SmartBreathing/
├── backend/                 # FastAPI backend + AI engine
│   ├── app/
│   │   ├── main.py          # API endpoints + static frontend serving
│   │   ├── ai_engine.py     # SmartBreathingAI: routine generation logic
│   │   ├── ecg.py           # ECG API router
│   │   ├── models.py        # Pydantic models
│   │   └── db.py            # MongoDB connection helper
│   └── requirements.txt
├── bot/                     # Telegram bot
│   ├── bot.py
│   └── requirements.txt
├── frontend/                # Measurement dashboard + login + registration
│   ├── index.html
│   ├── login.html
│   ├── menu.html
│   ├── nuevo_usuario_paso1.html
│   └── nuevo_usuario_paso2.html
├── ingestion/               # Sensor ingestion scripts
│   ├── read_co2_scd30.py    # CO₂ + humidity session ingestion (SCD30)
│   ├── serial_reader.py     # Generic serial testing helper
│   └── requirements.txt
├── docker-compose.yml       # MongoDB service
├── Makefile                 # Helper commands (backend, bot, ingestion, docker)
└── ...
```

*(Some filenames may be omitted here for brevity; see the repo for full details.)*

---

##  Tech stack

| Area         | Technologies                               |
| ------------ | ------------------------------------------ |
| Backend API  | Python, FastAPI, Uvicorn                   |
| Data storage | MongoDB (Docker Compose)                   |
| Frontend     | Static HTML, CSS, vanilla JS               |
| Bot          | Python + Telegram Bot API                  |
| Hardware     | Arduino Uno, SCD30 CO₂ sensor, ECG module… |
| Ingestion    | Python + pyserial                          |

---

##  CO₂ session algorithm (SCD30)

The CO₂ ingestion script (`ingestion/read_co2_scd30.py`) is designed to behave like a **lab protocol**:

1. **Baseline**

   * First valid sample after connecting is stored as **baseline** (normal breathing).
2. **Buffers & windows**

   * Keeps a sliding buffer of recent CO₂ values.
   * Compares the mean of the last 3 samples vs. the previous 3.
3. **Stability check**

   * If the absolute difference between both means is below a ppm threshold, the segment is considered **stabilised**.
   * Additional checks:

     * Minimum number of samples between stabilised plateaus.
     * Minimum change in CO₂ between consecutive plateaus (to avoid duplicates).
4. **Stopping criterion**

   * Session ends automatically after **baseline + 3 valid plateaus** (4 stabilised points total).
5. **Database writes**

   * Full `senal` and `humedad` arrays (raw curves).
   * `co2_estabilizado`, `hum_estabilizada`, `indices_estabilizados`, `num_puntos`.
   * Updates `Mediciones` with `co2_1..co2_n`, `hum_1..hum_n` so the dashboard can use them directly.

This logic is robust enough to handle small fluctuations while still giving clear plateau points for the regression and dashboard plots.

---

## 🧾 Measurements API (summary)

Some of the most relevant endpoints:

* `GET /health`
  Simple health check.

* `POST /api/users/create`
  Create a new user from the registration forms.

* `POST /api/check_user`
  Login (name + surname + 4-digit code).
  **Side effect:** starts a CO₂ session ingestion process in the background.

* `POST /api/mediciones`
  Create or update a measurement document for a user.
  Protects the automatic CO₂ fields from being overwritten manually.

* `GET /api/mediciones?user_id=<id>`
  List recent measurements for a given user.

* `GET /api/co2/last-session/{user_id}`
  Return the most recent CO₂ session for plotting in the dashboard.

* `GET /api/ecg/latest/{user_id}`
  Get latest ECG signal for that user.

* `POST /api/ai/generate-routine/{user_id}`
  Generate a routine based on goals and the user profile.

* `POST /api/ai/alternative-exercise/{user_id}`
  Suggest an alternative for one exercise.

---

##  Getting started (local dev)

> The prototype is meant to be run locally (laptop + Arduino).
> Adjust paths and ports if you are on Windows vs. Linux.

### 0. Requirements

* **Python 3.11+**
* **Docker Desktop** (or any Docker runtime) for MongoDB
* **Git**
* (For full prototype) an **Arduino Uno** + **SCD30** wired and programmed to send `CO2,Humidity` at **115200 baud**.

### 1. Clone the repository

```bash
git clone https://github.com/RAvila-bioeng/SmartBreathing.git
cd SmartBreathing
```

### 2. Start MongoDB

```bash
docker compose up -d
```

MongoDB is exposed on `localhost:27017` with user `root` and password `example`.

### 3. Backend (FastAPI)

From the project root:

```bash
make install-backend   # creates backend/.venv and installs dependencies
make api               # runs Uvicorn at http://0.0.0.0:8000
```

Optional `backend/.env`:

```env
MONGODB_URI=mongodb://root:example@localhost:27017
MONGODB_DB=SmartBreathing
```

Check:

```bash
curl http://localhost:8000/health
```

### 4. Frontend (measurement dashboard)

The frontend is served directly by FastAPI as static files.

* With the backend running, open:

```text
http://localhost:8000/menu.html      # main menu
http://localhost:8000/login.html     # login for measurements
http://localhost:8000/index.html     # dashboard (after login)
```

### 5. Telegram bot (optional but recommended)

```bash
make install-bot
```

Create `bot/.env`:

```env
TELEGRAM_BOT_TOKEN=xxxxxxxx:yyyyyyyy
OPENAI_API_KEY=sk-...        
BACKEND_BASE_URL=http://localhost:8000
```

Run the bot:

```bash
make bot
```

The bot uses the backend to fetch user data and generate routines with `SmartBreathingAI`.

### 6. CO₂ ingestion – SCD30 + Arduino

Install ingestion dependencies:

```bash
make install-ingestion
```

Create an `.env` file (either in `ingestion/.env` or at project root, depending on how you run it) with the serial port of your Arduino, for example on Windows:

```env
CO2_SERIAL_PORT=COM4
```

#### Manual test

With the backend not necessarily running yet:

```bash
python ingestion/read_co2_scd30.py \
  --user-id <MONGODB_USER_ID> \
  --port COM4 \
  --baud 115200 \
  --session
```

Check MongoDB to confirm a new document in `co2` and updated fields in `Mediciones`.

#### Automatic test via dashboard login

1. Start MongoDB and the backend.
2. Ensure `CO2_SERIAL_PORT` is correctly set.
3. Open `http://localhost:8000/login.html`.
4. Log in with an existing user (name, surname, 4-digit code).
5. The backend will:

   * Start `read_co2_scd30.py` in the background.
   * Once the session finishes, the dashboard will show the new CO₂ graphs and humidity.

---

## 🤝 Contributing / extending

This project was developed as a **university prototype**.
If you want to extend it, some natural directions are:

* Add more sensors and ingestion scripts (e.g. continuous SpO₂ integration).
* Improve the AI engine (e.g. reinforcement from adherence data, more advanced personalisation).
* Enhance the dashboard with:

  * Exportable PDF reports.
  * Comparison between sessions.
  * Threshold alerts for risky values (only for research / non-medical use).
* Containerise the whole stack (backend + bot + ingestion) for easier deployment.

Pull requests and suggestions are welcome.

---

## ⚠️ Disclaimer

SmartBreathing is a **research / educational prototype**.
It is **not certified** as a medical device and must **not** be used to diagnose, treat, or monitor any medical condition in real patients. Use it only in controlled, non-clinical environments.
