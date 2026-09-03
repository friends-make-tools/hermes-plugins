/** Unified Hermes weather status chip and native popover. */
import {
  Badge,
  Button,
  Codicon,
  Input,
  Popover,
  PopoverContent,
  PopoverTrigger,
  ScrollArea,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Switch,
  cn,
  haptic,
  host,
  useQuery
} from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'weather'
const SETTINGS_VERSION = 1
const SETTINGS_KEY = 'settings'
const ALERT_STATE_KEY = 'alert-state'
const REFRESH_OPTIONS = [5, 10, 15, 30, 60]
const POPOVER_SQUARE_SIZE = 'min(24rem, calc(100vw - 1rem), calc(100vh - 1rem))'
const views = [
  { id: 'current', label: 'Current', icon: 'circle-large-outline' },
  { id: 'hourly', label: 'Hourly', icon: 'history' },
  { id: 'daily', label: 'Daily', icon: 'calendar' },
  { id: 'alerts', label: 'Alerts', icon: 'warning' },
  { id: 'details', label: 'Details', icon: 'list-unordered' },
  { id: 'settings', label: 'Settings', icon: 'settings-gear' }
]
const SEVERITY_RANK = { unknown: 0, minor: 1, moderate: 2, severe: 3, extreme: 4 }
const DEFAULT_SETTINGS = {
  version: SETTINGS_VERSION,
  location: null,
  units: 'metric',
  refreshMinutes: 10,
  alertNotifications: true,
  minimumSeverity: 'severe'
}

let pluginCtx = null

function normalizeSettings(value) {
  const source = value && typeof value === 'object' ? value : {}
  const refreshMinutes = REFRESH_OPTIONS.includes(Number(source.refreshMinutes))
    ? Number(source.refreshMinutes)
    : DEFAULT_SETTINGS.refreshMinutes
  return {
    version: SETTINGS_VERSION,
    location: source.location && Number.isFinite(Number(source.location.latitude))
      && Number.isFinite(Number(source.location.longitude)) ? source.location : null,
    units: source.units === 'imperial' ? 'imperial' : 'metric',
    refreshMinutes,
    alertNotifications: source.alertNotifications !== false,
    minimumSeverity: ['severe', 'extreme'].includes(source.minimumSeverity)
      ? source.minimumSeverity
      : DEFAULT_SETTINGS.minimumSeverity
  }
}

function readSettings() {
  return normalizeSettings(pluginCtx.storage.get(SETTINGS_KEY, DEFAULT_SETTINGS))
}

function persistSettings(settings) {
  pluginCtx.storage.set(SETTINGS_KEY, settings)
}

function alertFingerprint(alert) {
  return String(alert?.id || `${alert?.title || ''}|${alert?.onset || ''}`)
}

function alertStateFor(locationKey) {
  const stored = pluginCtx.storage.get(ALERT_STATE_KEY, null)
  if (!stored || stored.version !== 1 || stored.locationKey !== locationKey) {
    return { version: 1, locationKey, baselineEstablished: false, seenAlerts: {} }
  }
  return {
    version: 1,
    locationKey,
    baselineEstablished: Boolean(stored.baselineEstablished),
    seenAlerts: stored.seenAlerts && typeof stored.seenAlerts === 'object' ? stored.seenAlerts : {}
  }
}

