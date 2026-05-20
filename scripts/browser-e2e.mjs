#!/usr/bin/env node
/**
 * Browser E2E smoke test for the EDQ local app.
 *
 * The test drives a real Chromium browser through the Chrome DevTools
 * Protocol without adding a project dependency. It logs console output,
 * runtime exceptions, network failures, screenshots, and page text into an
 * ignored reports/browser-e2e/<run>/ artifact directory.
 */

import { spawn } from 'node:child_process'
import { appendFileSync, existsSync } from 'node:fs'
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, '..')

const DEFAULT_CHROME_PATHS = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  path.join(process.env.LOCALAPPDATA || '', 'Google\\Chrome\\Application\\chrome.exe'),
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
]

function parseArgs(argv) {
  const options = {
    adminUser: process.env.EDQ_ADMIN_USER || 'admin',
    adminPass: process.env.EDQ_ADMIN_PASS || '',
    baseUrl: process.env.EDQ_URL || process.env.EDQ_PUBLIC_URL || '',
    cdpPort: Number(process.env.EDQ_BROWSER_CDP_PORT || 0) || 0,
    chromePath: process.env.EDQ_CHROME_PATH || '',
    headed: process.env.EDQ_BROWSER_HEADED
      ? process.env.EDQ_BROWSER_HEADED !== '0'
      : process.platform === 'win32',
    keepOpen: process.env.EDQ_BROWSER_KEEP_OPEN === '1',
    outputDir: '',
    runId: process.env.EDQ_E2E_RUN_ID || '',
  }

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    const next = () => argv[++index]
    if (arg === '--admin-user') options.adminUser = next()
    else if (arg === '--admin-pass') options.adminPass = next()
    else if (arg === '--base-url') options.baseUrl = next()
    else if (arg === '--cdp-port') options.cdpPort = Number(next())
    else if (arg === '--chrome-path') options.chromePath = next()
    else if (arg === '--headed') options.headed = true
    else if (arg === '--headless') options.headed = false
    else if (arg === '--keep-open') options.keepOpen = true
    else if (arg === '--output-dir') options.outputDir = next()
    else if (arg === '--run-id') options.runId = next()
    else if (arg === '--help' || arg === '-h') {
      printHelp()
      process.exit(0)
    } else {
      throw new Error(`Unknown argument: ${arg}`)
    }
  }
  return options
}

function printHelp() {
  console.log(`Usage: node scripts/browser-e2e.mjs [options]

Options:
  --base-url URL       EDQ frontend URL (default from env/.env or http://localhost:3000)
  --run-id ID          Specific test run to open; defaults to latest EasyIO run
  --admin-user USER    Login username (default admin)
  --admin-pass PASS    Login password (default EDQ_ADMIN_PASS or INITIAL_ADMIN_PASSWORD)
  --cdp-port PORT      Attach to an existing Chrome remote-debugging port
  --chrome-path PATH   Browser executable to launch when --cdp-port is omitted
  --headed             Show browser window
  --headless           Force headless browser mode
  --keep-open          Leave launched browser running after the test
  --output-dir DIR     Artifact directory (default reports/browser-e2e/<timestamp>)
`)
}

