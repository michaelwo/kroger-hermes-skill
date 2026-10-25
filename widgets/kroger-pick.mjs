import { execFile } from 'node:child_process'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)
const SCHEMA = 'kroger.recommendations.v1'
const PAGE_SIZE = 6

function pluginDirectory() {
  const home = process.env.HERMES_HOME?.trim() || join(homedir(), '.hermes')
  return join(home, 'plugins', 'kroger-shopping')
}

async function defaultRunPython(args) {
  const python = process.env.HERMES_PYTHON?.trim()
  if (!python) throw new Error('HERMES_PYTHON is unavailable; launch the TUI through the Hermes command')
  return execFileAsync(python, args, {
    cwd: pluginDirectory(),
    env: process.env,
    maxBuffer: 1024 * 1024,
    timeout: 60_000
  })
}

function errorMessage(error) {
  const stderr = typeof error?.stderr === 'string' ? error.stderr.trim() : ''
  return stderr || (error instanceof Error ? error.message : String(error))
}

function firstSelectable(products) {
  return products.findIndex(product => !product.out_of_stock)
}

function moveSelection(products, current, direction) {
  if (!products.length) return -1
  for (let step = 1; step <= products.length; step += 1) {
    const index = (current + direction * step + products.length) % products.length
    if (!products[index].out_of_stock) return index
  }
  return -1
}

function parseRecommendations(stdout) {
  const payload = JSON.parse(stdout)
  if (payload?.schema !== SCHEMA || !Array.isArray(payload.products)) {
    throw new Error(`unsupported recommendation payload; expected ${SCHEMA}`)
  }
  return payload.products
}

