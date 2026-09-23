/** Small inline icons, so the app ships with no icon dependency. */

type P = { size?: number }

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
})

export const SearchIcon = ({ size = 18 }: P) => (
  <svg {...base(size)} aria-hidden="true">
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.2-3.2" />
  </svg>
)

export const ClockIcon = ({ size = 15 }: P) => (
  <svg {...base(size)} aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
)

export const PinIcon = ({ size = 15 }: P) => (
  <svg {...base(size)} aria-hidden="true">
    <path d="M20 10c0 5.5-8 12-8 12s-8-6.5-8-12a8 8 0 1 1 16 0Z" />
    <circle cx="12" cy="10" r="2.6" />
  </svg>
)

export const UserIcon = ({ size = 15 }: P) => (
  <svg {...base(size)} aria-hidden="true">
    <circle cx="12" cy="8" r="3.6" />
    <path d="M5 20a7 7 0 0 1 14 0" />
  </svg>
)

export const SendIcon = ({ size = 18 }: P) => (
  <svg {...base(size)} aria-hidden="true">
    <path d="M4.5 12h14" />
    <path d="m12.5 5.5 6.5 6.5-6.5 6.5" />
  </svg>
)

export const SparkIcon = ({ size = 18 }: P) => (
  <svg {...base(size)} aria-hidden="true">
    <path d="M12 3.5 13.7 9l5.5 1.7-5.5 1.7L12 18l-1.7-5.6L4.8 10.7 10.3 9 12 3.5Z" />
  </svg>
)

export const BookIcon = ({ size = 14 }: P) => (
  <svg {...base(size)} aria-hidden="true">
    <path d="M5 4.5h9a3 3 0 0 1 3 3v12a2.4 2.4 0 0 0-2.4-2.4H5Z" />
    <path d="M5 4.5v12.6" />
  </svg>
)

export const GlobeIcon = ({ size = 14 }: P) => (
  <svg {...base(size)} aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18Z" />
  </svg>
)
