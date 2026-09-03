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

test('shows only the active view and defaults to Current', () => {
  assert.match(source, /const \[activeView, setActiveView\] = useState\(['"]current['"]\)/)
  assert.match(source, /switch \(activeView\)/)
  assert.match(source, /children:\s*activeViewContent/)
})

test('shows native buttons for all six weather views', () => {
  for (const [id, label] of [
    ['current', 'Current'],
    ['hourly', 'Hourly'],
    ['daily', 'Daily'],
    ['alerts', 'Alerts'],
    ['details', 'Details'],
    ['settings', 'Settings']
  ]) {
    assert.match(source, new RegExp(`id: ['"]${id}['"], label: ['"]${label}['"]`))
  }
  assert.match(source, /views\.map\(view => jsx\(Button/)
  assert.match(source, /onClick: \(\) => setActiveView\(view\.id\)/)
  assert.match(source, /role: ['"]tab['"]/)
  assert.match(source, /'aria-selected': activeView === view\.id/)
})

test('selects each weather data pane through the active view switch', () => {
  const cases = [
    ['current', 'CurrentConditions'],
    ['hourly', 'HourlyForecast'],
    ['daily', 'DailyForecast'],
    ['alerts', 'Alerts'],
    ['details', 'Details']
  ]
  for (const [view, component] of cases) {
    assert.match(source, new RegExp(`case ['"]${view}['"]:[\\s\\S]*?activePanel = jsx\\(${component},`))
  }
})

test('keeps location controls in a distinct Settings view', () => {
  const settingsView = source.slice(source.indexOf('function Settings'), source.indexOf('function WeatherChip'))
  assert.match(settingsView, /jsx\(LocationSetup/)
  assert.match(settingsView, /Remove location/)
  assert.match(source, /case ['"]settings['"]:[\s\S]*?activePanel = jsx\(Settings,/)
  const currentCase = source.slice(source.indexOf("case 'current':"), source.indexOf('const panel ='))
  assert.doesNotMatch(currentCase, /Settings|LocationSetup|Remove location/)
})

test('bounds every view with one shared scrolling body outside fixed controls', () => {
  const weatherChip = source.slice(source.indexOf('function WeatherChip'), source.indexOf('export default'))
  const panel = weatherChip.slice(weatherChip.indexOf("const panel = jsxs('div'"))
  const alertCase = weatherChip.slice(weatherChip.indexOf("case 'alerts':"), weatherChip.indexOf("case 'details':"))

  assert.doesNotMatch(weatherChip, /scrollableViews/)
  assert.match(source, /const VIEW_BODY_CLASS = ['"][^'"]*h-\[min\(16rem,55vh\)\][^'"]*max-h-\[min\(16rem,55vh\)\][^'"]*['"]/)
  assert.match(weatherChip, /const activeViewContent = jsx\(ScrollArea, \{[\s\S]*?className: VIEW_BODY_CLASS[\s\S]*?children: activePanel[\s\S]*?\}\)/)
  assert.match(alertCase, /activePanel = jsx\(Alerts, \{ data \}\)/)
  assert.match(panel, /Refresh now[\s\S]*?role: ['"]tablist['"][\s\S]*?id: ['"]weather-active-panel['"][\s\S]*?children: activeViewContent[\s\S]*?Weather data by Open-Meteo/)
  assert.doesNotMatch(panel, /h-\[24rem\]|max-h-\[min\(24rem,80vh\)\]/)
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
