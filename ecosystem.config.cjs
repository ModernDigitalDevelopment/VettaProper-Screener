module.exports = { apps: [{
  name: 'vps',
  script: 'python3',
  args: '-m uvicorn app.main:app --host 0.0.0.0 --port 3000',
  cwd: '/home/user/vps',
  env: { PYTHONPATH: '/home/user/vps', POLYGON_API_KEY: 'placeholder-for-local-ui-test' },
  watch: false, instances: 1, exec_mode: 'fork'
}]}