function rememberAndNotifyAlerts(alerts, settings, locationKey) {
  if (!locationKey || !Array.isArray(alerts)) return
  const state = alertStateFor(locationKey)
  const now = Date.now()
  const activeFingerprints = new Set(alerts.map(alertFingerprint))
  for (const [fingerprint, expiry] of Object.entries(state.seenAlerts)) {
    const expiryTime = Date.parse(expiry)
    if (Number.isFinite(expiryTime) && expiryTime <= now && !activeFingerprints.has(fingerprint)) {
      delete state.seenAlerts[fingerprint]
    }
  }

  const firstResult = !state.baselineEstablished
  const newAlerts = []
  for (const alert of alerts) {
    const fingerprint = alertFingerprint(alert)
    if (!state.seenAlerts[fingerprint]) newAlerts.push(alert)
    state.seenAlerts[fingerprint] = alert.expires || new Date(now + 24 * 60 * 60 * 1000).toISOString()
  }
  state.baselineEstablished = true
  pluginCtx.storage.set(ALERT_STATE_KEY, state)

  if (firstResult || !settings.alertNotifications) return
  const minimum = SEVERITY_RANK[settings.minimumSeverity] ?? SEVERITY_RANK.severe
  for (const alert of newAlerts) {
    if (!alert.isOfficial || (SEVERITY_RANK[alert.severity] ?? 0) < minimum) continue
    const notification = {
      title: alert.title,
      body: alert.description,
      silent: false
    }
    if (document.hasFocus()) {
      host.notify({ kind: 'warning', title: alert.title, message: alert.description })
    } else {
      void pluginCtx.os.notify(notification)
    }
  }
}

function numberText(value, digits = 0) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : '—'
}

function temperature(value, units) {
  return `${numberText(value)}°${units === 'imperial' ? 'F' : 'C'}`
}

