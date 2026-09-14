# NGINX Assistant Frontend

A simple Next.js (App Router, plain JS) frontend for the FastAPI backend in
`main.py` / `agent.py` / `auth.py` / `db.py`. Styled with Tailwind CSS in a
layout similar to Gemini: a chat list sidebar on the left, messages in the
middle, and a rounded input bar at the bottom.

## Setup

```bash
npm install
cp .env.local.example .env.local
```

Edit `.env.local` if your FastAPI backend isn't running on
`http://localhost:8000`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Then run the dev server:

```bash
npm run dev
```

Open http://localhost:3000 — it will send you to `/login` if you don't
have a token saved yet.

## Structure

- `utils/api.js` — the only file outside `app/`. One axios instance plus one
  function per backend endpoint (register, login, chats, messages, agent
  run/approve). The auth token is read from `localStorage` and attached to
  every request automatically.
- `app/page.js` — redirects to `/login` or `/chat` depending on whether a
  token is saved.
- `app/login/page.js`, `app/register/page.js` — plain forms that call
  `loginUser` / `registerUser` and save the returned token.
- `app/chat/page.js` — the main screen: sidebar (new chat / switch chat /
  delete chat), message list, and the input bar. When the backend returns
  an `interrupt` (the NGINX config approval step), an approval card is
  shown instead of the input being usable, with Approve/Reject buttons
  wired to `/agent/{chat_id}/approve`.

## Notes

- Your FastAPI `CORSMiddleware` only allows `localhost`/`127.0.0.1` origins,
  which matches Next's default dev server at `http://localhost:3000`.
- There's no token refresh — if a request comes back 401, you'll need to
  log in again (the token is just cleared on logout).
