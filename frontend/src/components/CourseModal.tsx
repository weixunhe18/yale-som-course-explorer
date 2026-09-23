import { useEffect } from 'react'
import type { Course } from '../api'

type Props = {
  course: Course
  onClose: () => void
}

export default function CourseModal({ course, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal__wrap" onClick={(e) => e.stopPropagation()}>
        <button className="modal__close" onClick={onClose} aria-label="Close">
          ×
        </button>
        <div className="modal" role="dialog" aria-modal="true" aria-label={course.title}>
          <div className="card__top">
            <span className="card__number">{course.number}</span>
            {course.category && <span className="tag">{course.category}</span>}
            {course.section && <span className="tag">Section {course.section}</span>}
            {course.units && <span className="tag tag--bell">{course.units} units</span>}
          </div>

          <h3>{course.title}</h3>

          <div className="card__meta">
            {course.faculty && (
              <span>
                <strong>Instructor:</strong>&nbsp;{course.faculty}
                {course.facultyEmail && (
                  <>
                    &nbsp;·&nbsp;
                    <a href={`mailto:${course.facultyEmail}`}>{course.facultyEmail}</a>
                  </>
                )}
              </span>
            )}
            {course.when && (
              <span>
                <strong>Meets:</strong>&nbsp;{course.when}
              </span>
            )}
            {course.room && (
              <span>
                <strong>Room:</strong>&nbsp;{course.room}
              </span>
            )}
            {course.session && (
              <span>
                <strong>Session:</strong>&nbsp;{course.session}
              </span>
            )}
          </div>

          {course.description && (
            <>
              <span className="modal__section-label">Description</span>
              <p>{course.description}</p>
            </>
          )}

          {course.facultyBio && (
            <>
              <span className="modal__section-label">About the instructor</span>
              <p>{course.facultyBio}</p>
            </>
          )}

          {course.syllabus && (
            <p>
              <a href={course.syllabus} target="_blank" rel="noreferrer">
                Open syllabus ↗
              </a>
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
