App ↔ Backend flow
Kotlin App
   │
   ├── Capture face using CameraX
   │
   ├── Send image/frame
   ▼
FastAPI
   │
   ├── OpenCV preprocessing
   ├── InsightFace detection + embedding
   ├── pgvector search
   └── Attendance logic
   ▼
Response
   │
   └── {employee, confidence, attendance_status}
For speed
MVP:
Android CameraX
      ↓
FastAPI
      ↓
InsightFace
      ↓
PostgreSQL + pgvector

Later, for lower latency:

Android
├── CameraX
├── Face Detection
└── Face Embedding model
        ↓
    FastAPI
        ↓
    pgvector + attendance

That hybrid approach is the better optimization path: do detection/embedding on-device and keep identity/attendance/business logic on the backend.