# AGENTS.md

This file provides guidance to Qoder (qoder.com) when working with code in this repository.

## Project Overview

A full-featured intelligent video analysis SaaS platform (YouTube Video Intelligent Summary System) with user authentication, video processing, AI analysis, and data persistence. Integrates Alibaba Cloud AI services (DashScope) and Supabase for backend services.

**Primary Stack:**
- **Frontend**: React 18 + TypeScript + Vite + shadcn/ui + Tailwind CSS
- **Backend**: FastAPI + Python 3.9+
- **AI Services**: Alibaba Cloud DashScope (Paraformer-v2 for transcription, Qwen3-VL-Flash for video understanding)
- **Storage**: Alibaba Cloud OSS (Object Storage Service)
- **Database**: Supabase (Auth + PostgreSQL + Storage)

## Common Commands

### Development

**Start complete development environment (frontend + backend):**
```bash
./start_dev.sh  # Uses tmux to run both services
# Frontend: http://localhost:8080
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

**Or start services separately:**
```bash
# Terminal 1: Backend
./app/tests/run_fastapi.sh
# or
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Frontend
./app/tests/run_frontend.sh
# or
cd frontend && npm run dev
```

**Gradio quick processing interface (alternative UI):**
```bash
cd backend
./run_gradio.sh
# Access: http://127.0.0.1:7860
```

### Frontend Commands

```bash
cd frontend
npm install           # Install dependencies
npm run dev          # Start dev server (port 8080)
npm run build        # Production build
npm run build:dev    # Development build
npm run lint         # Run ESLint
npm run preview      # Preview production build
```

### Backend Commands

```bash
cd backend
pip install -r requirements.txt  # Install dependencies

# Start FastAPI server
./run_fastapi.sh
# or with options
./run_fastapi.sh --port 8000 --host 0.0.0.0 --no-reload

# Run all backend tests
pytest app/tests/

# Run specific test files
pytest app/tests/test_video_service.py
pytest app/tests/test_paraformer_service.py
pytest app/tests/test_supabase_service.py
pytest app/tests/test_chat_service.py
pytest app/tests/test_complete_pipeline.py
pytest app/tests/test_full_system_integration.py

# Run pipeline tests
./app/tests/run_complete_pipeline_test.sh
./app/tests/run_pipeline_test.sh
./app/tests/run_transcription_test.sh
```

### Testing

```bash
# Full integration tests (frontend + backend)
./test_integration.sh

# System integration tests (auth, video processing, etc.)
./app/tests/run_system_integration_test.sh

# Verify Supabase integration
./app/tests/run_supabase_verification.sh
```

### Database

```bash
# Initialize Supabase schema
cd backend
python scripts/init_supabase_schema.py
# Or manually execute: backend/sql/schema_v1.sql in Supabase SQL Editor
```

## Architecture

### Core Processing Pipeline

The system follows a complete video processing pipeline coordinated by `AliyunVideoProcessingPipeline` (backend/app/services/pipeline_service.py):

1. **Video Download/Upload** → video_service.py (yt-dlp for YouTube, local upload support)
2. **Keyframe Extraction** → video_service.py (PySceneDetect for scene detection)
3. **Audio Transcription** → paraformer_service.py (Alibaba Paraformer-v2 with speaker diarization, millisecond-level timestamps)
4. **Video Understanding** → llm_service.py (Qwen3-VL-Flash multimodal analysis)
5. **Cloud Storage** → oss_service.py (Alibaba Cloud OSS for videos, keyframes, metadata)
6. **Data Persistence** → supabase_service.py (User data, video records, processing results)
7. **Interactive Chat** → chat_service.py (Q&A based on transcript content)

### Backend Structure

- `app/main.py` - FastAPI application entry point, middleware, CORS configuration
- `app/api/routes/` - API endpoints
  - `auth.py` - Authentication (signup, signin, Google OAuth)
  - `video.py` - Video processing routes (process, status, user videos)
  - `analysis.py` - Analysis routes (chat/Q&A)
- `app/services/` - Business logic layer
  - `pipeline_service.py` - Main orchestration of video processing workflow
  - `video_service.py` - Video download (yt-dlp) and keyframe extraction (PySceneDetect)
  - `paraformer_service.py` - Paraformer-v2 transcription with speaker diarization
  - `llm_service.py` - Qwen3-VL-Flash video summarization and understanding
  - `oss_service.py` - Alibaba Cloud OSS operations (upload, download, URL generation)
  - `supabase_service.py` - Database operations, user management, quota tracking
  - `chat_service.py` - Chat/Q&A service based on transcript
- `app/models/` - Pydantic data models for validation
- `app/core/` - Core configuration, logging
- `app/tests/` - Unit and integration tests

### Frontend Structure

- `src/main.tsx` - Application entry point
- `src/App.tsx` - Root component with routing
- `src/pages/` - Page components (Landing, Dashboard, Auth, etc.)
- `src/components/` - Reusable UI components
  - `auth/` - Authentication components
  - `dashboard/` - Dashboard components
  - `chat/` - Chat interface components
  - `ui/` - shadcn/ui component library
- `src/services/` - API client layer for backend communication
- `src/integrations/supabase/` - Supabase client configuration
- `src/contexts/` - React Context for state management
- `src/hooks/` - Custom React hooks

### Key Dependencies

**Backend:**
- `fastapi` - Web framework
- `gradio` - Alternative ML interface
- `yt-dlp` - YouTube video downloader
- `scenedetect[opencv]` - PySceneDetect for keyframe extraction
- `oss2` - Alibaba Cloud OSS SDK
- `dashscope` - Alibaba Cloud DashScope SDK (Paraformer-v2, Qwen3-VL-Flash)
- `supabase` - Supabase Python SDK
- `pytest` + `pytest-asyncio` - Testing framework

**Frontend:**
- `react` + `react-dom` - UI framework
- `react-router-dom` - Routing
- `@supabase/supabase-js` - Supabase client
- `@tanstack/react-query` - Server state management
- `shadcn/ui` + `@radix-ui/*` - UI component library
- `tailwindcss` - Styling
- `vite` - Build tool
- `eslint` - Linting

### Environment Configuration

**Root `.env` file** (required by backend):
```bash
# Alibaba Cloud OSS
OSS_ACCESS_KEY_ID=...
OSS_ACCESS_KEY_SECRET=...
OSS_BUCKET=...
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com

# Alibaba Cloud AI (DashScope)
QWEN_API_KEY=...  # or DASHSCOPE_API_KEY

# Supabase
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_KEY=...

# Google OAuth (optional)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

**Frontend `.env.development`**:
```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
```

### Test Organization

Per `.qoder/rules/sh_md_file_rule.md`:
- All `.sh` test scripts go in `app/tests/`
- All test-related markdown documentation goes in `app/tests/docs/`

### Network Proxy Configuration

The backend scripts configure network proxies for development:
```bash
export https_proxy=http://127.0.0.1:33210
export http_proxy=http://127.0.0.1:33210
export all_proxy=socks5://127.0.0.1:33211
```

## Notes

- The system uses **Paraformer-v2** (not SenseVoice) for transcription - provides 95% accuracy, millisecond timestamps, and speaker diarization
- Video processing is async and coordinated through the pipeline service
- User quota management supports Free/Pro/Enterprise subscription tiers
- The platform supports both Chinese and English documentation
- Frontend uses port 8080, backend uses port 8000 by default
- All cloud resources (videos, keyframes, metadata) are stored in Alibaba Cloud OSS
- Supabase handles user authentication (email + Google OAuth), database persistence, and storage
