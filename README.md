# Nairobi City Water & Sewerage Company (NCWSC)
## Water Quality Assurance & Laboratory Information Management System (waterLAB / QAD)

An enterprise-grade, real-time Laboratory Information Management System (LIMS) and Water Quality Control analytics platform developed for the Nairobi City Water & Sewerage Company (NCWSC).

---

## 🌟 Key Features

### 1. Real-time QC Analytical Worksheet
- **Hourly Cycle Management**: Multi-parameter sampling and analytical entry for Raw Water, Clarified Water, and Treated Water phases.
- **Dynamic Calculation & Validation**: Automated alkalinity, turbidity, pH, color, free/total residual chlorine (FRC/TRC) thresholds and compliance scoring.
- **Excel-Style Ergonomics**: Keyboard-driven navigation (<kbd>Enter</kbd> to save & advance, arrow keys for cross-cell navigation, automatic input masking).

### 2. Audio & Spoken Voice Notification System
- **Real-time Push Alerts**: Instant delivery of water quality alerts, shift notifications, and expiring cycle reminders over WebSockets (`/ws/alerts/`).
- **Reference Voice Cloning**: Persistent alert audio uses the selected `VoiceOver.sample_clip` as a voice reference through Chatterbox Turbo/Nano when the compatible runtime is installed in the Celery worker.
- **Honest Fallbacks**: When reference cloning is unavailable, regional Edge-TTS, gTTS, or offline pyttsx3 can still create audio. `VoiceAlert.voice_cloned` distinguishes cloned output from these stock voices. If a stored clip cannot autoplay, the **Voice** control remains available for replay and browser speech fallback.
- **Durable Inbox & Delivery**: Each alert event and recipient is stored before dispatch. Email, SMS, WhatsApp, Slack, and private WebSocket delivery results are tracked individually and retried after transient failures.
- **Timed Escalation**: Unacknowledged alerts are escalated after `tat_for_escalation`; later stages follow `escalation_timeout` and `escalation_policy`. Critical alerts can repeat their audio until acknowledged.
- **Dedicated "Voice" Controls**: Every notification item in the topbar bell dropdown includes an interactive **Voice** button to listen or re-listen on demand.

### 3. Persistent Fullscreen & PWA Experience
- **Seamless Navigation**: Fullscreen state is tracked via session tokens (`qad_fullscreen_active`). When navigating between worksheets, dashboards, and reports, the application automatically re-engages fullscreen on first user touch, click, or keystroke without needing manual toggles.
- **Progressive Web App (PWA)**: Certified web app manifest with `display: fullscreen` and `standalone` support.
- **True Kiosk / Desktop App Mode**: Installing as a PWA or launching in app mode (`chrome --app=...` / `msedge --app=...`) provides permanent, uninterrupted fullscreen operation across all page loads and reloads.

### 4. Operational Telemetry & Shift Handover
- **Shift Handover Engine**: Digital shift logs, supervisor assignment, checklist reconciliation, and handover approval workflows.
- **Jar Testing & Dosing Optimizer**: Coagulant dosage estimation, pH adjustment curves, and chlorine demand calculation.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11 or 3.12
- Redis Server (for Celery background workers and WebSockets channel layer)
- PostgreSQL (Production) or SQLite (Development)

### Local Environment Setup

1. **Activate Virtual Environment**:
   ```powershell
   # Windows PowerShell
   ..\Scripts\Activate.ps1
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and configure your database, secret key, and Redis credentials:
   ```env
   DEBUG=True
   SECRET_KEY=your-secure-secret-key
   REDIS_URL=redis://127.0.0.1:6379/0
   ```

4. **Apply Database Migrations**:
   ```bash
   python manage.py migrate
   ```

5. **Start ASGI Server (WebSockets & HTTP)**:
   ```bash
   daphne -b 0.0.0.0 -p 8000 qad.asgi:application
   ```
   *(Or for standard HTTP development: `python manage.py runserver 0.0.0.0:8000`)*

6. **Start Celery Worker & Beat (Background Tasks & Scheduled Alerts)**:
   ```bash
   # Terminal 1: Worker
   celery -A qad worker -l info -P threads

   # Terminal 2: Beat Scheduler
   celery -A qad beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
   ```

---

## 🖥️ Fullscreen Mode: Operation & Best Practices

To provide technicians with distraction-free monitoring in laboratory environments:

1. **Automatic In-Browser Retention**:
   - The application automatically expands to full viewport dimensions (`app-fullscreen`).
   - As you click navigation links or buttons, your fullscreen state is remembered and automatically resumed on your very first action on the new page.
   - If you press <kbd>Esc</kbd> to leave fullscreen, the app respects your decision and will not force fullscreen until your next internal navigation.

2. **Permanent Frameless Mode (Recommended for Lab Desktops)**:
   - **Method A (PWA Installation)**: Open the dashboard in Google Chrome or Microsoft Edge, click the **Install App** icon in the address bar (or menu > *Apps* > *Install NCWSCwaterLAB*). Launching the installed app will run in full native window mode without tabs, address bars, or navigation resets.
   - **Method B (Dedicated Desktop Shortcut)**:
     ```cmd
     # Microsoft Edge
     msedge.exe --app=http://localhost:8000/qc/dashboard/ --start-fullscreen

     # Google Chrome
     chrome.exe --app=http://localhost:8000/qc/dashboard/ --start-fullscreen
     ```

---

## 🔔 Voice & Notification Architecture

```
[ Water Quality Event / Cycle Expiry ]
                  │
                  ▼
         alerts/engine.py
                  │
        Persist AlertState + recipient AlertNotification rows
                   │
       ┌───────────┴─────────────┐
       ▼                         ▼
  Delivery outbox          VoiceAlert task
  per-channel retries      reference clone → fallback TTS
       │                         │
       └───────────┬─────────────┘
                   ▼
       Private recipient WebSocket
       + scoped dashboard inbox
                   │
       ┌───────────┴─────────────┐
       ▼                         ▼
  Audio playback          Acknowledge / TAT timer
  and replay controls     → staged escalation
```

- **Cloning runtime**: Chatterbox is loaded lazily by the voice task and its Turbo/Nano model is cached in the worker. The repository pins NumPy 2.2.2 and Transformers 4.48.2, while the upstream package currently pins a different set. Install a compatible voice runtime in the worker environment or align the dependency pins before enabling reference cloning; a plain `pip install` into the existing environment can conflict. Without that runtime, generated files are explicitly recorded as non-cloned fallbacks.
- **Audio autoplay**: Browsers may block automatic playback. Users can replay stored audio with the **Voice** control; if a notification has no audio file, that control uses browser speech synthesis.

---

## 📂 Repository Structure

- `accounts/` — User authentication, role-based access, and notification center templates.
- `alerts/` — Alert rules engine, voice profile management (`VoiceOver`), persistent voice alerts (`VoiceAlert`), and WebSocket consumers.
- `ca/` — Water Quality Compliance and Assessment dashboard, laboratory testing workflows.
- `core/` — Global styling (`base.css`, `theme.css`, `header.css`, `dropdown.css`), fullscreen manager (`fullscreen.js`), and notification script (`global_notifications.js`).
- `qc/` — Quality Control hourly sampling schedules, analytical worksheet forms, and real-time outbox processor.
- `sc/` — Shift roster, supervisor assignment, and shift handover workflows.
- `t/` — Treatment Plant master configurations and operational parameters.

---

## 📄 License & Confidentiality
Proprietary software developed for Nairobi City Water & Sewerage Company (NCWSC). All rights reserved.
