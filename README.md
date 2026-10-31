# Lantern

Lantern is an open-source, peer-to-peer file and folder transfer app. It helps
two devices establish a connection; when their networks permit, file bytes
travel directly between them over an encrypted WebRTC data channel rather than
being uploaded to Lantern.

**Status: public beta / experimental.** No independent security audit, TURN
relay, account system, resumable transfers, or durable room service yet. Some
networks will not establish a direct connection. Do not send sensitive files.

## Try Lantern

The public beta URL is **https://lantern-p2p.onrender.com** after the Render
blueprint is deployed. For the first deployment, open [Render's blueprint
flow](https://render.com/deploy?repo=https://github.com/lantern-p2p/lantern),
connect the public GitHub repository, and create the service. The free Render
instance may take about a minute to wake after idle, and open rooms disappear
when the instance sleeps or restarts.

1. Open Lantern on both devices.
2. On the sender, create a room and share its temporary code with the recipient.
3. On the recipient, enter the code and join.
4. Select files or a folder, send them, review the incoming list, and accept.

The first public host is configured as a single-instance beta. A cold start,
deploy, restart, or idle sleep can interrupt signaling and invalidate room
codes. A direct WebRTC session may keep transferring after signaling ends, but
there is no guarantee of uninterrupted availability.

## Run locally

Requirements: Python 3.10+ and a current browser with WebRTC support.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python server.py
```

Open `http://127.0.0.1:8765` in two browser windows. To enable the local-only
browser transfer smoke test, start the server with:

```powershell
$env:LANTERN_ENABLE_TESTS = "1"
python server.py
```

Then open `http://127.0.0.1:8765/tests/browser_smoke.html`. The smoke-test route
is disabled by default and is not exposed by the public Render service.

To use another port, set `PORT` before launching the server. The server binds
to `0.0.0.0` for hosting; the development server is not intended to be exposed
directly to the internet without a TLS-terminating host and its safety limits.

## Windows desktop app

The desktop client is an Electron shell around the same hosted Lantern web app.
It does not duplicate the transfer implementation or run a separate signaling
server. It needs internet access and the deployed service URL. Because the app
loads the hosted site directly, website design and interface improvements appear
in the desktop app automatically after the site deploys; rebuilding the Windows
installer is not required for web-only changes. Use `Ctrl+R` in the app to
reload the page if it was already open during a deployment.

```powershell
cd desktop
npm install
$env:LANTERN_URL = "https://lantern-p2p.onrender.com"
npm start
```

Build a Windows installer from Windows with:

```powershell
npm run dist
```

The installer is written to `desktop/dist/`. If the public host changes, update
the default URL in `desktop/main.cjs` before building. For development, setting
`LANTERN_URL` before `npm start` opens a different service URL. Electron keeps
Node integration disabled and restricts app navigation to the configured
Lantern origin.

## Tests

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
node --check app.js
```

The browser smoke test transfers generated synthetic content only and checks
SHA-256 and nested paths; it does not access real user files.

## Privacy and limitations

- The signaling server handles temporary room codes and WebRTC setup messages,
  not file contents. Room and rate-limit state is in memory; room codes are
  removed after their two-hour lifetime or when the service restarts.
- The app uses Google's public STUN server to help peers find a direct network
  path. Google may observe the peers' public IP addresses. This beta has no
  TURN relay, so restrictive NATs/firewalls can prevent a transfer.
- Files are read in the browser for hashing and sent in chunks, but the current
  implementation retains selected/received content in memory. Very large
  transfers can use substantial memory.
- The receiver verifies each file's SHA-256 digest and rejects unsafe paths.
  Save operations avoid overwriting existing names.
- Render's free web service may sleep after 15 minutes without inbound traffic
  and takes roughly a minute to wake. It has an ephemeral filesystem and
  in-memory rooms are lost on sleep/restart. Free hosting is suitable for this
  preview, not a production availability promise.

See [SECURITY.md](SECURITY.md) before using the beta and [LICENSE](LICENSE) for
the MIT license.