async function readRootEnv() {
  const envPath = path.join(repoRoot, '.env')
  const values = new Map()
  if (!existsSync(envPath)) return values
  const text = await readFile(envPath, 'utf8')
  for (const line of text.split(/\r?\n/)) {
    const match = line.match(/^([^#=\s]+)=(.*)$/)
    if (!match) continue
    values.set(match[1], match[2].trim().replace(/^['"]|['"]$/g, ''))
  }
  return values
}

function trimUrl(url) {
  return String(url || '').replace(/\/+$/, '')
}

function resolveChromePath(explicitPath) {
  if (explicitPath && existsSync(explicitPath)) return explicitPath
  const found = DEFAULT_CHROME_PATHS.find((candidate) => candidate && existsSync(candidate))
  if (!found) {
    throw new Error(
      'No Chrome or Edge executable found. Set EDQ_CHROME_PATH or pass --chrome-path.',
    )
  }
  return found
}

async function fetchJson(url, options) {
  const response = await fetch(url, options)
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} from ${url}`)
  }
  return response.json()
}

async function waitForCdp(port) {
  const deadline = Date.now() + 20_000
  let lastError
  while (Date.now() < deadline) {
    try {
      await fetchJson(`http://127.0.0.1:${port}/json/version`)
      return
    } catch (error) {
      lastError = error
      await delay(250)
    }
  }
  throw new Error(`Chrome did not expose CDP on port ${port}: ${lastError?.message || 'timeout'}`)
}

async function ensureBrowser(options, artifactDir) {
  if (options.cdpPort) {
    await waitForCdp(options.cdpPort)
    return { port: options.cdpPort, launched: null, profileDir: null }
  }

  const port = 9222 + Math.floor(Math.random() * 1000)
  const profileDir = path.join(repoRoot, '.tmp', `edq-browser-e2e-${Date.now()}`)
  await mkdir(profileDir, { recursive: true })
  const chromePath = resolveChromePath(options.chromePath)
  const args = [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-background-networking',
    '--disable-dev-shm-usage',
    '--disable-gpu',
    '--disable-sync',
    options.baseUrl,
  ]
  if (!options.headed) {
    args.unshift('--headless=new')
  }

  const launched = spawn(chromePath, args, {
    detached: false,
    stdio: ['ignore', 'ignore', 'pipe'],
  })
  let exited = false
  let exitCode = null
  launched.on('exit', (code) => {
    exited = true
    exitCode = code
  })
  launched.stderr?.on('data', (chunk) => {
    appendFileSync(path.join(artifactDir, 'chrome-stderr.log'), chunk)
  })

  await waitForCdp(port)
  await delay(500)
  if (exited) {
    throw new Error(`Chrome exited during startup with code ${exitCode}; see ${path.join(artifactDir, 'chrome-stderr.log')}`)
  }
  return { port, launched, profileDir }
}

async function newPageTarget(port, url) {
  const encoded = encodeURIComponent(url)
  try {
    return await fetchJson(`http://127.0.0.1:${port}/json/new?${encoded}`, { method: 'PUT' })
  } catch {
    return fetchJson(`http://127.0.0.1:${port}/json/new?${encoded}`)
  }
}

class CdpSession {
  constructor(wsUrl, artifactDir) {
    this.artifactDir = artifactDir
    this.commandId = 0
    this.pending = new Map()
    this.consoleEntries = []
    this.exceptions = []
    this.logEntries = []
    this.requests = new Map()
    this.responses = []
    this.failures = []
    this.ws = new WebSocket(wsUrl)
    this.ws.onmessage = (event) => this.handleMessage(event)
  }

  async open() {
    await new Promise((resolve, reject) => {
      this.ws.onopen = resolve
      this.ws.onerror = reject
    })
  }

  handleMessage(event) {
    const message = JSON.parse(event.data)
    if (message.id && this.pending.has(message.id)) {
      const { resolve, reject } = this.pending.get(message.id)
      this.pending.delete(message.id)
      if (message.error) reject(new Error(JSON.stringify(message.error)))
      else resolve(message.result)
      return
    }

    if (message.method === 'Runtime.consoleAPICalled') {
      this.consoleEntries.push({
        level: message.params.type,
        text: (message.params.args || []).map((arg) => arg.value ?? arg.description ?? '').join(' '),
        url: message.params.stackTrace?.callFrames?.[0]?.url || '',
      })
    } else if (message.method === 'Runtime.exceptionThrown') {
      this.exceptions.push(message.params.exceptionDetails)
    } else if (message.method === 'Log.entryAdded') {
      this.logEntries.push(message.params.entry)
    } else if (message.method === 'Network.requestWillBeSent') {
      this.requests.set(message.params.requestId, {
        method: message.params.request.method,
        url: message.params.request.url,
      })
    } else if (message.method === 'Network.responseReceived') {
      const request = this.requests.get(message.params.requestId) || {}
      this.responses.push({
        method: request.method,
        url: message.params.response.url,
        status: message.params.response.status,
        mimeType: message.params.response.mimeType,
      })
    } else if (message.method === 'Network.loadingFailed') {
      const request = this.requests.get(message.params.requestId) || {}
      this.failures.push({
        method: request.method,
        url: request.url,
        errorText: message.params.errorText,
        canceled: message.params.canceled,
      })
    }
  }

  send(method, params = {}) {
    const id = ++this.commandId
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.ws.send(JSON.stringify({ id, method, params }))
    })
  }

  async enable() {
    await this.send('Page.enable')
    await this.send('Runtime.enable')
    await this.send('Network.enable')
    await this.send('Log.enable')
  }

  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    })
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text)
    }
    return result.result?.value
  }

  async navigate(url) {
    await this.send('Page.navigate', { url })
    await delay(1000)
  }

  async screenshot(name) {
    const result = await this.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
    const filePath = path.join(this.artifactDir, name)
    await writeFile(filePath, Buffer.from(result.data, 'base64'))
    return filePath
  }

  async close() {
    this.ws.close()
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function waitFor(session, predicateSource, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs
  let lastValue
  while (Date.now() < deadline) {
    lastValue = await session.evaluate(`(${predicateSource})()`)
    if (lastValue?.ok) return lastValue
    await delay(250)
  }
  throw new Error(`Timed out waiting for ${label}; last value: ${JSON.stringify(lastValue)}`)
}

async function main() {
  const options = parseArgs(process.argv.slice(2))
  const env = await readRootEnv()
  options.baseUrl = trimUrl(options.baseUrl || env.get('EDQ_PUBLIC_URL') || `http://localhost:${env.get('EDQ_PUBLIC_PORT') || 3000}`)
  options.adminPass = options.adminPass || env.get('INITIAL_ADMIN_PASSWORD') || ''

  if (!options.adminPass) {
    throw new Error('Set EDQ_ADMIN_PASS, pass --admin-pass, or configure INITIAL_ADMIN_PASSWORD in .env.')
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
  const artifactDir = path.resolve(
    repoRoot,
    options.outputDir || path.join('reports', 'browser-e2e', timestamp),
  )
  await mkdir(artifactDir, { recursive: true })

  const browser = await ensureBrowser(options, artifactDir)
  const target = await newPageTarget(browser.port, `${options.baseUrl}/login`)
  const session = new CdpSession(target.webSocketDebuggerUrl, artifactDir)

  let summary
  try {
    await session.open()
    await session.enable()

    const runDetailPath = options.runId ? `/test-runs/${options.runId}` : '/test-runs'
    await session.navigate(`${options.baseUrl}${runDetailPath}`)
    await delay(1500)
    await session.screenshot('01-login-or-start.png')

    const loginState = await session.evaluate(`(() => ({
      href: location.href,
      needsLogin: Boolean(document.querySelector('#login-username') && document.querySelector('#login-password'))
    }))()`)

    if (loginState.needsLogin) {
      await session.evaluate(`(() => {
        const setValue = (input, value) => {
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
          setter.call(input, value)
          input.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }))
          input.dispatchEvent(new Event('change', { bubbles: true }))
        }
        setValue(document.querySelector('#login-username'), ${JSON.stringify(options.adminUser)})
        setValue(document.querySelector('#login-password'), ${JSON.stringify(options.adminPass)})
        document.querySelector('button[type=submit]')?.click()
        return true
      })()`)
      await waitFor(
        session,
        `() => ({ ok: !location.pathname.startsWith('/login'), href: location.href })`,
        15_000,
        'login redirect',
      )
    }

    await session.screenshot('02-after-login.png')

    await session.evaluate(`(() => {
      const link = [...document.querySelectorAll('a')].find((item) => item.getAttribute('href') === '/test-runs')
      if (!link) return false
      link.click()
      return true
    })()`)
    await waitFor(
      session,
      `() => ({ ok: location.pathname === '/test-runs', href: location.href })`,
      10_000,
      'test-runs route',
    )
    await delay(1000)
    await session.screenshot('03-test-runs.png')

    const selectedRun = await session.evaluate(`(async () => {
      const response = await fetch('/api/test-runs/?limit=200', { credentials: 'include' })
      const runs = await response.json()
      const candidates = runs.filter((run) => {
        const text = [run.device_name, run.device_ip, run.template_name, run.device_manufacturer, run.device_model]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
        return text.includes('easyio')
      })
      const run = ${JSON.stringify(options.runId)}
        ? runs.find((item) => item.id === ${JSON.stringify(options.runId)})
        : candidates.find((item) => item.status === 'awaiting_manual') || candidates[0] || runs[0]
      return run ? {
        id: run.id,
        status: run.status,
        device_name: run.device_name,
        device_ip: run.device_ip,
        template_name: run.template_name,
        completed_tests: run.completed_tests,
        total_tests: run.total_tests
      } : null
    })()`)

    if (!selectedRun?.id) {
      throw new Error('No test run found to open in the browser.')
    }

    const clickedRun = await session.evaluate(`(() => {
      const link = [...document.querySelectorAll('a')].find((item) => item.getAttribute('href') === '/test-runs/${selectedRun.id}')
      if (!link) return false
      link.scrollIntoView({ block: 'center' })
      link.click()
      return true
    })()`)

    if (!clickedRun) {
      throw new Error(`Could not find test-run link for ${selectedRun.id} on the Test Runs page.`)
    }

    await waitFor(
      session,
      `() => ({ ok: location.pathname === '/test-runs/${selectedRun.id}', href: location.href })`,
      10_000,
      'test-run detail route',
    )
    await delay(1500)
    await session.screenshot('04-run-detail.png')

    const finalPage = await session.evaluate(`(() => ({
      href: location.href,
      title: document.title,
      text: document.body.innerText
    }))()`)
    await writeFile(path.join(artifactDir, 'run-detail.txt'), finalPage.text)

    const expectedDevice = selectedRun.device_name || selectedRun.device_ip
    const hasDevice = finalPage.text.includes(expectedDevice)
    const hasRunState = /Awaiting Manual|Running|Completed|Failed|Cancelled|Manual Pending|TESTS/i.test(finalPage.text)
    const failedResponses = session.responses.filter((response) => {
      const sameOrigin = response.url?.startsWith(options.baseUrl) || response.url?.startsWith(`${options.baseUrl.replace('localhost', '127.0.0.1')}`)
      if (!sameOrigin || response.status < 400) return false
      if (response.status === 401 && response.url.includes('/api/auth/me')) return false
      return true
    })
    const networkFailures = session.failures.filter((failure) => !failure.canceled)

    summary = {
      ok: hasDevice && hasRunState && failedResponses.length === 0 && networkFailures.length === 0 && session.exceptions.length === 0,
      artifactDir,
      baseUrl: options.baseUrl,
      run: selectedRun,
      href: finalPage.href,
      checks: {
        hasDevice,
        hasRunState,
        consoleErrors: session.consoleEntries.filter((entry) => ['error', 'assert'].includes(entry.level)).length,
        runtimeExceptions: session.exceptions.length,
        failedResponses: failedResponses.length,
        networkFailures: networkFailures.length,
      },
    }
  } finally {
    await writeFile(path.join(artifactDir, 'console.json'), JSON.stringify(session.consoleEntries, null, 2))
    await writeFile(path.join(artifactDir, 'runtime-exceptions.json'), JSON.stringify(session.exceptions, null, 2))
    await writeFile(path.join(artifactDir, 'browser-log.json'), JSON.stringify(session.logEntries, null, 2))
    await writeFile(path.join(artifactDir, 'network-responses.json'), JSON.stringify(session.responses, null, 2))
    await writeFile(path.join(artifactDir, 'network-failures.json'), JSON.stringify(session.failures, null, 2))
    if (summary) {
      await writeFile(path.join(artifactDir, 'summary.json'), JSON.stringify(summary, null, 2))
    }
    await session.close()
    if (browser.launched && !options.keepOpen) {
      browser.launched.kill()
      await delay(500)
    }
    if (browser.profileDir && !options.keepOpen) {
      try {
        await rm(browser.profileDir, { recursive: true, force: true, maxRetries: 3, retryDelay: 250 })
      } catch (error) {
        await writeFile(
          path.join(artifactDir, 'cleanup-warning.txt'),
          `Could not remove temporary browser profile ${browser.profileDir}: ${error.message}\n`,
        )
      }
    }
  }

  console.log(JSON.stringify(summary, null, 2))
  if (!summary.ok) {
    process.exitCode = 1
  }
}

main().catch((error) => {
  console.error(error.stack || error.message)
  process.exit(1)
})
