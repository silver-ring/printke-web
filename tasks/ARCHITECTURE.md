# PrintKe Platform Architecture

## Overview
PrintKe is a card printing platform with real-time delivery tracking for Kenya.

## Applications

| App | Tech Stack | Purpose |
|-----|------------|---------|
| printke-api | FastAPI (Python) | Backend microservices |
| printke-web | Jinja2 + HTMX | Customer website (orders) |
| printke-admin | React + Vite | Admin back office |
| printke-driver | Expo (React Native) | Driver mobile app |

## Microservices Architecture

```
                    ┌─────────────────┐
                    │   API Gateway   │
                    │    (Traefik)    │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  Auth Service │  │ Order Service │  │Delivery Service│
│   (FastAPI)   │  │   (FastAPI)   │  │   (FastAPI)    │
└───────────────┘  └───────────────┘  └───────────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                    ┌────────┴────────┐
                    │                 │
                    ▼                 ▼
            ┌─────────────┐   ┌─────────────┐
            │ PostgreSQL  │   │    Redis    │
            └─────────────┘   └─────────────┘
```

## Services Breakdown

### 1. Auth Service
- User registration/login
- JWT token management
- Driver authentication
- Admin authentication
- Document storage per user

### 2. Order Service
- Order creation
- Order management
- Pricing calculation
- PDF generation
- M-Pesa payment integration

### 3. Delivery Service
- Driver management
- Order assignment to drivers
- Real-time GPS tracking (WebSocket)
- Delivery status updates
- ETA calculation

### 4. Notification Service (Future)
- SMS notifications (Africa's Talking)
- Email notifications
- Push notifications

## Database Schema

### Users Table
- id, email, phone, password_hash
- role (customer, driver, admin)
- documents (JSON - stored file references)

### Drivers Table
- id, user_id, name, phone, vehicle_type
- is_active, current_location (lat, lng)
- last_location_update

### Deliveries Table
- id, order_id, driver_id
- status (assigned, picked_up, in_transit, delivered)
- pickup_location, delivery_location
- started_at, delivered_at
- current_lat, current_lng

### Location History Table
- id, delivery_id, lat, lng, timestamp

## Tech Decisions

### Why Expo for Driver App?
- JavaScript - AI-friendly development
- Cross-platform (Android + iOS)
- Expo Go for instant testing
- Background location with expo-location
- Easy to build APK

### Why React + Vite for Admin?
- Fast development
- Rich ecosystem
- Real-time updates with WebSocket
- Maps integration (Leaflet)

### Why Docker Compose (not K8s)?
- Single server deployment
- Simpler for small team
- Easy to scale later to K8s
- Lower complexity

## Deployment

```yaml
# docker-compose.yml structure
services:
  traefik:      # API Gateway & Load Balancer
  api-auth:     # Auth microservice
  api-orders:   # Orders microservice
  api-delivery: # Delivery microservice
  postgres:     # Database
  redis:        # Cache & Pub/Sub
  minio:        # Document storage (S3-compatible)
```

## GitHub Repositories

Organization: `printke`

| Repository | Description |
|------------|-------------|
| printke-api | Backend microservices (monorepo) |
| printke-admin | Admin dashboard (React) |
| printke-driver | Driver app (Expo) |
| printke-infra | Docker, K8s configs |

## Development Workflow

1. Each service runs independently
2. Shared PostgreSQL database
3. Redis for real-time pub/sub
4. WebSocket for live tracking
5. Docker Compose for local dev
6. GitHub Actions for CI/CD
