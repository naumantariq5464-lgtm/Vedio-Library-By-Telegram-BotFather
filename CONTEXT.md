# Video Library Project Context & Architecture Specification

> **Notice for AI Assistants & Developers**: This document serves as the single source of truth for the Video Library application architecture, data models, API contracts, security guidelines, and development roadmap. Always consult this document before adding, modifying, or refactoring code.

---

## 1. Project Overview

The **Video Library Website** is a modern, single-page video platform designed for direct, seamless video consumption. The system allows an Administrator to upload videos via a simple Admin Panel. Uploaded media files are stored securely in a private Telegram Channel using the Telegram Bot API, while metadata is stored in a PostgreSQL database.

The application features two distinct interfaces:
1. **Public User Website**: A public, single-page dashboard featuring a dark black-and-red design where visitors can browse and stream uploaded videos. No user registration, login, or account creation is required.
2. **Admin Panel**: A lightweight interface accessible via a hidden/discreet trigger where the administrator authenticates and manages video uploads/deletions.

---

## 2. Project Goals

* **Zero-friction Video Access**: Visitors should be able to view available videos immediately without mandatory signup or authentication.
* **Cost-Effective Scalable Storage**: Utilize Telegram private channels as an infinite, high-capacity media store while using PostgreSQL exclusively for metadata indexing.
* **Modern Black & Red Aesthetic**: Deliver a visually striking UI using near-black backgrounds, high-contrast red accent buttons/glows, sleek dark-gray video cards, clean typography, and smooth transitions.
* **Atomic Upload & Data Consistency**: Ensure that media is only committed to the database after successful verification and upload to Telegram, preventing orphaned or broken video cards.
* **Decoupled Architecture**: Maintain strict separation between media storage (Telegram), metadata storage (PostgreSQL), server logic (FastAPI), and presentation (React).

---

## 3. Technology Stack

| Layer | Technology | Rationale / Details |
| :--- | :--- | :--- |
| **Frontend Framework** | React.js (Vite) | Single-page reactive application structure with stateful UI components. |
| **Styling** | Vanilla CSS / Tailwind CSS | Black & red modern palette (`#0a0a0a` background, `#e50914` primary red accents, `#181818` card containers). |
| **Backend Framework** | Python 3.11+ / FastAPI | High-performance asynchronous REST API framework with native Pydantic validation. |
| **Database ORM** | SQLAlchemy 2.0 (Async) + Alembic | Asynchronous PostgreSQL ORM for schema migration and query handling. |
| **Database Host** | PostgreSQL (Neon serverless) | Cloud PostgreSQL for metadata storage (IDs, titles, Telegram keys, timestamps). |
| **Media Storage** | Telegram Bot API + Telegram Private Channel | Unlimited media file storage hosted inside a private Telegram channel. |
| **Authentication** | Custom Admin Session / JWT | Secure admin access verified against backend environment variables (`ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH`). |
| **Video Delivery** | HTML5 `<video>` + FastAPI Streaming Proxy | Backend proxy stream handling HTTP Range requests (`206 Partial Content`) for seeking. |

---

## 4. System Architecture

The overall system architecture decouples user presentation, administrative uploads, data indexing, and media storage.

```mermaid
graph TD
    subgraph Admin Domain
        Admin[Admin User]
        AdminPanel[Admin React Panel]
    end

    subgraph Public Domain
        User[Public Viewer]
        PublicSite[Public React Website]
    end

    subgraph Backend Layer
        API[FastAPI Server]
        AuthModule[Auth & Security Module]
        StreamProxy[Media Streaming Proxy]
    end

    subgraph Data & Storage Layer
        DB[(PostgreSQL - Neon)]
        TgBot[Telegram Bot API]
        TgChannel[Private Telegram Channel]
    end

    Admin -->|Login & Upload Video| AdminPanel
    AdminPanel -->|POST /admin/videos| API
    API --> AuthModule
    API -->|Upload Media| TgBot
    TgBot -->|Store File| TgChannel
    TgBot -->|Return file_id & message_id| API
    API -->|Save Metadata| DB

    User -->|Browse Videos| PublicSite
    PublicSite -->|GET /videos| API
    API -->|Fetch Metadata| DB
    User -->|Watch Video| PublicSite
    PublicSite -->|GET /videos/:id/stream| StreamProxy
    StreamProxy -->|Fetch Media Bytes| TgBot
    StreamProxy -->|HTTP 206 Stream| PublicSite
```

---

