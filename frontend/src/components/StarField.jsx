// Full-viewport night sky behind the landing eyepiece. Canvas only, no extra libraries.
// Positions are fractions of the frame so a resize keeps the same stars.
import { useEffect, useRef } from 'react'

const STAR_COUNT = 280

function mulberry32(seed) {
  let a = seed
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function createStars(count) {
  const rand = mulberry32(0xa57e0)
  const stars = []
  for (let i = 0; i < count; i++) {
    const roll = rand()
    const bright = roll > 0.97
    const mid = !bright && roll > 0.84
    let color = '#f4f1ea'
    const tint = rand()
    if ((bright && tint > 0.45) || (mid && tint > 0.78)) {
      color = tint > 0.72 ? '#f0b07a' : '#a9c6ff'
    }
    stars.push({
      x: rand(),
      y: rand(),
      r: bright ? 1.35 + rand() * 1.05 : mid ? 0.85 + rand() * 0.45 : 0.4 + rand() * 0.45,
      alpha: bright ? 0.82 + rand() * 0.18 : mid ? 0.45 + rand() * 0.3 : 0.18 + rand() * 0.32,
      phase: rand() * Math.PI * 2,
      twinkle: 0.35 + rand() * 1.15,
      drift: 0.45 + rand() * 0.9,
      color,
      bright,
    })
  }
  stars.sort((a, b) => (a.color < b.color ? -1 : a.color > b.color ? 1 : 0))
  return stars
}

const STARS = createStars(STAR_COUNT)

export default function StarField({ animate }) {
  const ref = useRef(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d', { alpha: false })
    if (!ctx) return

    let raf = 0
    let running = false
    let last = performance.now()
    let time = 0

    const paint = (t) => {
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      if (w < 1 || h < 1) return
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const bw = Math.round(w * dpr)
      const bh = Math.round(h * dpr)
      if (canvas.width !== bw || canvas.height !== bh) {
        canvas.width = bw
        canvas.height = bh
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.fillStyle = '#05070f'
      ctx.fillRect(0, 0, w, h)

      let color = ''
      for (let i = 0; i < STARS.length; i++) {
        const star = STARS[i]
        const tw = animate ? 0.62 + 0.38 * Math.sin(t * star.twinkle + star.phase) : 1
        const y = ((star.y * h + (animate ? t * 6.5 * star.drift : 0)) % h + h) % h
        const x = ((star.x * w + (animate ? t * 1.4 * star.drift : 0)) % w + w) % w
        if (star.color !== color) {
          color = star.color
          ctx.fillStyle = color
        }
        if (star.bright) {
          ctx.globalAlpha = star.alpha * tw * 0.16
          ctx.beginPath()
          ctx.arc(x, y, star.r * 3.6, 0, Math.PI * 2)
          ctx.fill()
        }
        ctx.globalAlpha = star.alpha * tw
        ctx.beginPath()
        ctx.arc(x, y, star.r, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.globalAlpha = 1
    }

    const frame = (now) => {
      if (!running) return
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      time += dt
      paint(time)
      raf = requestAnimationFrame(frame)
    }

    const start = () => {
      if (!animate || document.hidden) {
        running = false
        paint(time)
        return
      }
      running = true
      last = performance.now()
      raf = requestAnimationFrame(frame)
    }

    const stop = () => {
      running = false
      cancelAnimationFrame(raf)
    }

    const onVisibility = () => {
      if (document.hidden) stop()
      else start()
    }

    const observer = new ResizeObserver(() => {
      if (!running) paint(time)
    })
    observer.observe(canvas)
    document.addEventListener('visibilitychange', onVisibility)
    start()

    return () => {
      stop()
      observer.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [animate])

  return <canvas ref={ref} className="starfield" aria-hidden="true" />
}
