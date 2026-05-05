const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');
const util = require('util');
const crypto = require('crypto');

const execAsync = util.promisify(exec);
const EDQ_PUBLIC_URL = process.env.EDQ_PUBLIC_URL || `http://localhost:${process.env.EDQ_PUBLIC_PORT || '3000'}`;

class DockerManager {
  constructor() {
    this.projectName = 'edq';
    this.composeFile = this._resolveComposeFile();
  }

  _resolveComposeFile() {
    const candidates = [
      path.join(__dirname, '..', 'docker-compose.yml'),
      path.join(process.resourcesPath || '', 'docker-compose.yml'),
      path.join(__dirname, 'docker-compose.yml'),
    ];

    for (const candidate of candidates) {
      try {
        if (fs.existsSync(candidate)) {
          return candidate;
        }
      } catch (_) {}
    }

    return candidates[0];
  }

  async checkDocker() {
    try {
      await execAsync('docker --version');
      await execAsync('docker compose version');

      const { stdout } = await execAsync('docker info --format "{{.ServerVersion}}"');
      if (!stdout.trim()) {
        return false;
      }
      return true;
    } catch {
      return false;
    }
  }

  async startContainers(onProgress) {
    if (!fs.existsSync(this.composeFile)) {
      throw new Error(
        `docker-compose.yml not found at: ${this.composeFile}\nPlease ensure the EDQ project files are in the correct location.`
      );
    }

    this._ensureEnvFile();

    onProgress?.('Building containers (this may take a few minutes on first run)...');

    const cmd = `docker compose -f "${this.composeFile}" -p ${this.projectName} up -d --build`;

    return new Promise((resolve, reject) => {
      const proc = exec(cmd, {
        timeout: 600000,
        cwd: path.dirname(this.composeFile),
        env: { ...process.env, COMPOSE_DOCKER_CLI_BUILD: '1', DOCKER_BUILDKIT: '1' },
      });

      let stderr = '';

      proc.stdout.on('data', (data) => {
        const line = data.toString().trim();
        if (line) {
          onProgress?.(line);
        }
      });

      proc.stderr.on('data', (data) => {
        const line = data.toString().trim();
        stderr += line + '\n';
        if (line && onProgress) {
          const short = line.length > 80 ? line.substring(0, 77) + '...' : line;
          onProgress(short);
        }
      });

      proc.on('close', (code) => {
        if (code === 0) {
          resolve();
        } else {
          reject(new Error(`docker compose exited with code ${code}\n${stderr.slice(-500)}`));
        }
      });

      proc.on('error', (err) => {
        reject(new Error(`Failed to exec docker compose: ${err.message}`));
      });
    });
  }

  async stopContainers() {
    try {
      const cmd = `docker compose -f "${this.composeFile}" -p ${this.projectName} down`;
      await execAsync(cmd, { timeout: 60000, cwd: path.dirname(this.composeFile) });
    } catch (err) {
      console.error('Failed to stop containers:', err.message);
    }
  }

  async waitForHealth(maxWait = 120000, onProgress) {
    const start = Date.now();
    let lastStatus = '';

    while (Date.now() - start < maxWait) {
      try {
        const result = await this._httpGet(`${EDQ_PUBLIC_URL}/api/health`, 5000);
        const json = JSON.parse(result);

        if (json.status === 'ok') {
          onProgress?.('All services healthy!');
          return true;
        }

        const status = `Backend: ${json.database || 'checking'}, Tools: ${json.tools_sidecar || 'checking'}`;
        if (status !== lastStatus && onProgress) {
          onProgress(status);
          lastStatus = status;
        }
      } catch {
        const elapsed = Math.round((Date.now() - start) / 1000);
        const status = `Waiting for services... (${elapsed}s)`;
        if (status !== lastStatus && onProgress) {
          onProgress(status);
          lastStatus = status;
        }
      }
      await this._sleep(2000);
    }

    throw new Error(
      `Services did not become healthy within ${Math.round(maxWait / 1000)}s.\n` +
        'Check Docker Desktop for container logs.'
    );
  }

  async getStatus() {
    try {
      const cmd = `docker compose -f "${this.composeFile}" -p ${this.projectName} ps --format json`;
      const { stdout } = await execAsync(cmd, { cwd: path.dirname(this.composeFile) });

      const lines = stdout.trim().split('\n').filter(Boolean);
      const containers = [];
      for (const line of lines) {
        try {
          containers.push(JSON.parse(line));
        } catch (_) {}
      }
      return containers;
    } catch {
      return [];
    }
  }

  async getLogs(service, lines = 100) {
    try {
      const svc = service ? ` ${service}` : '';
      const cmd = `docker compose -f "${this.composeFile}" -p ${this.projectName} logs --tail ${lines}${svc}`;
      const { stdout } = await execAsync(cmd, { cwd: path.dirname(this.composeFile) });
      return stdout;
    } catch (err) {
      return `Failed to retrieve logs: ${err.message}`;
    }
  }

  _ensureEnvFile() {
    const envPath = path.join(path.dirname(this.composeFile), '.env');
    const examplePath = path.join(path.dirname(this.composeFile), '.env.example');

    if (!fs.existsSync(envPath) && fs.existsSync(examplePath)) {
      const content = fs.readFileSync(examplePath, 'utf-8');
      const patched = content
        .replace(
          /^JWT_SECRET=.*$/m,
          `JWT_SECRET=${crypto.randomBytes(32).toString('hex')}`
        )
        .replace(
          /^JWT_REFRESH_SECRET=.*$/m,
          `JWT_REFRESH_SECRET=${crypto.randomBytes(32).toString('hex')}`
        )
        .replace(
          /^SECRET_KEY=.*$/m,
          `SECRET_KEY=${crypto.randomBytes(16).toString('hex')}`
        )
        .replace(
          /^TOOLS_API_KEY=.*$/m,
          `TOOLS_API_KEY=${crypto.randomBytes(16).toString('hex')}`
        )
        .replace(
          /^INITIAL_ADMIN_PASSWORD=.*$/m,
          `INITIAL_ADMIN_PASSWORD=${crypto.randomBytes(12).toString('base64url')}`
        );
      fs.writeFileSync(envPath, patched, 'utf-8');
    }
  }

  _httpGet(url, timeout) {
    return new Promise((resolve, reject) => {
      const req = http.get(url, (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(data);
          } else {
            reject(new Error(`HTTP ${res.statusCode}`));
          }
        });
      });
      req.on('error', reject);
      req.setTimeout(timeout, () => {
        req.destroy();
        reject(new Error('HTTP request timed out'));
      });
    });
  }

  _sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }
}

module.exports = DockerManager;
