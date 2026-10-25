import assert from 'node:assert/strict'
import test from 'node:test'

import { createKrogerPicker } from '../widgets/kroger-pick.mjs'

const key = (overrides = {}, ch = '') => ({
  ch,
  key: {
    ctrl: false,
    downArrow: false,
    escape: false,
    leftArrow: false,
    return: false,
    rightArrow: false,
    upArrow: false,
    ...overrides
  }
})

const payload = products => JSON.stringify({
  products,
  query: 'milk',
  schema: 'kroger.recommendations.v1',
  success: true
})

const product = (upc, outOfStock = false) => ({
  brand: 'Simple Truth',
  description: `Milk ${upc}`,
  ingredient_data_known: true,
  last_purchased_date: null,
  out_of_stock: outOfStock,
  price: 4.99,
  previously_purchased: false,
  size: '64 fl oz',
  unit_price: '$0.08/fl oz',
  unwanted_ingredient_count: 0,
  unwanted_ingredients: [],
  upc
})

function fakeSdk() {
  const sdk = {
    Box: 'Box',
    Dialog: 'Dialog',
    Overlay: 'Overlay',
    Text: 'Text',
    WidgetGrid: 'WidgetGrid',
    defineWidgetApp(app) {
      sdk.app = app
      return app
    },
    h(type, props, ...children) {
      return { children, props, type }
    },
    isCtrl: () => false,
    updateWidget(_app, update) {
      if (sdk.state) sdk.state = update(sdk.state)
    }
  }
  return sdk
}

const flush = () => new Promise(resolve => setImmediate(resolve))

test('loads versioned recommendations and selects the first in-stock product', async () => {
  const sdk = fakeSdk()
  const calls = []
  const app = createKrogerPicker(sdk, {
    runPython: async args => {
      calls.push(args)
      return { stderr: '', stdout: payload([product('out', true), product('in')]) }
    }
  })

  sdk.state = app.init('milk')
  await flush()

  assert.deepEqual(calls, [['-m', 'kroger_shopping', 'recommend', 'milk', '--limit', '10', '--json']])
  assert.equal(sdk.state.phase, 'ready')
  assert.equal(sdk.state.selectedIndex, 1)
})

test('navigation skips unavailable products and selection does not write to the cart', async () => {
  const sdk = fakeSdk()
  let addCalls = 0
  const app = createKrogerPicker(sdk, {
    runPython: async args => {
      if (args.includes('add')) addCalls += 1
      return { stderr: '', stdout: payload([product('one'), product('out', true), product('three')]) }
    }
  })

  sdk.state = app.init('milk')
  await flush()
  sdk.state = app.reduce(sdk.state, key({ downArrow: true }))
  assert.equal(sdk.state.selectedIndex, 2)

  sdk.state = app.reduce(sdk.state, key({ return: true }))
  assert.equal(sdk.state.phase, 'confirm')
  assert.equal(addCalls, 0)
})

test('explicit confirmation adds one DELIVERY item once and retains a success screen', async () => {
  const sdk = fakeSdk()
  const calls = []
  let finishAdd
  const app = createKrogerPicker(sdk, {
    runPython: args => {
      calls.push(args)
      if (args.includes('recommend')) {
        return Promise.resolve({ stderr: '', stdout: payload([product('0001111050434')]) })
      }
      return new Promise(resolve => { finishAdd = resolve })
    }
  })

  sdk.state = app.init('milk')
  await flush()
  sdk.state = app.reduce(sdk.state, key({ return: true }))
  sdk.state = app.reduce(sdk.state, key({ return: true }))
  assert.equal(sdk.state.phase, 'adding')

  const duplicate = app.reduce(sdk.state, key({ return: true }))
  assert.equal(duplicate, sdk.state)
  assert.equal(calls.length, 2)
  assert.deepEqual(calls[1], [
    '-m', 'kroger_shopping', 'add', '0001111050434',
    '--quantity', '1', '--modality', 'DELIVERY'
  ])

  finishAdd({ stderr: '', stdout: 'Added to cart: UPC 0001111050434, quantity 1, modality DELIVERY.\n' })
  await flush()
  assert.equal(sdk.state.phase, 'success')
  assert.equal(sdk.state.product.upc, '0001111050434')
  assert.equal(app.reduce(sdk.state, key({ return: true })), null)
})

test('an add failure keeps the modal open with the error', async () => {
  const sdk = fakeSdk()
  const app = createKrogerPicker(sdk, {
    runPython: async args => {
      if (args.includes('recommend')) return { stderr: '', stdout: payload([product('0001111050434')]) }
      const error = new Error('command failed')
      error.stderr = 'Kroger authorization expired'
      throw error
    }
  })

  sdk.state = app.init('milk')
  await flush()
  sdk.state = app.reduce(sdk.state, key({ return: true }))
  sdk.state = app.reduce(sdk.state, key({ return: true }))
  await flush()

  assert.equal(sdk.state.phase, 'error')
  assert.match(sdk.state.error, /authorization expired/)
  assert.notEqual(app.reduce(sdk.state, key()), null)
})
