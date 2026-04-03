module.exports = {
  apps: [
    {
      name: "taoguba-crawler-skill",
      cwd: "/home/nuonuo/app/taoguba-crawler-skill",
      script: "main.py",
      interpreter: "/home/nuonuo/app/taoguba-crawler-skill/.venv/bin/python",
      exec_mode: "fork",
      instances: 1,
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 20,
      kill_timeout: 20000,
      time: true,
      env: {
        PYTHONUNBUFFERED: "1",
      },
      out_file: "/home/nuonuo/app/taoguba-crawler-skill/logs/pm2-out.log",
      error_file: "/home/nuonuo/app/taoguba-crawler-skill/logs/pm2-error.log",
      merge_logs: false,
    },
  ],
};
