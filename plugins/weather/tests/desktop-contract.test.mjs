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

test('sizes PopoverContent as a responsive square', () => {
  const sizeClass = source.match(/const POPOVER_SQUARE_CLASS = ['"]([^'"]+)['"]/)?.[1]
  assert.ok(sizeClass, 'missing responsive square size class')

  const height = sizeClass.match(/h-\[([^\]]+)\]/)?.[1]
  const width = sizeClass.match(/w-\[([^\]]+)\]/)?.[1]
  assert.equal(height, width)
  assert.equal(width, 'min(24rem,calc(100vw-1rem),calc(100vh-1rem))')
  assert.match(source, /jsx\(PopoverContent, \{[\s\S]*?className: POPOVER_SQUARE_CLASS[\s\S]*?children: panel/)
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

test('uses an accessible compact ghost Refresh icon', () => {
  const weatherChip = source.slice(source.indexOf('function WeatherChip'), source.indexOf('export default'))
  const header = weatherChip.slice(weatherChip.indexOf("const header = jsxs('header'"), weatherChip.indexOf("const body = jsx('main'"))

  assert.match(header, /variant: ['"]ghost['"]/)
  assert.match(header, /size: ['"]icon['"]/)
  assert.match(header, /className: ['"][^'"]*size-7[^'"]*['"]/)
  assert.match(header, /'aria-label': ['"]Refresh weather['"]/)
  assert.match(header, /title: ['"]Refresh weather['"]/)
  assert.match(header, /children: jsx\(Codicon, \{ name: ['"]refresh['"], size: 14, spinning: query\.isFetching \}\)/)
  assert.doesNotMatch(header, /Refreshing…|Refresh now/)
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
  assert.match(source, /children:\s*activePanel/)
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
    assert.match(source, new RegExp(`id: ['"]${id}['"], label: ['"]${label}['"], icon: ['"][^'"]+['"]`))
  }
  assert.match(source, /views\.map\(view => jsxs\(Button/)
  assert.match(source, /onClick: \(\) => setActiveView\(view\.id\)/)
  assert.match(source, /role: ['"]tab['"]/)
  assert.match(source, /'aria-label': view\.label/)
  assert.match(source, /'aria-selected': activeView === view\.id/)
})

test('keeps the bottom tab bar on one horizontal line', () => {
  const weatherChip = source.slice(source.indexOf('function WeatherChip'), source.indexOf('export default'))
  const tabBar = weatherChip.slice(weatherChip.indexOf("const tabBar = jsx('nav'"), weatherChip.indexOf("const panel = jsxs('div'"))

  assert.match(tabBar, /className: ['"][^'"]*flex-nowrap[^'"]*overflow-hidden[^'"]*['"]/)
  assert.match(tabBar, /className: ['"][^'"]*min-w-0[^'"]*flex-1[^'"]*whitespace-nowrap[^'"]*['"]/)
  assert.match(tabBar, /jsx\(Codicon, \{ name: view\.icon/)
  assert.doesNotMatch(tabBar, /grid-cols-|flex-wrap/)
})

test('routes all six weather views through the shared ScrollArea', () => {
  const weatherChip = source.slice(source.indexOf('function WeatherChip'), source.indexOf('export default'))
  const cases = [
    ['current', 'CurrentConditions'],
    ['hourly', 'HourlyForecast'],
    ['daily', 'DailyForecast'],
    ['alerts', 'Alerts'],
    ['details', 'Details'],
    ['settings', 'Settings']
  ]
  for (const [view, component] of cases) {
    assert.match(weatherChip, new RegExp(`case ['"]${view}['"]:[\\s\\S]*?activePanel = jsx\\(${component},`))
  }
  assert.match(weatherChip, /const viewContent = !settings\.location && activeView === ['"]current['"][\s\S]*?children: activePanel/)
  assert.match(weatherChip, /jsx\(ScrollArea, \{[\s\S]*?children: viewContent/)
})

test('keeps location controls in a distinct Settings view', () => {
  const settingsView = source.slice(source.indexOf('function Settings'), source.indexOf('function WeatherChip'))
  assert.match(settingsView, /jsx\(LocationSetup/)
  assert.match(settingsView, /Remove location/)
  assert.match(source, /case ['"]settings['"]:[\s\S]*?activePanel = jsx\(Settings,/)
  const currentCase = source.slice(source.indexOf("case 'current':"), source.indexOf('const viewContent ='))
  assert.doesNotMatch(currentCase, /Settings|LocationSetup|Remove location/)
})

test('orders a fixed header, bounded shared body, attribution, and bottom tabs', () => {
  const weatherChip = source.slice(source.indexOf('function WeatherChip'), source.indexOf('export default'))
  const body = weatherChip.slice(weatherChip.indexOf("const body = jsx('main'"), weatherChip.indexOf('const attribution ='))
  const panel = weatherChip.slice(weatherChip.indexOf("const panel = jsxs('div'"))

  assert.doesNotMatch(weatherChip, /scrollableViews/)
  assert.equal((weatherChip.match(/jsx\(ScrollArea/g) || []).length, 1)
  assert.match(body, /className: ['"]min-h-0 flex-1 overflow-hidden['"]/)
  assert.match(body, /jsx\(ScrollArea, \{[\s\S]*?className: ['"]h-full w-full['"][\s\S]*?children: viewContent/)
  assert.match(panel, /className: ['"]flex h-full min-h-0 flex-col['"]/)
  assert.match(panel, /children: \[header, body, attribution, tabBar\]/)
  assert.doesNotMatch(weatherChip, /VIEW_BODY_CLASS|max-h-/)
})

test('shows setup current hourly daily details settings and refresh controls', () => {
  for (const label of ['Choose location', 'Current conditions', 'Next 24 hours', 'Seven-day forecast', 'Details', 'Settings', 'Refresh weather']) {
    assert.ok(source.includes(label), `missing UI label: ${label}`)
  }
})

test('daily rows show rain amount probability wind and gust', () => {
  const daily = source.slice(source.indexOf('function DailyForecast'), source.indexOf('function Details'))
  for (const field of ['precipitationProbability', 'precipitation', 'windSpeed', 'windGust']) {
    assert.ok(daily.includes(`item.${field}`), `daily rows omit ${field}`)
  }
})

test('shows one-line provider attribution with accessible source links', () => {
  const weatherChip = source.slice(source.indexOf('function WeatherChip'), source.indexOf('export default'))
  const attribution = weatherChip.slice(weatherChip.indexOf("const attribution = jsx('footer'"), weatherChip.indexOf("const tabBar = jsx('nav'"))

  assert.match(attribution, /className: ['"][^'"]*shrink-0[^'"]*min-w-0[^'"]*['"]/)
  assert.match(attribution, /className: ['"][^'"]*text-\[0\.625rem\][^'"]*truncate[^'"]*whitespace-nowrap[^'"]*['"]/)
  assert.match(attribution, /'aria-label': ['"]Open Open-Meteo website['"]/)
  assert.match(attribution, /'aria-label': ['"]Open Environment and Climate Change Canada website['"]/)
  assert.match(attribution, /openExternal\(['"]https:\/\/open-meteo\.com\/['"]\)/)
  assert.match(attribution, /openExternal\(['"]https:\/\/weather\.gc\.ca\/warnings\/index_e\.html['"]\)/)
  assert.doesNotMatch(attribution, /whitespace-normal|flex-wrap/)
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
