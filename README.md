# 🅿️ ParkVision AI

> An intelligent parking lot monitoring system that uses computer vision and AI to detect and track parking space occupancy in real time — served through a modern interactive web dashboard.

---

## What is ParkVision AI?

ParkVision AI is a full-stack smart parking solution designed to automate the monitoring of parking lots using artificial intelligence. Instead of relying on physical sensors or manual observation, the system analyzes video feeds using computer vision models to determine which parking spaces are occupied and which are free — in real time.

The results are exposed through a REST API and visualized on a web dashboard that combines interactive maps, 3D parking lot views, and live occupancy statistics. The system is designed to be scalable, containerized, and easy to deploy in real-world urban or commercial parking environments.

---

## How It Works

At its core, ParkVision AI processes video input from parking lot cameras. Each frame is analyzed by a computer vision pipeline that identifies individual parking spots and classifies them as occupied or free. These predictions are served through a FastAPI backend and consumed by a Next.js frontend that renders the data visually for operators or end users.

Experiments and model iterations are tracked using **MLflow**, allowing the team to compare model versions, log metrics, and manage the lifecycle of AI models in a structured way. This makes the system not just a production tool but also a platform for continuous model improvement.

---

## Key Features

- **Real-time occupancy detection** from video streams using computer vision
- **REST API** built with FastAPI, served via Uvicorn on port 8000
- **Interactive web dashboard** with live parking data
- **Map-based visualization** using Leaflet and React-Leaflet
- **3D parking lot view** powered by Three.js and React Three Fiber
- **ML experiment tracking** with MLflow for model versioning and performance monitoring
- **Fully Dockerized** — both backend and frontend can be spun up with a single command
- **Modern tooling** — `uv` for Python dependency management, Next.js App Router, Tailwind CSS v4

---

## Tech Stack

### Backend

| Technology | Role |
|-----------|------|
| Python 3.12 | Core language |
| FastAPI | REST API framework |
| Uvicorn | ASGI server |
| MLflow | Experiment tracking & model registry |
| uv | Fast, reproducible package management |
| Docker + Docker Compose | Containerization & orchestration |
| pytest | Testing |

### Frontend

| Technology | Role |
|-----------|------|
| Next.js 16 (App Router) | React framework |
| React 19 | UI library |
| Three.js + React Three Fiber | 3D parking visualizations |
| Leaflet + React-Leaflet | Interactive geographic maps |
| Tailwind CSS v4 | Utility-first styling |
| Lucide React | Icon library |

---

## Getting Started

### Prerequisites

- Python 3.12+ and [`uv`](https://github.com/astral-sh/uv)
- Node.js 18+ and npm (or yarn / pnpm / bun)
- Docker and Docker Compose (for containerized deployment)

### Run the Backend

```bash
git clone https://github.com/ElbahiaBoudal/ParkVision_AI.git
cd ParkVision_AI

uv sync
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

API available at → `http://localhost:8000`

### Run the Frontend

```bash
git clone https://github.com/ElbahiaBoudal/parking_AI_front-.git
cd parking_AI_front-

npm install
npm run dev
```

Dashboard available at → `http://localhost:3000`

### Run with Docker

```bash
cd ParkVision_AI
docker compose up --build
```

---

## Repositories

| Repo | Link |
|------|------|
| Backend (AI + API) | [ParkVision_AI](https://github.com/ElbahiaBoudal/ParkVision_AI) |
| Frontend (Dashboard) | [parking_AI_front-](https://github.com/ElbahiaBoudal/parking_AI_front-) |

---

## Author

**Elbahia Boudal** — [@ElbahiaBoudal](https://github.com/ElbahiaBoudal)
