module.exports = {
  apps: [
    {
      name: 'wl-backend',
      script: 'venv/bin/uvicorn',
      args: 'app.main:app --host 0.0.0.0 --port 8000',
      cwd: './backend',
      interpreter: 'none',
      watch: false,
      env: {
        PYTHONUNBUFFERED: '1',
      },
    },
    {
      name: 'wl-frontend',
      script: 'node_modules/.bin/next',
      args: 'start --port 3000',
      cwd: './frontend',
      interpreter: 'none',
      watch: false,
    },
  ],
};
