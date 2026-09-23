/**
 * Client for the FastAPI backend.
 *
 * Courses now come from the `courses` table, so `GET /api/courses` returns tidy
 * snake_case keys rather than the JSON file's spaced title-case ones. Every row
 * carries the table's primary key, which finally gives the list a real React key.
 *
 * Everything except health and the two auth routes needs `Authorization: Bearer
 * <token>`; the token lives in localStorage so a refresh doesn't sign you out.
 */

export const API_BASE =
  import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

const TOKEN_KEY = 'som.token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

/** Thrown for any non-2xx response, carrying the status so callers can branch. */
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

/** A 401 means the stored token is gone or expired — callers sign the user out. */
export const isAuthError = (err: unknown): boolean =>
  err instanceof ApiError && err.status === 401

/** Interface of `RawCourse` as the API now returns it. */
export interface RawCourse {
  row_id: number
  course_id: string
  number: string
  title: string
  section: string
  category: string
  course_type: string
  description: string
  units: string
  faculty: string
  faculty_email: string
  faculty_bio: string
  daytimes: string
  room: string
  session: string
  syllabus: string
}

export interface Course {
  key: string
  id: string
  number: string
  title: string
  category: string
  description: string
  section: string
  units: string
  when: string
  room: string
  faculty: string
  facultyEmail: string
  facultyBio: string
  session: string
  syllabus: string
}

export interface ChatReply {
  reply: string
  tools_used: string[]
}

export interface StoredMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  tools_used: string[]
  created_at: string
}

/**
 * The backend already strips whitespace, but a few rows still arrive as null when
 * a column was never populated, so coalesce here too.
 */
const s = (value: string | undefined | null): string => (value ?? '').trim()

export function normalise(row: RawCourse): Course {
  return {
    // The table's primary key — unique per row, unlike Course ID which repeats
    // across sections.
    key: String(row.row_id),
    id: s(row.course_id),
    number: s(row.number),
    title: s(row.title),
    category: s(row.category),
    description: s(row.description),
    section: s(row.section),
    units: s(row.units),
    when: s(row.daytimes),
    room: s(row.room),
    faculty: s(row.faculty),
    facultyEmail: s(row.faculty_email),
    facultyBio: s(row.faculty_bio),
    session: s(row.session),
    syllabus: s(row.syllabus),
  }
}

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    // FastAPI puts the human-readable reason in `detail`; validation errors make
    // it a list of objects, so fall back to the status text.
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') message = body.detail
      else if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
        message = String(body.detail[0].msg).replace(/^Value error, /, '')
      }
    } catch {
      /* non-JSON body — keep the status line */
    }
    throw new ApiError(res.status, message)
  }
  return (await res.json()) as T
}

function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ------------------------------------------------------------------ auth

export interface AuthResult {
  token: string
  username: string
}

async function credentials(
  path: 'login' | 'signup',
  username: string,
  password: string,
): Promise<AuthResult> {
  const res = await fetch(new URL(`/api/auth/${path}`, API_BASE), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const data = await asJson<AuthResult>(res)
  setToken(data.token)
  return data
}

export const login = (u: string, p: string) => credentials('login', u, p)
export const signup = (u: string, p: string) => credentials('signup', u, p)

export function logout(): void {
  setToken(null)
}

/** Resolve the stored token to a username, or null if it is missing/expired. */
export async function fetchMe(signal?: AbortSignal): Promise<string | null> {
  if (!getToken()) return null
  try {
    const res = await fetch(new URL('/api/auth/me', API_BASE), {
      headers: authHeaders(),
      signal,
    })
    if (!res.ok) {
      if (res.status === 401) setToken(null)
      return null
    }
    const data = (await res.json()) as { username: string }
    return data.username
  } catch {
    // Network failure — keep the token so a flaky connection isn't a sign-out.
    return null
  }
}

// --------------------------------------------------------------- courses

export async function fetchCourses(
  query?: string,
  signal?: AbortSignal,
): Promise<Course[]> {
  const url = new URL('/api/courses', API_BASE)
  if (query) url.searchParams.set('q', query)
  const data = await asJson<{ count: number; courses: RawCourse[] }>(
    await fetch(url, { headers: authHeaders(), signal }),
  )
  return data.courses.map(normalise)
}

// ------------------------------------------------------------------ chat

export async function sendChat(
  message: string,
  signal?: AbortSignal,
): Promise<ChatReply> {
  const res = await fetch(new URL('/api/chat', API_BASE), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ message }),
    signal,
  })
  return asJson<ChatReply>(res)
}

export async function fetchHistory(
  signal?: AbortSignal,
): Promise<StoredMessage[]> {
  const res = await fetch(new URL('/api/chat/history', API_BASE), {
    headers: authHeaders(),
    signal,
  })
  return asJson<StoredMessage[]>(res)
}

export async function clearHistory(): Promise<void> {
  const res = await fetch(new URL('/api/chat/history', API_BASE), {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`)
}

export async function fetchHealth(signal?: AbortSignal): Promise<boolean> {
  try {
    const res = await fetch(new URL('/api/health', API_BASE), { signal })
    return res.ok
  } catch {
    return false
  }
}
