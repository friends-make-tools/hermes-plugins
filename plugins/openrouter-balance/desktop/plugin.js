/**
 * OpenRouter Balance — desktop status bar chip (Hermes desktop plugin).
 *
 * Shows remaining OpenRouter prepaid balance and 30-day spend. Data comes
 * from this plugin's Python backend (GET /summary, scoped to
 * /api/plugins/openrouter-balance). The management key never reaches this
 * file — the backend reads it from $HERMES_HOME/.env (spec N1).
 *
 * Plain ESM, loaded uncompiled — UI is jsx() calls, not JSX syntax.
 * Only these imports resolve: @hermes/plugin-sdk, react, react/jsx-runtime.
 */

import { cn, haptic, host, Tip, useQuery } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

const ID = 'openrouter-balance'

// R5: poll interval (default 300 s). Edit this constant to reconfigure.
const REFRESH_INTERVAL_MS = 5 * 60 * 1000

// D5/R6: chip click target.
const ACTIVITY_URL = 'https://openrouter.ai/activity'

// Captured in register(); the component reads it for ctx.rest and ctx.os.
let pluginCtx = null

function money(n) {
  return typeof n === 'number' && Number.isFinite(n) ? `$${n.toFixed(2)}` : '$—'
}

function hhmm(iso) {
  const d = iso ? new Date(iso) : null
  if (!d || Number.isNaN(d.getTime())) return '—'
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function errText(err) {
  return err?.message || String(err)
}

// R3/R4: tooltip carries values, last-updated time, the window note, and any
// refresh error. R3 stale case shows "Last updated HH:MM" from this list.
function tipFor(data, error) {
  const parts = data
    ? [
        `Balance ${money(data.balance)}`,
        `Purchased ${money(data.total_credits)}`,
        `Used ${money(data.total_usage)}`,
        `30-day spend ${money(data.spend_30d)}`
      ]
    : ['Balance —']
  parts.push(`Last updated ${hhmm(data?.fetched_at)}`)
  parts.push('30-day window excludes today')
  if (error) parts.push(`Refresh failed: ${errText(error)}`)
  return parts.join(' · ')
}

// D3: 'OR $<balance> · 30d $<spend>'. R3: first-load failure shows 'OR: —'.
function chipLabel(data) {
  return data ? `OR ${money(data.balance)} · 30d ${money(data.spend_30d)}` : 'OR: —'
}

function BalanceChip() {
  // R2/D4: the poll loop belongs to React Query (refetchInterval). N4: retry
  // is off — a failed refresh keeps the prior data; the next attempt happens
  // on the interval, never sooner.
  const query = useQuery({
    queryKey: [ID, 'summary'],
    queryFn: async () => {
      try {
        const data = await pluginCtx.rest('/summary', { timeoutMs: 15000 })
        // Guard against a 502 body arriving as a resolved value.
        if (!data || typeof data.balance !== 'number' || typeof data.spend_30d !== 'number') {
          throw new Error(data?.error ? `backend: ${data.error}` : 'unexpected /summary payload')
        }
        return data
      } catch (err) {
        host.logs(`${ID}: /summary fetch failed:`, errText(err))
        throw err
      }
    },
    refetchInterval: REFRESH_INTERVAL_MS,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: false,
    retry: false,
    staleTime: 30_000
  })

  const data = query.data
  // R3: on error the chip keeps its last values and dims to secondary text.
  const dimmed = query.isError

  return jsx(Tip, {
    label: tipFor(data, query.error),
    children: jsx('button', {
      type: 'button',
      className: cn(
        'inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem] transition-colors',
        dimmed
          ? 'text-(--ui-text-secondary)'
          : 'text-foreground hover:bg-(--chrome-action-hover) hover:text-(--ui-accent)'
      ),
      onClick: () => {
        haptic('tap')
        const opened = pluginCtx.os.openExternal(ACTIVITY_URL)
        if (opened === false) host.logs(`${ID}: openExternal unavailable for ${ACTIVITY_URL}`)
      },
      children: chipLabel(data)
    })
  })
}

export default {
  id: ID, // must match the plugin folder name
  name: 'OpenRouter Balance',
  // Unified-package desktop half is opt-in (spec section 6): the user flips it
  // on in Settings → Plugins, beside the Python half's plugins.enabled gate.
  defaultEnabled: false,
  register(ctx) {
    pluginCtx = ctx
    ctx.register({
      id: 'balance-chip',
      area: 'statusBar.right',
      order: 130,
      render: () => jsx(BalanceChip, {})
    })
  }
}
