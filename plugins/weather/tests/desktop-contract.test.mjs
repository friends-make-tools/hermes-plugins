import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const pluginUrl = new URL('../desktop/plugin.js', import.meta.url)
const source = readFileSync(pluginUrl, 'utf8')

function renderCurrentHero(apparentTemperature) {
  const numberHelpers = source.slice(source.indexOf('function numberText'), source.indexOf('function formatTime'))
  const unitHelpers = source.slice(source.indexOf('function isFiniteNumber'), source.indexOf('function dayName'))
  const heroSource = source.slice(source.indexOf('function CurrentHero'), source.indexOf('function NextSixHours'))
  const element = (type, props) => ({ type, props })
  const CurrentHero = Function(
    'jsx',
    'jsxs',
    'section',
    'localDateTime',
    `${numberHelpers}\n${unitHelpers}\n${heroSource}\nreturn CurrentHero`
  )(element, element, (title, children) => ({ title, children }), () => 'local time')

  return CurrentHero({
    current: {
      apparentTemperature,
      condition: 'Clear',
      humidity: 50,
      icon: '☀',
      precipitation: 0,
      temperature: 22,
      windSpeed: 5
    },
    units: 'metric',
    updatedAt: '2026-09-02T18:00:00Z',
    timeZone: 'America/Toronto'
  })
}

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

