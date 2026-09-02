import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const pluginUrl = new URL('../desktop/plugin.js', import.meta.url)
const source = readFileSync(pluginUrl, 'utf8')

test('uses the fixed weather plugin identity and right status area', () => {
  assert.match(source, /const ID = ['"]weather['"]/)
  assert.match(source, /id:\s*ID/)
  assert.match(source, /defaultEnabled:\s*false/)
  assert.match(source, /area:\s*['"]statusBar\.right['"]/)
})

test('uses a native popover above the chip', () => {
  assert.match(source, /PopoverTrigger/)
  assert.match(source, /PopoverContent/)
  assert.match(source, /side:\s*['"]top['"]/)
  assert.match(source, /align:\s*['"]end['"]/)
})

test('uses native Hermes controls for settings', () => {
  for (const control of ['Select', 'SelectTrigger', 'SelectContent', 'SelectItem', 'SelectValue', 'Switch']) {
    assert.match(source, new RegExp(`\\b${control}\\b`))
  }
  assert.doesNotMatch(source, /jsx\(['"]select['"]/)
})

test('uses one shared weather query through ctx rest', () => {
  assert.equal((source.match(/\buseQuery\s*\(/g) || []).length, 1)
  assert.match(source, /pluginCtx\.rest\(weatherPath\(settings\)/)
  assert.match(source, /pluginCtx\.rest\(['"]\/locations\?/)
})

test('keys weather data by location and unit settings', () => {
  assert.match(source, /queryKey:\s*\[ID,\s*['"]weather['"],\s*locationKey,\s*settings\.units\]/)
  assert.match(source, /location\.timezone/)
  assert.doesNotMatch(source, /placeholderData/)
})

test('uses React Query refresh without custom polling loops', () => {
  assert.match(source, /refetchInterval:/)
  assert.match(source, /refetchIntervalInBackground:\s*true/)
  assert.match(source, /refetchOnWindowFocus:\s*true/)
  assert.match(source, /refetchOnReconnect:\s*true/)
  assert.match(source, /retry:\s*false/)
  assert.doesNotMatch(source, /setInterval|setTimeout/)
})

test('keeps data and presents stale refresh failures', () => {
  assert.match(source, /query\.data/)
  assert.match(source, /query\.isError/)
  assert.match(source, /Stale data|Last successful update/)
})

test('stores versioned settings and supports location removal', () => {
  assert.match(source, /SETTINGS_VERSION\s*=\s*1/)
  assert.match(source, /pluginCtx\.storage\.get\(SETTINGS_KEY/)
  assert.match(source, /pluginCtx\.storage\.set\(SETTINGS_KEY/)
  assert.match(source, /removeLocation/)
})

test('implements persistent alert baselining and deduplication', () => {
  assert.match(source, /ALERT_STATE_KEY/)
  assert.match(source, /baselineEstablished/)
  assert.match(source, /seenAlerts/)
  assert.match(source, /alertFingerprint/)
  assert.match(source, /expires/)
  assert.match(source, /activeFingerprints/)
})

test('does not misuse the read-only host logs API', () => {
  assert.doesNotMatch(source, /host\.logs\s*\(/)
})

test('honors notification settings and severe baseline', () => {
  assert.match(source, /alertNotifications/)
  assert.match(source, /minimumSeverity/)
  assert.match(source, /host\.notify/)
  assert.match(source, /pluginCtx\.os\.notify/)
})

test('shows setup current hourly daily details settings and refresh controls', () => {
  for (const label of ['Choose location', 'Current conditions', 'Next 24 hours', 'Seven-day forecast', 'Details', 'Settings', 'Refresh now']) {
    assert.ok(source.includes(label), `missing UI label: ${label}`)
  }
})

test('daily rows show rain amount probability wind and gust', () => {
  const daily = source.slice(source.indexOf('function DailyForecast'), source.indexOf('function Details'))
  for (const field of ['precipitationProbability', 'precipitation', 'windSpeed', 'windGust']) {
    assert.ok(daily.includes(`item.${field}`), `daily rows omit ${field}`)
  }
})

test('shows provider attribution and official alert source links', () => {
  assert.match(source, /Weather data by Open-Meteo/)
  assert.match(source, /Environment and Climate Change Canada/)
  assert.match(source, /openExternal\(alert\.sourceUrl\)/)
})

test('uses manual search and never infers a location', () => {
  assert.doesNotMatch(source, /geolocation|ipapi|ipinfo|navigator\.geolocation/i)
  assert.match(source, /searchLocations/)
})

test('imports only supported desktop modules', () => {
  const modules = [...source.matchAll(/from\s+['"]([^'"]+)['"]/g)].map(match => match[1])
  assert.ok(modules.length > 0)
  assert.deepEqual([...new Set(modules)].sort(), ['@hermes/plugin-sdk', 'react', 'react/jsx-runtime'])
})

test('uses theme variables without hardcoded colors', () => {
  assert.match(source, /--ui-/)
  assert.doesNotMatch(source, /#[0-9a-f]{3,8}\b|rgba?\s*\(|\b(?:black|white|red|blue|green|yellow|orange|purple|gray|grey)\b/i)
})
