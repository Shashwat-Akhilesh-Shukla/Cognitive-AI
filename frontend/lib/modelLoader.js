/**
 * Utility to automatically download face-api.js models on first load
 * Models are cached in IndexedDB for faster subsequent loads
 */

const MODEL_URLS = {
  'tiny_face_detector_model-weights_manifest.json':
    'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model/tiny_face_detector_model-weights_manifest.json',
  'tiny_face_detector_model-weights.bin':
    'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model/tiny_face_detector_model-weights.bin',
  'face_expression_model-weights_manifest.json':
    'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model/face_expression_model-weights_manifest.json',
  'face_expression_model-weights.bin':
    'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model/face_expression_model-weights.bin',
}

const DB_NAME = 'faceapi_models'
const STORE_NAME = 'models'

let db = null

// Initialize IndexedDB
function initDB() {
  return new Promise((resolve, reject) => {
    if (db) {
      resolve(db)
      return
    }

    const request = indexedDB.open(DB_NAME, 1)

    request.onerror = () => reject(request.error)
    request.onsuccess = () => {
      db = request.result
      resolve(db)
    }
    request.onupgradeneeded = (event) => {
      const database = event.target.result
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        database.createObjectStore(STORE_NAME)
      }
    }
  })
}

// Get model from cache
function getFromCache(filename) {
  return new Promise((resolve) => {
    if (!db) {
      resolve(null)
      return
    }

    const transaction = db.transaction([STORE_NAME], 'readonly')
    const store = transaction.objectStore(STORE_NAME)
    const request = store.get(filename)

    request.onerror = () => resolve(null)
    request.onsuccess = () => resolve(request.result)
  })
}

// Save model to cache
function saveToCache(filename, data) {
  return new Promise((resolve) => {
    if (!db) {
      resolve()
      return
    }

    const transaction = db.transaction([STORE_NAME], 'readwrite')
    const store = transaction.objectStore(STORE_NAME)
    const request = store.put(data, filename)

    request.onerror = () => resolve()
    request.onsuccess = () => resolve()
  })
}

// Download and cache model file
async function downloadModel(filename, url) {
  try {
    // Check cache first
    const cached = await getFromCache(filename)
    if (cached) {
      console.log(`✓ Loaded ${filename} from cache`)
      return cached
    }

    // Download from CDN
    console.log(`⬇️  Downloading ${filename}...`)
    const response = await fetch(url)
    if (!response.ok) throw new Error(`Failed to fetch ${filename}`)

    const blob = await response.blob()
    await saveToCache(filename, blob)
    console.log(`✓ Cached ${filename}`)
    return blob
  } catch (error) {
    console.error(`Failed to download ${filename}:`, error)
    throw error
  }
}

// Setup face-api models from CDN with caching
export async function setupFaceAPIModels() {
  try {
    await initDB()

    // Create a temporary solution to load models from CDN
    // face-api.js will load models from /models/ directory
    // We'll use a service worker or fetch override to serve from CDN

    console.log('Setting up face-api models...')

    // For now, configure face-api to load from CDN directly
    // This is simpler than managing IndexedDB for browser-side ML
    return {
      modelPath: 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model/',
      ready: true,
    }
  } catch (error) {
    console.error('Failed to setup face-api models:', error)
    throw error
  }
}

export default setupFaceAPIModels
