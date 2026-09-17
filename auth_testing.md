# Watchful Auth Testing Playbook

Watchful supports TWO auth methods that share one `users` collection (keyed by `user_id`, a custom UUID; MongoDB `_id` is never exposed).

## 1. JWT email/password
- POST /api/auth/register {email, password, name} -> {user, token}
- POST /api/auth/login {email, password} -> {user, token}
- Token is a JWT (7-day). Returned in body AND set as httpOnly cookie `access_token`.
- Send as `Authorization: Bearer <token>` or via cookie.

Admin (seeded on startup): admin@watchful.app / Watchful2026!
Test user: register agente@watchful.app / Agente2026!

## 2. Google (Emergent managed)
- Frontend redirects to https://auth.emergentagent.com/?redirect=<origin>/app
- Returns to /app#session_id=... , AppRouter detects hash and mounts AuthCallback
- AuthCallback POSTs /api/auth/session {session_id} -> backend calls Emergent session-data -> {user, token=session_token}
- session_token stored in `user_sessions` collection + httpOnly cookie `session_token`

### Create a Google-style test session directly (for gated UI tests)
```
mongosh --eval "
use('test_database');
var uid='user_'+Math.random().toString(16).slice(2,14);
db.users.insertOne({user_id:uid,email:'gtest_'+Date.now()+'@example.com',name:'Google Test',role:'user',credits:30,auth_provider:'google',created_at:new Date().toISOString()});
var tok='sess_'+Date.now();
db.user_sessions.insertOne({user_id:uid,session_token:tok,expires_at:new Date(Date.now()+7*24*3600*1000).toISOString(),created_at:new Date().toISOString()});
print('TOKEN '+tok);
"
```
Use TOKEN as `Authorization: Bearer <tok>` OR set localStorage `watchful_token` in browser and cookie `session_token`.

## get_current_user resolution order
cookie access_token / session_token -> Authorization Bearer -> query `?token=` (files only).
Resolver tries JWT decode first, then `user_sessions` lookup.

## Quick API smoke
```
API=https://property-video-ai-3.preview.emergentagent.com/api
curl -s -X POST $API/auth/login -H 'Content-Type: application/json' -d '{"email":"admin@watchful.app","password":"Watchful2026!"}'
# take token, then:
curl -s $API/auth/me -H "Authorization: Bearer <token>"
curl -s $API/actions
```