export function createKrogerPicker(sdk, { runPython = defaultRunPython } = {}) {
  let app

  const update = transform => sdk.updateWidget(app, transform)

  const load = term => {
    runPython(['-m', 'kroger_shopping', 'recommend', term, '--limit', '10', '--json']).then(
      ({ stdout }) => {
        try {
          const products = parseRecommendations(stdout)
          update(state => ({
            ...state,
            error: null,
            phase: products.length ? 'ready' : 'empty',
            products,
            selectedIndex: firstSelectable(products)
          }))
        } catch (error) {
          update(state => ({ ...state, error: errorMessage(error), phase: 'error' }))
        }
      },
      error => update(state => ({ ...state, error: errorMessage(error), phase: 'error' }))
    )
  }

  const add = product => {
    runPython([
      '-m', 'kroger_shopping', 'add', product.upc,
      '--quantity', '1', '--modality', 'DELIVERY'
    ]).then(
      ({ stdout }) => update(state => ({ ...state, phase: 'success', product, success: stdout.trim() })),
      error => update(state => ({ ...state, error: errorMessage(error), phase: 'error' }))
    )
  }

  app = sdk.defineWidgetApp({
    id: 'kroger-pick',
    help: 'pick a ranked Kroger product and add one DELIVERY item',
    usage: 'usage: /kroger-pick <product search>',

    init(arg) {
      const term = arg.trim()
      if (!term) return null
      load(term)
      return { error: null, phase: 'loading', product: null, products: [], selectedIndex: -1, success: '', term }
    },

    reduce(state, { ch, key }) {
      if (state.phase === 'success' && (key.return || key.escape || ch === 'q')) return null
      if (key.escape || ch === 'q' || sdk.isCtrl(key, ch, 'c')) {
        if (state.phase === 'confirm') return { ...state, phase: 'ready' }
        return null
      }
      if (state.phase === 'error' && (ch === 'b' || key.leftArrow) && state.products.length) {
        return { ...state, error: null, phase: 'ready' }
      }
      if (state.phase === 'ready') {
        if (key.upArrow || key.leftArrow || ch === 'k' || ch === 'h') {
          return { ...state, selectedIndex: moveSelection(state.products, state.selectedIndex, -1) }
        }
        if (key.downArrow || key.rightArrow || ch === 'j' || ch === 'l') {
          return { ...state, selectedIndex: moveSelection(state.products, state.selectedIndex, 1) }
        }
        if ((key.return || ch === 'a') && state.selectedIndex >= 0) {
          const product = state.products[state.selectedIndex]
          if (!product.out_of_stock) return { ...state, phase: 'confirm', product }
        }
      }
      if (state.phase === 'confirm') {
        if (ch === 'b' || key.leftArrow) return { ...state, phase: 'ready' }
        if (key.return || ch === 'a') {
          add(state.product)
          return { ...state, phase: 'adding' }
        }
      }
      return state
    },

    render({ cols, state, t }) {
      const h = sdk.h
      const text = (value, color = t.color.text) => h(sdk.Text, { color }, String(value))
      const body = []

      if (state.phase === 'loading') body.push(text(`Searching Kroger for “${state.term}”…`, t.color.muted))
      if (state.phase === 'empty') body.push(text('No products found.', t.color.warn))
      if (state.phase === 'error') {
        body.push(text(state.error, t.color.error))
        body.push(text(state.products.length ? 'b/← back  ·  Esc close' : 'Esc close', t.color.muted))
      }
      if (state.phase === 'confirm' || state.phase === 'adding') {
        const product = state.product
        body.push(text(state.phase === 'adding' ? 'Adding to Kroger cart…' : 'Add to Kroger cart?', t.color.label))
        body.push(text(product.description))
        body.push(text(`UPC: ${product.upc}`, t.color.muted))
        body.push(text('Quantity: 1  ·  Modality: DELIVERY', t.color.muted))
        if (state.phase === 'confirm') body.push(text('Enter/a confirm  ·  b/← back  ·  Esc cancel', t.color.muted))
      }
      if (state.phase === 'success') {
        body.push(text('Added to Kroger cart', t.color.success ?? t.color.primary))
        body.push(text(state.product.description))
        body.push(text(`UPC: ${state.product.upc}`, t.color.label))
        body.push(text('Quantity: 1  ·  Modality: DELIVERY', t.color.muted))
        body.push(text('Enter or Esc to close', t.color.muted))
      }
      if (state.phase === 'ready') {
        const page = state.selectedIndex < 0 ? 0 : Math.floor(state.selectedIndex / PAGE_SIZE)
        const start = page * PAGE_SIZE
        const visible = state.products.slice(start, start + PAGE_SIZE)
        const widgets = visible.map((product, offset) => {
          const index = start + offset
          const selected = index === state.selectedIndex
          const disabled = product.out_of_stock
          const color = disabled ? t.color.muted : selected ? t.color.primary : t.color.border
          const price = product.price == null ? 'N/A' : `$${Number(product.price).toFixed(2)}`
          return {
            id: product.upc,
            children: h(sdk.Box, { borderColor: color, borderStyle: 'round', flexDirection: 'column', paddingX: 1 },
              text(`${selected ? '› ' : ''}${product.description}`, disabled ? t.color.muted : t.color.text),
              text(`${price}  ·  ${product.size || 'size N/A'}  ·  ${product.unit_price || 'unit N/A'}`, t.color.muted),
              text(`UPC ${product.upc}${disabled ? '  ·  OUT OF STOCK' : ''}`, disabled ? t.color.error : t.color.label),
              product.last_purchased_date ? text(`Last purchased ${product.last_purchased_date}`, t.color.muted) : null
            )
          }
        })
        body.push(h(sdk.WidgetGrid, { cols: Math.max(24, Math.min(cols - 8, 108)), maxColumns: 2, minColumnWidth: 42, widgets }))
        body.push(text(`Page ${page + 1}/${Math.max(1, Math.ceil(state.products.length / PAGE_SIZE))}  ·  arrows/jk move  ·  Enter review  ·  Esc close`, t.color.muted))
      }

      return h(sdk.Overlay, { zone: 'center' },
        h(sdk.Dialog, { title: `Kroger · ${state.term}`, width: Math.max(32, Math.min(cols - 4, 116)) },
          h(sdk.Box, { flexDirection: 'column', gap: 1 }, ...body)
        )
      )
    }
  })

  return app
}

export default function register(sdk) {
  createKrogerPicker(sdk)
}
