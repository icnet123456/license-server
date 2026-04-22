# CardGenerator License Server for Render

This folder is the GitHub upload package for the online license server only.

## Upload these files to a new GitHub repository
- server.py
- requirements.txt
- render.yaml
- .gitignore

## Deploy on Render
1. Create a new GitHub repository.
2. Upload the contents of this folder to that repository root.
3. In Render, create a new Web Service from that repository.
4. Render will read render.yaml automatically.

## Available endpoints
- /health
- /api/meta
- /api/create-license
- /api/check-license
- /api/check-device
- /api/start-trial
- /api/check-trial
- /admin

## Notes
- Do not upload licenses.db if you want a clean new database.
- The SQLite database file is created automatically on first run.
