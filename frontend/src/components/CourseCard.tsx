import type { Course } from '../api'
import { ClockIcon, PinIcon, UserIcon } from './Icons'

function clip(text: string, limit: number): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  return clean.length <= limit ? clean : `${clean.slice(0, limit - 1).trimEnd()}…`
}

type Props = {
  course: Course
  onOpen: (course: Course) => void
}

export default function CourseCard({ course, onOpen }: Props) {
  return (
    <article className="card">
      <div className="card__top">
        <span className="card__number">{course.number || '—'}</span>
        {course.category && <span className="tag">{course.category}</span>}
        {/* MGT 401 runs six near-identical sections; show which one this is. */}
        {course.section && <span className="tag">§{course.section}</span>}
        {course.units && <span className="tag tag--bell">{course.units} units</span>}
      </div>

      <h3 className="card__title">{course.title || 'Untitled course'}</h3>

      <div className="card__meta">
        {course.faculty && (
          <span>
            <UserIcon />
            {course.faculty}
          </span>
        )}
        {course.when && (
          <span>
            <ClockIcon />
            {course.when}
          </span>
        )}
        {course.room && (
          <span>
            <PinIcon />
            {course.room}
          </span>
        )}
      </div>

      {course.description && (
        <p className="card__desc">{clip(course.description, 165)}</p>
      )}

      <div className="card__footer">
        <button className="linkish" onClick={() => onOpen(course)}>
          Details →
        </button>
        {course.syllabus && (
          <a
            className="linkish"
            href={course.syllabus}
            target="_blank"
            rel="noreferrer"
          >
            Syllabus ↗
          </a>
        )}
      </div>
    </article>
  )
}