function shortTime(value) {
  const date = value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

function dayName(value) {
  const date = value ? new Date(`${value}T12:00:00`) : null
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleDateString([], { weekday: 'short' })
    : '—'
}

function weatherPath(settings) {
  const location = settings.location
  const params = new URLSearchParams({
    latitude: String(location.latitude),
    longitude: String(location.longitude),
    units: settings.units,
    name: location.name || 'Selected location',
    countryCode: location.countryCode || '',
    admin1: location.admin1 || '',
    timezone: location.timezone || 'auto'
  })
  return `/weather?${params.toString()}`
}

function section(title, children) {
  return jsxs('section', {
    className: 'flex flex-col gap-2',
    children: [
      jsx('h3', { className: 'text-xs font-semibold text-(--ui-text-secondary)', children: title }),
      children
    ]
  })
}

function detailRow(label, value) {
  return jsxs('div', {
    className: 'flex items-center justify-between gap-3 text-xs',
    children: [
      jsx('span', { className: 'text-(--ui-text-tertiary)', children: label }),
      jsx('span', { className: 'text-right text-(--ui-text-primary)', children: value })
    ]
  })
}

function LocationSetup({ onSelect, title = 'Choose location' }) {
  const [term, setTerm] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')

  async function searchLocations(event) {
    event?.preventDefault()
    const query = term.trim()
    if (query.length < 2) {
      setSearchError('Enter at least two characters.')
      return
    }
    setSearching(true)
    setSearchError('')
    try {
      const payload = await pluginCtx.rest('/locations?' + new URLSearchParams({ q: query }), { timeoutMs: 15000 })
      setResults(Array.isArray(payload?.locations) ? payload.locations : [])
    } catch {
      setSearchError('Location search is unavailable.')
    } finally {
      setSearching(false)
    }
  }

  return section(title, jsxs('form', {
    className: 'flex flex-col gap-2',
    onSubmit: searchLocations,
    children: [
      jsxs('div', {
        className: 'flex gap-2',
        children: [
          jsx(Input, {
            value: term,
            onChange: event => setTerm(event.target.value),
            placeholder: 'City or place',
            'aria-label': 'Location search'
          }),
          jsx(Button, { type: 'submit', disabled: searching, children: searching ? 'Searching…' : 'Search' })
        ]
      }),
      searchError ? jsx('p', { className: 'text-xs text-(--ui-text-secondary)', children: searchError }) : null,
      results.length === 0 && !searching
        ? jsx('p', { className: 'text-xs text-(--ui-text-tertiary)', children: 'Search manually to set your weather location.' })
        : null,
      ...results.map(location => jsx(Button, {
        type: 'button',
        variant: 'ghost',
        className: 'justify-start text-left',
        onClick: () => onSelect(location),
        children: location.displayName
      }, location.id))
    ]
  }))
}

function Alerts({ data }) {
  const status = data?.provider?.alerts?.status
  if (status === 'error') {
    return section('Active alerts', jsx('p', {
      className: 'text-xs text-(--ui-text-secondary)',
      children: 'Official alerts unavailable. Forecast data remains available.'
    }))
  }
  if (!data?.alerts?.length) return null
  return section('Active alerts', jsx('div', {
    className: 'flex flex-col gap-2',
    children: data.alerts.map(alert => jsxs('article', {
      className: 'rounded-md border border-(--ui-stroke-secondary) p-2',
      children: [
        jsxs('div', {
          className: 'mb-1 flex items-center gap-2',
          children: [
            jsx(Badge, { children: alert.severity }),
            jsx('strong', { className: 'text-xs', children: alert.title })
          ]
        }),
        jsx('p', { className: 'whitespace-pre-wrap text-xs text-(--ui-text-secondary)', children: alert.description }),
        jsx(Button, {
          type: 'button',
          variant: 'ghost',
          className: 'mt-1 px-0 text-xs',
          onClick: () => void pluginCtx.os.openExternal(alert.sourceUrl),
          children: 'Environment and Climate Change Canada'
        })
      ]
    }, alert.id))
  }))
}

function CurrentConditions({ data, units }) {
  const current = data?.current
  if (!current) {
    return section('Current conditions', jsx('p', {
      className: 'text-xs text-(--ui-text-secondary)',
      children: data?.provider?.forecast?.error || 'Forecast unavailable.'
    }))
  }
  return section('Current conditions', jsxs('div', {
    className: 'flex items-center justify-between',
    children: [
      jsxs('div', {
        children: [
          jsx('div', { className: 'text-2xl', children: `${current.icon} ${temperature(current.temperature, units)}` }),
          jsx('div', { className: 'text-xs text-(--ui-text-secondary)', children: current.condition })
        ]
      }),
      jsx('div', {
        className: 'text-right text-xs text-(--ui-text-tertiary)',
        children: `Feels like ${temperature(current.apparentTemperature, units)}`
      })
    ]
  }))
}

function HourlyForecast({ items, units }) {
  return section('Next 24 hours', jsx('div', {
    className: 'flex gap-3 overflow-x-auto pb-1',
    children: (items || []).map(item => jsxs('div', {
      className: 'flex min-w-14 flex-col items-center gap-1 text-xs',
      children: [
        jsx('span', { className: 'text-(--ui-text-tertiary)', children: shortTime(item.time) }),
        jsx('span', { children: item.icon }),
        jsx('span', { children: temperature(item.temperature, units) }),
        jsx('span', { className: 'text-(--ui-text-tertiary)', children: `${numberText(item.precipitationProbability)}%` })
      ]
    }, item.time))
  }))
}

function DailyForecast({ items, units }) {
  const speedUnit = units === 'imperial' ? 'mph' : 'km/h'
  const amountUnit = units === 'imperial' ? 'in' : 'mm'
  return section('Seven-day forecast', jsx('div', {
    className: 'flex flex-col gap-2',
    children: (items || []).map(item => jsxs('div', {
      className: 'rounded-md border border-(--ui-stroke-secondary) p-2',
      children: [
        jsxs('div', {
          className: 'grid grid-cols-[3rem_1.5rem_1fr_auto] items-center gap-2 text-xs',
          children: [
            jsx('span', { children: dayName(item.date) }),
            jsx('span', { children: item.icon }),
            jsx('span', { className: 'truncate text-(--ui-text-secondary)', children: item.condition }),
            jsx('span', { children: `${temperature(item.temperatureMax, units)} / ${temperature(item.temperatureMin, units)}` })
          ]
        }),
        jsx('p', {
          className: 'mt-1 text-[0.6875rem] text-(--ui-text-tertiary)',
          children: `Rain ${numberText(item.precipitationProbability)}% · ${numberText(item.precipitation, 1)} ${amountUnit} · Wind ${numberText(item.windSpeed)} ${speedUnit} · Gust ${numberText(item.windGust)} ${speedUnit}`
        })
      ]
    }, item.date))
  }))
}

function Details({ data, units }) {
  const current = data?.current || {}
  const today = data?.daily?.[0] || {}
  const hour = data?.hourly?.[0] || {}
  const speedUnit = units === 'imperial' ? 'mph' : 'km/h'
  const amountUnit = units === 'imperial' ? 'in' : 'mm'
  return section('Details', jsx('div', {
    className: 'flex flex-col gap-1',
    children: [
      detailRow('Rain chance', `${numberText(hour.precipitationProbability)}%`),
      detailRow('Rain amount', `${numberText(current.precipitation, 1)} ${amountUnit}`),
      detailRow('Humidity', `${numberText(current.humidity)}%`),
      detailRow('Wind', `${numberText(current.windSpeed)} ${speedUnit} · ${numberText(current.windDirection)}°`),
      detailRow('Gust', `${numberText(current.windGust)} ${speedUnit}`),
      detailRow('Visibility', `${numberText(Number(current.visibility) / (units === 'imperial' ? 1609.344 : 1000), 1)} ${units === 'imperial' ? 'mi' : 'km'}`),
      detailRow('Pressure', `${numberText(current.pressure)} hPa`),
      detailRow('Sunrise / sunset', `${shortTime(today.sunrise)} / ${shortTime(today.sunset)}`),
      detailRow('Last successful update', shortTime(data?.fetchedAt))
    ]
  }))
}

function settingSelect(value, onValueChange, options, label) {
  return jsxs(Select, {
    value: String(value),
    onValueChange,
    children: [
      jsx(SelectTrigger, {
        className: 'min-w-28',
        'aria-label': label,
        children: jsx(SelectValue, {})
      }),
      jsx(SelectContent, {
        children: options.map(option => jsx(SelectItem, {
          value: String(option.value),
          children: option.label
        }, option.value))
      })
    ]
  })
}

function Settings({ settings, onChange, onSelectLocation, removeLocation }) {
  return section('Settings', jsxs('div', {
    className: 'flex flex-col gap-2 text-xs',
    children: [
      jsxs('label', {
        className: 'flex items-center justify-between gap-2',
        children: [
          jsx('span', { children: 'Units' }),
          settingSelect(settings.units, units => onChange({ units }), [
            { value: 'metric', label: 'Metric' },
            { value: 'imperial', label: 'Imperial' }
          ], 'Units')
        ]
      }),
      jsxs('label', {
        className: 'flex items-center justify-between gap-2',
        children: [
          jsx('span', { children: 'Refresh interval' }),
          settingSelect(
            settings.refreshMinutes,
            value => onChange({ refreshMinutes: Number(value) }),
            REFRESH_OPTIONS.map(value => ({ value, label: `${value} minutes` })),
            'Refresh interval'
          )
        ]
      }),
      jsxs('label', {
        className: 'flex items-center justify-between gap-2',
        children: [
          jsx('span', { children: 'Alert notifications' }),
          jsx(Switch, {
            checked: settings.alertNotifications,
            onCheckedChange: checked => onChange({ alertNotifications: Boolean(checked) })
          })
        ]
      }),
      jsxs('label', {
        className: 'flex items-center justify-between gap-2',
        children: [
          jsx('span', { children: 'Minimum severity' }),
          settingSelect(settings.minimumSeverity, minimumSeverity => onChange({ minimumSeverity }), [
            { value: 'severe', label: 'Severe' },
            { value: 'extreme', label: 'Extreme' }
          ], 'Minimum severity')
        ]
      }),
      jsx(Separator, {}),
      jsx(LocationSetup, { onSelect: onSelectLocation, title: 'Change location' }),
      jsx(Button, { type: 'button', variant: 'ghost', onClick: removeLocation, children: 'Remove location' })
    ]
  }))
}

function WeatherChip() {
  const [settings, setSettings] = useState(readSettings)
  const [activeView, setActiveView] = useState('current')
  const locationKey = settings.location
    ? [
        settings.location.latitude,
        settings.location.longitude,
        settings.location.timezone,
        settings.location.countryCode,
        settings.location.name
      ].join('|')
    : 'none'
  const query = useQuery({
    queryKey: [ID, 'weather', locationKey, settings.units],
    enabled: Boolean(settings.location),
    queryFn: () => pluginCtx.rest(weatherPath(settings), { timeoutMs: 15000 }),
    refetchInterval: settings.refreshMinutes * 60 * 1000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
    retry: false,
    staleTime: 5 * 60 * 1000
  })
  const data = query.data

  useEffect(() => {
    rememberAndNotifyAlerts(data?.alerts, settings, locationKey)
  }, [data?.alerts, settings.alertNotifications, settings.minimumSeverity, locationKey])

  const chipLabel = useMemo(() => {
    if (!settings.location) return '☀ Choose location'
    if (!data && query.isLoading) return '☀ Loading…'
    if (!data) return '☀ Weather unavailable'
    const current = data.current
    const main = current
      ? `${current.icon} ${temperature(current.temperature, settings.units)} ${current.condition}`
      : '☀ Forecast unavailable'
    return `${main}${data.alerts?.length ? ' ⚠' : ''}${query.isError ? ' · stale' : ''}`
  }, [settings.location, settings.units, data, query.isLoading, query.isError])

  function updateSettings(patch) {
    setSettings(previous => {
      const next = normalizeSettings({ ...previous, ...patch })
      persistSettings(next)
      return next
    })
  }

  function selectLocation(location) {
    updateSettings({ location })
  }

  function removeLocation() {
    updateSettings({ location: null })
    pluginCtx.storage.remove(ALERT_STATE_KEY)
  }

  let activePanel = null
  switch (activeView) {
    case 'hourly':
      activePanel = jsx(HourlyForecast, { items: data?.hourly, units: settings.units })
      break
    case 'daily':
      activePanel = jsx(DailyForecast, { items: data?.daily, units: settings.units })
      break
    case 'alerts':
      activePanel = jsx(Alerts, { data })
      break
    case 'details':
      activePanel = jsx(Details, { data, units: settings.units })
      break
    case 'settings':
      activePanel = jsx(Settings, {
        settings,
        onChange: updateSettings,
        onSelectLocation: selectLocation,
        removeLocation
      })
      break
    case 'current':
    default:
      activePanel = jsx(CurrentConditions, { data, units: settings.units })
  }

  const viewContent = !settings.location && activeView === 'current'
    ? jsx('div', {
        className: 'p-3',
        children: jsx(LocationSetup, { onSelect: selectLocation })
      })
    : jsxs('div', {
        className: 'flex flex-col gap-3 p-3',
        children: [
          query.isError && data ? jsx('p', {
            className: 'text-xs text-(--ui-text-secondary)',
            children: `Stale data. Last successful update ${shortTime(data.fetchedAt)}.`
          }) : null,
          jsx('div', {
            id: 'weather-active-panel',
            role: 'tabpanel',
            'aria-label': `${activeView} weather view`,
            children: activePanel
          })
        ]
      })

  const header = jsxs('header', {
    className: 'flex shrink-0 items-center justify-between gap-2 border-b border-(--ui-stroke-secondary) p-3',
    children: [
      jsx('strong', {
        className: 'truncate text-sm',
        children: settings.location?.displayName || 'Choose location'
      }),
      jsx(Button, {
        type: 'button',
        variant: 'ghost',
        size: 'icon',
        className: 'size-7 shrink-0 p-0',
        'aria-label': 'Refresh weather',
        title: 'Refresh weather',
        disabled: !settings.location || query.isFetching,
        onClick: () => void query.refetch(),
        children: jsx(Codicon, { name: 'refresh', size: 14, spinning: query.isFetching })
      })
    ]
  })

  const body = jsx('main', {
    className: 'min-h-0 flex-1 overflow-hidden',
    style: { flex: '1 1 0%', minHeight: 0, overflow: 'hidden' },
    children: jsx(ScrollArea, {
      className: 'h-full w-full',
      style: { width: '100%', height: '100%' },
      children: viewContent
    })
  })

  const attribution = jsx('footer', {
    className: 'shrink-0 min-w-0 overflow-hidden border-t border-(--ui-stroke-secondary) px-3 py-1',
    children: jsxs('p', {
      className: 'text-[0.625rem] text-(--ui-text-tertiary) truncate whitespace-nowrap',
      title: 'Weather data by Open-Meteo · Official Canadian alerts by Environment and Climate Change Canada',
      children: [
        jsx('button', {
          type: 'button',
          className: 'underline',
          'aria-label': 'Open Open-Meteo website',
          onClick: () => void pluginCtx.os.openExternal('https://open-meteo.com/'),
          children: 'Weather data by Open-Meteo'
        }),
        ' · ',
        jsx('button', {
          type: 'button',
          className: 'underline',
          'aria-label': 'Open Environment and Climate Change Canada website',
          onClick: () => void pluginCtx.os.openExternal('https://weather.gc.ca/warnings/index_e.html'),
          children: 'Official Canadian alerts by Environment and Climate Change Canada'
        })
      ]
    })
  })

  const tabBar = jsx('nav', {
    role: 'tablist',
    'aria-label': 'Weather views',
    className: 'flex shrink-0 flex-nowrap overflow-hidden border-t border-(--ui-stroke-secondary) p-1',
    children: views.map(view => jsxs(Button, {
      type: 'button',
      role: 'tab',
      size: 'sm',
      variant: activeView === view.id ? 'secondary' : 'ghost',
      className: 'h-auto min-w-0 flex-1 flex-col gap-0.5 px-0.5 py-1 text-[0.625rem] leading-none whitespace-nowrap',
      'aria-label': view.label,
      'aria-selected': activeView === view.id,
      'aria-controls': 'weather-active-panel',
      onClick: () => setActiveView(view.id),
      children: [
        jsx(Codicon, { name: view.icon, size: 14 }),
        jsx('span', { className: 'truncate', children: view.label })
      ]
    }, view.id))
  })

  const panel = jsxs('div', {
    className: 'flex h-full min-h-0 flex-col',
    style: {
      display: 'flex',
      height: '100%',
      minHeight: 0,
      overflow: 'hidden',
      flexDirection: 'column'
    },
    children: [header, body, attribution, tabBar]
  })

  return jsx(Popover, {
    children: jsxs('div', {
      children: [
        jsx(PopoverTrigger, {
          asChild: true,
          children: jsx('button', {
            type: 'button',
            title: settings.location ? settings.location.displayName : 'Choose a weather location',
            className: cn(
              'inline-flex h-full min-w-28 items-center justify-center px-1.5 text-[0.6875rem] transition-opacity',
              query.isError ? 'opacity-70 text-(--ui-text-secondary)' : 'text-(--ui-text-primary) hover:bg-(--chrome-action-hover)'
            ),
            onClick: () => haptic('tap'),
            children: chipLabel
          })
        }),
        jsx(PopoverContent, {
          side: 'top',
          align: 'end',
          sideOffset: 6,
          className: 'p-0',
          style: {
            width: POPOVER_SQUARE_SIZE,
            height: POPOVER_SQUARE_SIZE
          },
          children: panel
        })
      ]
    })
  })
}

export default {
  id: ID,
  name: 'Weather',
  defaultEnabled: false,
  register(ctx) {
    pluginCtx = ctx
    ctx.register({
      id: 'weather-chip',
      area: 'statusBar.right',
      order: 125,
      render: () => jsx(WeatherChip, {})
    })
  }
}
