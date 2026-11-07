// Minimal EXIF reader for the confirm screen: only the time the photo was taken.
// Person C. The backend (Person A) reads EXIF again server-side and strips it before storing;
// this copy only pre-fills the time so the user can check it before uploading.
// JPEG only (PNG rarely carries EXIF). Returns null when nothing usable is found.

const TAG_EXIF_IFD = 0x8769
const TAG_DATETIME = 0x0132 // IFD0, "last modified": fallback only
const TAG_DATETIME_ORIGINAL = 0x9003
const TAG_OFFSET_TIME_ORIGINAL = 0x9011 // e.g. "-05:00"; many phones write it, some don't

export async function readExifTime(file) {
  try {
    const buf = await file.slice(0, 256 * 1024).arrayBuffer()
    const view = new DataView(buf)
    if (view.byteLength < 4 || view.getUint16(0) !== 0xffd8) return null // not a JPEG
    let off = 2
    while (off + 10 < view.byteLength) {
      const marker = view.getUint16(off)
      if ((marker & 0xff00) !== 0xff00) break
      const len = view.getUint16(off + 2)
      // APP1 segment starting with "Exif\0\0"
      if (marker === 0xffe1 && view.getUint32(off + 4) === 0x45786966) {
        return parseTiff(view, off + 10)
      }
      off += 2 + len
    }
  } catch {
    // Corrupt or truncated EXIF: treat as "no time found".
  }
  return null
}

function parseTiff(view, start) {
  const little = view.getUint16(start) === 0x4949 // "II" = little-endian
  const u16 = (o) => view.getUint16(start + o, little)
  const u32 = (o) => view.getUint32(start + o, little)

  // Returns { tag: entryOffset } for one IFD; offsets are relative to the TIFF header.
  const readIfd = (ifdOff) => {
    const entries = {}
    const count = u16(ifdOff)
    for (let i = 0; i < count; i++) {
      const e = ifdOff + 2 + i * 12
      entries[u16(e)] = e
    }
    return entries
  }
  const readAscii = (e) => {
    const count = u32(e + 4)
    const valueOff = count > 4 ? u32(e + 8) : e + 8
    let s = ''
    for (let i = 0; i < count; i++) {
      const c = view.getUint8(start + valueOff + i)
      if (c === 0) break
      s += String.fromCharCode(c)
    }
    return s.trim()
  }

  const ifd0 = readIfd(u32(4))
  let original = null
  let offset = null
  if (ifd0[TAG_EXIF_IFD] !== undefined) {
    const exif = readIfd(u32(ifd0[TAG_EXIF_IFD] + 8))
    if (exif[TAG_DATETIME_ORIGINAL] !== undefined) original = readAscii(exif[TAG_DATETIME_ORIGINAL])
    if (exif[TAG_OFFSET_TIME_ORIGINAL] !== undefined) offset = readAscii(exif[TAG_OFFSET_TIME_ORIGINAL])
  }
  if (!original && ifd0[TAG_DATETIME] !== undefined) original = readAscii(ifd0[TAG_DATETIME])
  if (!original) return null
  const date = exifToDate(original, offset)
  return date ? { date, hadOffset: Boolean(offset && /^[+-]\d\d:\d\d$/.test(offset)) } : null
}

// EXIF format: "YYYY:MM:DD HH:MM:SS". With an offset we know the exact instant.
// Without one, assume the photo was taken in the device's current time zone; the Date
// constructor applies the right DST rule for that date (DST ended Nov 1, 2026).
function exifToDate(text, offset) {
  const m = /^(\d{4}):(\d\d):(\d\d) (\d\d):(\d\d):(\d\d)/.exec(text)
  if (!m) return null
  const [, y, mo, d, h, mi, s] = m
  const date =
    offset && /^[+-]\d\d:\d\d$/.test(offset)
      ? new Date(`${y}-${mo}-${d}T${h}:${mi}:${s}${offset}`)
      : new Date(+y, +mo - 1, +d, +h, +mi, +s)
  return Number.isNaN(date.getTime()) ? null : date
}
