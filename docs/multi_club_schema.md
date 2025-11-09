# Multi-Club Database Schema

## Overview
This schema supports multiple clubs/organizations, each with coaches and sailors, using a single database with tenant isolation via `club_id`.

## New Tables

### clubs
```sql
CREATE TABLE clubs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,  -- e.g., "BRYC" for Bristol Yacht Club
    subscription_tier VARCHAR(50) DEFAULT 'free',  -- free, basic, pro
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settings JSON  -- club-specific settings
);
```

### users (replaces hardcoded users)
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    club_id INTEGER REFERENCES clubs(id),
    role VARCHAR(50) NOT NULL,  -- 'sailor', 'coach', 'admin'
    sail_number VARCHAR(50),  -- sailor's personal sail number
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
```

### boats (new table)
```sql
CREATE TABLE boats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    name VARCHAR(255),  -- e.g., "My Laser"
    sail_number VARCHAR(50) NOT NULL,
    boat_class VARCHAR(100),  -- e.g., "Laser", "420", "GP14"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_default BOOLEAN DEFAULT FALSE
);
```

## Updated Tables

### sessions (add club_id and user columns)
```sql
ALTER TABLE sessions ADD COLUMN club_id INTEGER REFERENCES clubs(id);
ALTER TABLE sessions ADD COLUMN notes TEXT;
-- user_id and boat_id already exist
```

### All AI tables (add club_id)
- maneuvers
- performance_baselines
- performance_anomalies
- coaching_recommendations
- wind_shifts
- wind_patterns
- fleet_comparisons

## Access Control Rules

### Sailors
- Can view/edit only their own data
- Can view club leaderboards (anonymous)

### Coaches
- Can view all sailors in their club
- Can view detailed analytics for their club sailors
- Cannot edit sailor data

### Admins
- Full access to their club data
- Can invite coaches/sailors
- Can manage club settings

## Query Patterns

### Get User's Sessions
```sql
SELECT * FROM sessions WHERE user_id = ? ORDER BY start_ts DESC;
```

### Coach View: Club Athletes
```sql
SELECT u.id, u.name, u.sail_number, COUNT(s.id) as session_count
FROM users u
LEFT JOIN sessions s ON u.id = s.user_id
WHERE u.club_id = ? AND u.role = 'sailor'
GROUP BY u.id
ORDER BY u.name;
```

### Admin View: Club Overview
```sql
SELECT
    COUNT(DISTINCT u.id) as total_sailors,
    COUNT(s.id) as total_sessions,
    SUM(s.duration) as total_hours
FROM users u
LEFT JOIN sessions s ON u.id = s.user_id
WHERE u.club_id = ?;
```

## Migration Strategy

1. **Backward Compatibility**: Keep existing sessions working
2. **Default Club**: Create "Default Club" for existing data
3. **User Migration**: Create user accounts for existing user_id 1
4. **Gradual Rollout**: Deploy with optional auth first, then enforce

## Security

- Passwords hashed with bcrypt (12 rounds)
- JWT tokens with 7-day expiry
- Refresh tokens for mobile apps
- API endpoints protected with auth middleware
- Row-level security via club_id filtering