## 5. Complete Upload Data Flow

The upload sequence guarantees that media is stored safely in Telegram before any record is created in PostgreSQL.

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant FE as React Admin Panel
    participant BE as FastAPI Backend
    participant TG as Telegram Bot API
    participant DB as PostgreSQL Database

    Admin->>FE: Select file & enter Video Title
    Admin->>FE: Click "Upload Video"
    FE->>BE: POST /admin/videos (Multipart Form Data + Bearer Token)
    BE->>BE: Verify Admin JWT Token & Validate File Type/Size
    alt Invalid Auth or File
        BE-->>FE: 401 Unauthorized or 400 Bad Request
    else Valid Request
        BE->>TG: sendDocument / sendVideo (File + Bot Token)
        alt Telegram Upload Fails
            TG-->>BE: Error (API Error / Network Timeout)
            BE-->>FE: 502 Bad Gateway ("Telegram Upload Failed")
            Note over BE,DB: No DB Record Created
        else Telegram Upload Succeeds
            TG-->>BE: Response (file_id, message_id, channel_id)
            BE->>DB: INSERT INTO videos (title, telegram_file_id, telegram_message_id, channel_id, created_at)
            DB-->>BE: Returns generated Video record (id, title, created_at)
            BE-->>FE: 201 Created (Video metadata payload)
            FE-->>Admin: Display Upload Success Notification & Update Video List
        end
    end
```

---

## 6. Complete Video Playback Flow

Directly passing a Telegram `file_id` to an HTML5 `<video src="...">` element fails because `file_id` is an internal Telegram identifier, not a web URL. The FastAPI backend acts as a streaming proxy.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant FE as React Public Website
    participant BE as FastAPI Streaming Proxy
    participant DB as PostgreSQL Database
    participant TG as Telegram Bot API / Local Bot Server

    User->>FE: Click "Watch Video" on Card
    FE->>BE: GET /videos/{id}/stream (Headers: Range: bytes=0-)
    BE->>DB: SELECT * FROM videos WHERE id = {id}
    DB-->>BE: Video metadata (telegram_file_id)
    BE->>TG: Request file path via getFile(telegram_file_id)
    TG-->>BE: Return file_path (e.g. videos/file_123.mp4)
    BE->>TG: GET file download stream (range-aware HTTP request)
    TG-->>BE: Binary Byte Stream
    BE-->>FE: HTTP 206 Partial Content (Content-Range, Content-Type: video/mp4)
    FE->>User: Play video smoothly inside HTML5 Video Player
```

---

## 7. Telegram Storage Architecture

Telegram serves as a free, resilient media storage provider:
* **Private Channel**: Serves as the repository container for all media assets.
* **Telegram Bot**: Acts as the interface agent. The Bot must be added to the Private Telegram Channel with **Admin privileges** (specifically "Post Messages" permission).
* **Identifier Retrieval**: Upon calling `sendVideo` or `sendDocument`, Telegram's API returns a payload containing:
  - `file_id`: Unique persistent identifier for API file fetching.
  - `message_id`: ID of the channel post containing the media file.
  - `chat.id`: ID of the target private channel.

---

## 8. PostgreSQL Database Schema

The database stores metadata referencing Telegram media assets.

### `videos` Table DDL (SQLAlchemy Model Specification)

```sql
CREATE TABLE videos (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    telegram_file_id VARCHAR(512) NOT NULL,
    telegram_message_id BIGINT NOT NULL,
    channel_id VARCHAR(100) NOT NULL,
    file_size BIGINT DEFAULT 0,
    duration INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_videos_created_at ON videos(created_at DESC);
```

```mermaid
erDiagram
    VIDEOS {
        int id PK
        string title
        string telegram_file_id
        bigint telegram_message_id
        string channel_id
        bigint file_size
        int duration
        timestamp created_at
    }
```

---

## 9. Database Field Explanations

| Field Name | Type | Description & Purpose |
| :--- | :--- | :--- |
| `id` | Integer (PK) | Primary key generated automatically by PostgreSQL. Used by frontend for UI routing (`/videos/12`) and REST endpoints. |
| `title` | String | Human-readable title entered by the admin during upload. Rendered on public video cards. |
| `telegram_file_id` | String | Internal string key provided by Telegram API (e.g., `BAACAgABC...`). Used by backend proxy to request the file path. |
| `telegram_message_id` | BigInt | The specific message ID of the video post in the private Telegram Channel. Useful for media deletion or direct channel lookup. |
| `channel_id` | String | The unique identifier of the private Telegram Channel (e.g., `-1001987654321`). |
| `created_at` | Timestamp | Timestamp indicating when the video record was added to the database. |