test('uses inline geometry for the responsive square and scroll containment', () => {
  const squareSize = source.match(/const POPOVER_SQUARE_SIZE = ['"]([^'"]+)['"]/)?.[1]
  assert.equal(squareSize, 'min(24rem, calc(100vw - 1rem), calc(100vh - 1rem))')

  const weatherChip = source.slice(source.indexOf('function WeatherChip'), source.indexOf('export default'))
  const body = weatherChip.slice(weatherChip.indexOf("const body = jsx('main'"), weatherChip.indexOf('const attribution ='))
  const panel = weatherChip.slice(weatherChip.indexOf("const panel = jsxs('div'"), weatherChip.indexOf('return jsx(Popover'))
  const popoverContent = weatherChip.slice(weatherChip.indexOf('jsx(PopoverContent'))

  assert.match(popoverContent, /style: \{\s*width: POPOVER_SQUARE_SIZE,\s*height: POPOVER_SQUARE_SIZE\s*\}/)
  assert.match(panel, /style: \{\s*display: ['"]flex['"],\s*height: ['"]100%['"],\s*minHeight: 0,\s*overflow: ['"]hidden['"],\s*flexDirection: ['"]column['"]\s*\}/)
  assert.match(body, /style: \{ flex: ['"]1 1 0%['"], minHeight: 0, overflow: ['"]hidden['"] \}/)
  assert.match(body, /jsx\(ScrollArea, \{[\s\S]*?style: \{ width: ['"]100%['"], height: ['"]100%['"] \}/)
  assert.doesNotMatch(source, /POPOVER_SQUARE_CLASS|[hw]-\[min\(/)
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

test('shows only the active view and defaults to Forecast', () => {
  assert.match(source, /const \[activeView, setActiveView\] = useState\(['"]forecast['"]\)/)
  assert.match(source, /switch \(activeView\)/)
  assert.match(source, /children:\s*activePanel/)
})

test('shows native buttons for exactly four weather views', () => {
  const viewDefinitions = source.slice(source.indexOf('const views = ['), source.indexOf('const SEVERITY_RANK'))
  for (const [id, label] of [
    ['forecast', 'Forecast'],
    ['alerts', 'Alerts'],
    ['details', 'Details'],
    ['settings', 'Settings']
  ]) {
    assert.match(viewDefinitions, new RegExp(`id: ['"]${id}['"], label: ['"]${label}['"], icon: ['"][^'"]+['"]`))
  }
  assert.equal((viewDefinitions.match(/\bid:/g) || []).length, 4)
  assert.doesNotMatch(viewDefinitions, /id: ['"](?:current|hourly|daily)['"]/)
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
  assert.match(tabBar, /className: ['"][^'"]*min-w-0[^'"]*flex-1[^'"]*text-xs[^'"]*whitespace-nowrap[^'"]*['"]/)
  assert.match(tabBar, /jsx\(Codicon, \{ name: view\.icon/)
  assert.doesNotMatch(tabBar, /grid-cols-|flex-wrap/)
})

test('routes all four weather views through the shared ScrollArea', () => {
  const weatherChip = source.slice(source.indexOf('function WeatherChip'), source.indexOf('export default'))
  const cases = [
    ['forecast', 'Forecast'],
    ['alerts', 'Alerts'],
    ['details', 'Details'],
    ['settings', 'Settings']
  ]
  for (const [view, component] of cases) {
    assert.match(weatherChip, new RegExp(`case ['"]${view}['"]:[\\s\\S]*?activePanel = jsx\\(${component},`))
  }
  assert.match(weatherChip, /const viewContent = !settings\.location && activeView === ['"]forecast['"][\s\S]*?children: activePanel/)
  assert.match(weatherChip, /jsx\(ScrollArea, \{[\s\S]*?children: viewContent/)
  assert.doesNotMatch(weatherChip, /case ['"](?:current|hourly|daily)['"]:/)
})

test('keeps location controls in a distinct Settings view', () => {
  const settingsView = source.slice(source.indexOf('function Settings'), source.indexOf('function WeatherChip'))
  assert.match(settingsView, /jsx\(LocationSetup/)
  assert.match(settingsView, /Remove location/)
  assert.match(source, /case ['"]settings['"]:[\s\S]*?activePanel = jsx\(Settings,/)
  const forecastView = source.slice(source.indexOf('function Forecast'), source.indexOf('function Details'))
  assert.doesNotMatch(forecastView, /Settings|LocationSetup|Remove location/)
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

test('shows setup combined forecast details settings and refresh controls', () => {
  for (const label of ['Choose location', 'Current conditions', 'Next six hours', 'Seven-day forecast', 'Details', 'Settings', 'Refresh weather']) {
    assert.ok(source.includes(label), `missing UI label: ${label}`)
  }
})

test('uses explicit current-condition hero icon sizing next to the temperature', () => {
  const hero = source.slice(source.indexOf('function CurrentHero'), source.indexOf('function NextSixHours'))

  assert.match(hero, /style: \{ gridTemplateColumns: ['"]auto minmax\(0, 1fr\)['"] \}/)
  assert.match(hero, /style: \{ fontSize: ['"]3\.5rem['"], lineHeight: 1 \}/)
  assert.doesNotMatch(hero, /\btext-(?:4|5|6|7|8|9)xl\b/)
})

test('suppresses feels-like text when apparent temperature is null', () => {
  assert.doesNotMatch(JSON.stringify(renderCurrentHero(null)), /Feels like/)
})

test('displays a finite zero apparent temperature', () => {
  const hero = source.slice(source.indexOf('function CurrentHero'), source.indexOf('function NextSixHours'))

  assert.match(hero, /isFiniteNumber\(current\.apparentTemperature\)/)
  assert.match(JSON.stringify(renderCurrentHero(0)), /Feels like 0°C/)
})

test('keeps icon-based current metrics inside the hero', () => {
  const hero = source.slice(source.indexOf('function CurrentHero'), source.indexOf('function NextSixHours'))
  const forecast = source.slice(source.indexOf('function Forecast'), source.indexOf('function Details'))

  for (const field of ['precipitation', 'humidity', 'windSpeed']) {
    assert.ok(hero.includes(`current.${field}`), `current hero omits ${field}`)
  }
  assert.match(hero, /const metrics = \[/)
  assert.match(hero, /metrics\.map\(\(\{ label, icon, value \}\)/)
  assert.match(hero, /grid grid-cols-3/)
  assert.match(hero, /'aria-label': `\$\{label\}: \$\{value\}`/)
  assert.match(hero, /title: `\$\{label\}: \$\{value\}`/)
  assert.match(hero, /'aria-hidden': true, children: icon/)
  assert.doesNotMatch(source, /Current metrics|function CurrentMetrics/)
  assert.doesNotMatch(forecast, /jsx\(CurrentMetrics/)
})

test('formats the update date and time in the selected IANA timezone', () => {
  const helpers = source.slice(source.indexOf('function formatTime'), source.indexOf('function isFiniteNumber'))
  const helperModule = Function(`${helpers}; return { isValidDateValue, localDateTime }`)()
  const hero = source.slice(source.indexOf('function CurrentHero'), source.indexOf('function NextSixHours'))
  const forecast = source.slice(source.indexOf('function Forecast'), source.indexOf('function Details'))
  const weatherChip = source.slice(source.indexOf('function WeatherChip'), source.indexOf('export default'))

  assert.notEqual(
    helperModule.localDateTime('2026-09-02T18:00:00Z', 'America/Toronto'),
    helperModule.localDateTime('2026-09-02T18:00:00Z', 'Asia/Tokyo')
  )
  assert.equal(helperModule.localDateTime('not-a-date', 'America/Toronto'), '—')
  assert.equal(helperModule.isValidDateValue('not-a-date'), false)
  assert.match(helpers, /function localDateTime\(value, timeZone\)/)
  assert.match(helpers, /Intl\.DateTimeFormat\(\[\], options\)\.format\(date\)/)
  for (const part of ["weekday: 'short'", "month: 'short'", "day: 'numeric'", "hour: 'numeric'", "minute: '2-digit'"]) {
    assert.ok(helpers.includes(part), `local date and time omits ${part}`)
  }
  assert.match(hero, /localDateTime\(updatedAt, timeZone\)/)
  assert.match(hero, /Local time in \$\{timeZone\}/)
  assert.match(forecast, /isValidDateValue\(data\?\.sourceUpdatedAt\)\s*\? data\.sourceUpdatedAt\s*:\s*data\?\.fetchedAt/)
  assert.match(weatherChip, /timeZone:\s*settings\.location\?\.timezone \|\| data\?\.timezone \|\| ['"]UTC['"]/)
})

test('Forecast combines its current hero, six hours, and seven days', () => {
  const forecast = source.slice(source.indexOf('function CurrentHero'), source.indexOf('function Details'))

  assert.match(forecast, /function CurrentHero/)
  for (const field of ['icon', 'temperature', 'condition', 'apparentTemperature']) {
    assert.ok(forecast.includes(`current.${field}`), `current hero omits ${field}`)
  }
  assert.match(forecast, /function NextSixHours/)
  assert.match(forecast, /\.slice\(0, 6\)/)
  assert.match(forecast, /grid grid-cols-6/)
  assert.match(forecast, /function SevenDayForecast/)
  assert.match(forecast, /\.slice\(0, 7\)/)
  assert.match(forecast, /whitespace-nowrap/)
  assert.match(forecast, /function Forecast/)
  assert.match(forecast, /jsx\(CurrentHero/)
  assert.match(forecast, /jsx\(NextSixHours/)
  assert.match(forecast, /jsx\(SevenDayForecast/)
})

test('shows hourly rain only for finite numeric probabilities', () => {
  const helper = source.slice(source.indexOf('function isFiniteNumber'), source.indexOf('function dayName'))
  const hourly = source.slice(source.indexOf('function NextSixHours'), source.indexOf('function SevenDayForecast'))

  assert.match(helper, /typeof value === ['"]number['"] && Number\.isFinite\(value\)/)
  assert.match(hourly, /isFiniteNumber\(item\.precipitationProbability\)/)
})

test('daily rows use compact aligned icon and value cells', () => {
  const daily = source.slice(source.indexOf('function SevenDayForecast'), source.indexOf('function Forecast'))
  for (const field of ['temperatureMax', 'temperatureMin', 'precipitationProbability', 'precipitation', 'windSpeed']) {
    assert.ok(daily.includes(`item.${field}`), `daily rows omit ${field}`)
  }
  assert.match(daily, /dayName\(item\.date\)/)
  assert.match(daily, /compactDate\(item\.date\)/)
  assert.match(daily, /isFiniteNumber\(item\.precipitationProbability\)[\s\S]*?isFiniteNumber\(item\.precipitation\)/)
  assert.match(daily, /className: ['"][^'"]*whitespace-nowrap[^'"]*py-1[^'"]*text-xs[^'"]*['"]/)
  assert.doesNotMatch(daily, /py-1\.5|text-\[0\.6875rem\]/)
  assert.doesNotMatch(daily, /children: `(?:Rain|Wind) /)
})

test('daily icon cells preserve accessible condition rain and wind meanings', () => {
  const daily = source.slice(source.indexOf('function SevenDayForecast'), source.indexOf('function Forecast'))

  assert.match(daily, /'aria-label': item\.condition/)
  assert.match(daily, /title: item\.condition/)
  assert.match(daily, /'aria-label': `Rain: \$\{rainValue\}`/)
  assert.match(daily, /title: `Rain: \$\{rainValue\}`/)
  assert.match(daily, /'aria-label': `Wind: \$\{windValue\}`/)
  assert.match(daily, /title: `Wind: \$\{windValue\}`/)
  assert.ok((daily.match(/'aria-hidden': true/g) || []).length >= 2)
})

test('shows one-line dynamic active-provider attribution with accessible source links', () => {
  const weatherChip = source.slice(source.indexOf('function WeatherChip'), source.indexOf('export default'))
  const attribution = weatherChip.slice(weatherChip.indexOf("const attribution = jsx('footer'"), weatherChip.indexOf("const tabBar = jsx('nav'"))

  assert.match(attribution, /className: ['"][^'"]*shrink-0[^'"]*min-w-0[^'"]*['"]/)
  assert.match(attribution, /className: ['"][^'"]*text-\[0\.625rem\][^'"]*truncate[^'"]*whitespace-nowrap[^'"]*['"]/)
  assert.match(weatherChip, /data\?\.provider\?\.forecast\?\.name === ['"]MET Norway['"]/)
  assert.match(weatherChip, /forecastProviderName/)
  assert.match(weatherChip, /forecastProviderUrl/)
  assert.match(attribution, /'aria-label': `Open \$\{forecastProviderName\} website`/)
  assert.match(attribution, /'aria-label': ['"]Open Environment and Climate Change Canada website['"]/)
  assert.match(attribution, /openExternal\(forecastProviderUrl\)/)
  assert.match(weatherChip, /https:\/\/open-meteo\.com\//)
  assert.match(weatherChip, /https:\/\/www\.met\.no\/en/)
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