### Key Distinction of Identifiers

* **Database ID (`id`)**: Local numeric key for application routes and relational lookups. Never exposed to Telegram.
* **Telegram File ID (`telegram_file_id`)**: An opaque string key used strictly with Telegram Bot API methods (like `getFile`) to fetch media stream URLs.
* **Telegram Message ID (`telegram_message_id`)**: The ID of the actual channel post. Required if invoking `deleteMessage` on Telegram when an admin deletes a video.
* **Telegram Channel ID (`channel_id`)**: The Target Chat ID representing the channel location where the file lives.

> **Crucial Rule**: Never store binary media data, plain-text admin credentials, or bot API tokens inside PostgreSQL.

---

## 10. Public Website Requirements

* **Layout & Palette**: Dark mode UI (`#0a0a0a` backdrop), subtle glassmorphism cards (`rgba(255, 255, 255, 0.03)`), `#e50914` red highlights on buttons/hover states.
* **Header / Navigation**: Branding logo ("VIDEO LIBRARY"), discreet admin link trigger in header or footer.
* **Hero / Search (V1 Simple)**: Sleek banner displaying title & quick instructions.
* **Video Grid**: Responsive CSS Grid (`repeat(auto-fill, minmax(280px, 1fr))`).
* **Video Cards**:
  - Dark container with subtle hover scale/border effect (`transform: translateY(-4px)`).
  - Video Title rendered clearly.
  - Video preview thumbnail or generic stylized media icon.
  - Prominent "Watch Video" red action button.
* **Modal / Player Page**: HTML5 `<video>` player supporting play/pause, seek bar, volume, full-screen mode, and native streaming via `/videos/{id}/stream`.
* **States**:
  - **Loading**: Skeleton shimmer cards during API fetch.
  - **Empty**: User-friendly message ("No videos available yet. Check back soon!") when grid is empty.
  - **Error**: Toast or alert message if API call fails.

---

## 11. Admin Panel Requirements

* **Discreet Access**: Triggered via a subtle button/icon on the public page leading to `/admin/login`.
* **Login Form**:
  - Email & Password fields.
  - Form validation with clear error messaging for incorrect credentials.
* **Dashboard Interface**:
  - **Upload Card**: Form containing Video Title (`<input type="text">`), File Picker (`<input type="file" accept="video/*">`), and "Upload Video" submit button.
  - **Upload Progress**: Real-time progress bar (%) showing upload advancement to FastAPI backend.
  - **Alerts**: Explicit success message ("Video uploaded and published successfully!") or error alert.
  - **Video Management Table**: List of uploaded videos displaying ID, Title, Upload Date, and a "Delete Video" action button with confirmation prompt.

---

## 12. Admin Authentication Design

* **Credential Storage**: Credentials defined in backend environment variables (`ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH`).
* **Password Verification**: Passwords hashed using `passlib` (Bcrypt or Argon2). Plaintext passwords must never be compared directly or committed to source control.
* **Session Management**: Upon successful login (`POST /admin/login`), FastAPI issues a Signed JSON Web Token (JWT) with an expiration window (e.g., 24 hours).
* **Route Protection**: FastAPI dependency `get_current_admin` parses the HTTP Authorization header (`Bearer <token>`). Unauthenticated requests to `/admin/*` return `401 Unauthorized`.
* **Hidden Button Clarification**: The hidden UI button is merely an access entry point for convenience, not a security boundary. Security is enforced strictly by backend JWT verification.

---

## 13. Backend API Endpoints

### Public Endpoints

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/videos` | Fetch list of public videos (ID, title, created_at) | No |
| `GET` | `/api/videos/{id}` | Fetch detailed metadata for a single video | No |
| `GET` | `/api/videos/{id}/stream` | Stream video content (supports HTTP Range `206`) | No |

### Admin Endpoints

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/admin/login` | Authenticate admin & return JWT access token | No |
| `POST` | `/api/admin/videos` | Accept file upload, upload to Telegram, store DB metadata | **Yes (JWT)** |
| `DELETE` | `/api/admin/videos/{id}` | Remove video record from DB and delete Telegram post | **Yes (JWT)** |

---

## 14. Frontend Structure and Responsibilities

Planned directory layout for the React frontend:

```text
frontend/
├── public/
├── src/
│   ├── assets/              # Icons, fallback thumbnails
│   ├── components/
│   │   ├── Navbar.jsx        # Public header & discreet admin entry
│   │   ├── VideoCard.jsx     # Card component for grid display
│   │   ├── VideoGrid.jsx     # Responsive grid layout
│   │   ├── VideoPlayer.jsx   # HTML5 media player modal/page
│   │   ├── LoadingSkeleton.jsx # Skeleton UI for loading state
│   │   └── ProtectedRoute.jsx# Auth wrapper for admin routes
│   ├── pages/
│   │   ├── Home.jsx          # Public single-page video dashboard
│   │   ├── AdminLogin.jsx    # Admin login screen
│   │   └── AdminDashboard.jsx# Upload form & video deletion list
│   ├── services/
│   │   └── api.js            # Axios/Fetch API client wrapper
│   ├── styles/
│   │   └── index.css         # Global dark black-and-red theme CSS
│   ├── App.jsx               # Routes and application state
│   └── main.jsx
├── package.json
└── vite.config.js
```

---

## 15. Telegram Bot Configuration

1. **Bot Creation**: Created via Telegram `@BotFather` to generate `TELEGRAM_BOT_TOKEN`.
2. **Channel Setup**: A private Telegram Channel created for hosting media files.
3. **Bot Authorization**: Bot added as Administrator to the private channel with privileges:
   - *Post Messages*: Required to send video files.
   - *Delete Messages*: Required to remove media when deleted from Admin panel.
4. **Channel ID Extraction**: Channel ID extracted (typically starting with `-100...`) and stored in `TELEGRAM_CHANNEL_ID`.

---

## 16. Environment Variables

Create a template file named `.env.example` in the backend root directory:

```env
# Database Configuration (Neon PostgreSQL)
DATABASE_URL=postgresql+asyncpg://user:password@ep-cool-host.neon.tech/videodb?sslmode=require

# Telegram Bot Credentials
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyZ
TELEGRAM_CHANNEL_ID=-1001987654321

# Admin Authentication
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD_HASH=$2b$12$eImiTXuWVxfM37uY4JANjO...

# JWT Secret & Security
SECRET_KEY=super_secret_jwt_signing_key_change_in_production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Server Settings
CORS_ORIGINS=http://localhost:5173,https://your-production-domain.com
```

> **Security Rule**: Never check `.env` into git. Store secrets in server environment variables in production.

---

## 17. Security Requirements

* **Credential Isolation**: Keep bot tokens, database passwords, and admin hashes strictly on the backend.
* **Input Validation**: Use FastAPI Pydantic models to sanitize video titles and validate parameters.
* **Upload Restrictions**: Limit uploaded file MIME types (`video/mp4`, `video/webm`, `video/mkv`) and max filesize.
* **CORS Restrictions**: Configure FastAPI `CORSMiddleware` to allow requests only from trusted frontend domains.
* **Rate Limiting**: Protect `/api/admin/login` against brute-force password guessing.
* **HTTPS**: Force TLS/HTTPS in production to prevent token interception.

---

## 18. Error Handling

* **Telegram API Failures**: If Telegram API returns an error or times out during upload, backend catches the exception, aborts database insertion, and returns `502 Bad Gateway`.
* **Database Errors**: Wrapped in transaction blocks (`session.rollback()`) to maintain consistency.
* **Missing Media (404)**: If a user requests a video ID that doesn't exist, return `404 Not Found`. If Telegram file path cannot be resolved, return `404 Media Unavailable`.
* **Session Expiry**: Expired JWT tokens yield `401 Token Expired`, automatically redirecting the admin to `/admin/login`.

---

## 19. Data Consistency and Upload Lifecycle

```mermaid
stateDiagram-v2
    [*] --> UploadInitiated: Admin Submits Form
    UploadInitiated --> Validating: Check MIME & Token
    Validating --> TelegramUploading: Validation Passed
    Validating --> Rejected: Invalid Input / Auth Failed

    TelegramUploading --> DatabaseIndexing: Telegram Returns file_id
    TelegramUploading --> OrphanCleanup: Telegram Upload Error

    DatabaseIndexing --> Published: DB Insert Successful
    DatabaseIndexing --> TelegramRollback: DB Insert Error

    TelegramRollback --> Rejected: Delete Telegram Msg & Fail
    OrphanCleanup --> Rejected: Abort Transaction

    Published --> [*]
    Rejected --> [*]
```

To guarantee data consistency:
1. Media MUST be successfully uploaded to Telegram before calling PostgreSQL insert.
2. If PostgreSQL insert fails after Telegram upload succeeds, backend MUST issue a call to Telegram `deleteMessage(chat_id, message_id)` to prevent orphaned media files.

---

## 20. Deployment Overview

* **Frontend**: Host static Vite/React production build on Vercel or Netlify.
* **Backend**: Deploy FastAPI app on Render, Railway, or VPS (Docker containerized).
* **Database**: Serverless PostgreSQL hosted on Neon.tech.
* **Media Storage**: Private Telegram Channel (no deployment needed, managed by Telegram infra).

---

## 21. Initial Version Scope (V1)

### Included in V1
* Public single-page video dashboard (Dark Black & Red theme).
* Responsive video card grid auto-generated from PostgreSQL.
* Basic video streaming player (`<video>` modal/page).
* Discreet Admin login screen with JWT authentication.
* Admin panel with video title input, video file picker, upload progress indicator, and video deletion list.
* FastAPI backend with Telegram Bot & Neon PostgreSQL integration.

### Excluded from V1 (Pushed to V2)
* Video search & category filtering.
* Video views counter & analytics.
* Custom thumbnail uploads (V1 uses auto video frame / default thumbnail).
* User registration & watch history.
* Multiple admin user management.

---

## 22. Future Enhancements (V2+)

* Video category tags & search query bar.
* Custom poster/thumbnail image upload support.
* Video description text & view counters.
* Pagination or infinite scrolling for large video libraries.
* HLS / DASH adaptive bitrate streaming conversion for optimized mobile streaming.

---

## 23. Known Technical Limitations & Mitigations

### 1. Telegram Bot API File Size Download Limit (20 MB Limit)
* **Constraint**: The standard HTTP Telegram Bot API (`api.telegram.org/file/bot<token>/<file_path>`) limits file downloads via `getFile` to **20 MB**.
* **Impact**: Videos larger than 20 MB cannot be fetched using standard Bot HTTP GET calls.
* **Mitigation Options**:
  1. **Local Telegram Bot API Server**: Run a local instance of `telegram-bot-api` in Docker alongside FastAPI. The local bot API server increases the file download limit to **2000 MB (2 GB)**.
  2. **MTProto Client Integration (Pyrogram / Telethon)**: Use an asynchronous Python MTProto library in FastAPI to download file chunks directly from Telegram datacenters without using the HTTP Bot API.
* **Unresolved Architectural Decision**: Selection between **Local Bot API Server in Docker** vs **Pyrogram/Telethon MTProto client** for media streaming will be finalized in Phase 2 during backend development.

### 2. Video Seeking / Range Requests
* HTML5 `<video>` tags require servers to support `HTTP Range` headers (`bytes=0-1024`). FastAPI streaming endpoint must parse Range headers and stream byte chunks accordingly.

---

## 24. Development Phases

```mermaid
gantt
    title Development Roadmap
    dateFormat  YYYY-MM-DD
    section Setup & Docs
    Context & Architecture       :done,    des1, 2026-09-30, 1d
    section Phase 1: Backend Foundation
    FastAPI + PostgreSQL Setup   :active,  des2, 2026-10-01, 2d
    section Phase 2: Telegram Storage
    Bot Integration & Streaming  :         des3, 2026-10-03, 3d
    section Phase 3: Admin Auth
    JWT Login & Admin Routes     :         des4, 2026-10-06, 2d
    section Phase 4: Admin Panel
    React Upload & Delete UI     :         des5, 2026-10-08, 2d
    section Phase 5: Public Frontend
    Black & Red UI + Video Grid  :         des6, 2026-10-10, 3d
    section Phase 6: Polish & Deploy
    Error Handling & Deployment  :         des7, 2026-10-13, 2d
```

---

## 25. Important Architectural Rules

1. **No Application Code Modification Yet**: Do not modify, run, or create application code files until explicit instructions are given in implementation tasks.
2. **Strict Media Routing**: All video streaming requests MUST pass through FastAPI backend proxy. The public frontend MUST NEVER directly access Telegram tokens or channel paths.
3. **Database Integrity**: Media upload to Telegram is mandatory prior to database insertion. Failed uploads MUST NOT create database entries.
4. **Theme Adherence**: The UI must strictly follow the dark black-and-red design tokens.
5. **No 3rd Party Auth Services**: Do not introduce Firebase, Auth0, or Supabase Auth. Use custom environment variable authentication with JWT.
