/** Inline SVGs lifted from the Stitch export. No icon font dependency. */

type Props = { className?: string }

const stroke = {
  fill: 'none',
  stroke: 'currentColor',
  viewBox: '0 0 24 24',
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  strokeWidth: 2,
}

function S({ d, className = 'w-4 h-4' }: { d: string; className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap={stroke.strokeLinecap}
        strokeLinejoin={stroke.strokeLinejoin}
        strokeWidth={stroke.strokeWidth}
        d={d}
      />
    </svg>
  )
}

export const ArrowLeft = (p: Props) => <S {...p} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
export const ArrowRight = (p: Props) => <S {...p} d="M14 5l7 7m0 0l-7 7m7-7H3" />
export const ArrowSmallRight = (p: Props) => <S {...p} d="M13 7l5 5m0 0l-5 5m5-5H6" />
export const Check = (p: Props) => <S {...p} d="M5 13l4 4L19 7" />
export const Clock = (p: Props) => <S {...p} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
export const ChevronDown = (p: Props) => <S {...p} d="M19 9l-7 7-7-7" />
export const ChevronRight = (p: Props) => <S {...p} d="M9 5l7 7-7 7" />
export const Bolt = (p: Props) => <S {...p} d="M13 10V3L4 14h7v7l9-11h-7z" />
export const Lock = (p: Props) => (
  <S {...p} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
)
export const Pin = (p: Props) => (
  <svg className={p.className ?? 'w-4 h-4'} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
)
export const Link = (p: Props) => (
  <S
    {...p}
    d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
  />
)
export const Dots = (p: Props) => (
  <S {...p} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
)
export const Mail = (p: Props) => (
  <S {...p} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
)
// --- Queue screen (screen 1) ------------------------------------------------
export const Inbox = (p: Props) => (
  <S {...p} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
)
export const Ticket = (p: Props) => (
  <S {...p} d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" />
)
export const Groups = (p: Props) => (
  <S {...p} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
)
export const History = (p: Props) => (
  <S {...p} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
)
export const Terminal = (p: Props) => <S {...p} d="M8 9l3 3-3 3m5 0h3M4 19h16a1 1 0 001-1V6a1 1 0 00-1-1H4a1 1 0 00-1 1v12a1 1 0 001 1z" />
export const Person = (p: Props) => (
  <S {...p} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
)
export const PersonAdd = (p: Props) => (
  <S {...p} d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
)
export const Settings = (p: Props) => (
  <svg className={p.className ?? 'w-4 h-4'} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
)
export const Search = (p: Props) => <S {...p} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
export const Bell = (p: Props) => (
  <S {...p} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1h6z" />
)
export const Help = (p: Props) => (
  <S {...p} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
)
export const Tune = (p: Props) => <S {...p} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
export const Sync = (p: Props) => (
  <S {...p} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
)
export const Warning = (p: Props) => (
  <S {...p} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
)
export const TimerOff = (p: Props) => (
  <S {...p} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
)
export const Hourglass = (p: Props) => (
  <S {...p} d="M6 3h12M6 21h12M8 3v3.5a4 4 0 004 4 4 4 0 004-4V3M8 21v-3.5a4 4 0 014-4 4 4 0 014 4V21" />
)
export const Sparkles = (p: Props) => (
  <S {...p} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
)
export const Columns = (p: Props) => (
  <S {...p} d="M9 4v16m6-16v16M4 6a2 2 0 012-2h12a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6z" />
)
export const Fire = (p: Props) => (
  <S {...p} d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 4.5 16.5 6 17.657 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" />
)
export const Shield = (p: Props) => (
  <S {...p} d="M9 12l2 2 4-4M12 3l7 4v5c0 4.5-3 8.3-7 9-4-.7-7-4.5-7-9V7l7-4z" />
)
export const Robot = (p: Props) => (
  <S {...p} d="M9 3v2m6-2v2M5 7h14a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V9a2 2 0 012-2zm4 5h.01M15 12h.01M9 16h6" />
)
export const Plus = (p: Props) => <S {...p} d="M12 4v16m8-8H4" />
export const ChevronLeft = (p: Props) => <S {...p} d="M15 19l-7-7 7-7" />
export const Trash = (p: Props) => (
  <S {...p} d="M6 7h12M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2m-9 0l1 13a2 2 0 002 2h6a2 2 0 002-2l1-13M10 11v6m4-6v6" />
)

export const WhatsApp = ({ className = 'w-2 h-2' }: Props) => (
  <svg className={`${className} fill-current`} viewBox="0 0 24 24">
    <path d="M12.031 6.172c-3.181 0-5.767 2.586-5.768 5.766-.001 1.298.38 2.27 1.019 3.287l-.711 2.598 2.664-.698c.969.586 1.761.885 2.796.885 3.181 0 5.767-2.587 5.768-5.766 0-3.18-2.587-5.772-5.768-5.772zm3.393 8.243c-.144.405-.837.774-1.17.824-.312.045-.694.072-2.029-.481-1.616-.669-2.658-2.315-2.738-2.423-.081-.108-.654-.87-.654-1.657 0-.787.413-1.173.56-1.332.146-.159.32-.199.426-.199.106 0 .213.002.305.008.098.006.228-.037.357.273.132.319.452 1.104.492 1.185.04.081.066.177.013.283-.053.106-.08.172-.159.266-.08.093-.167.208-.239.28-.08.08-.163.167-.07.327.094.159.418.69 1 1.208.749.667 1.381.874 1.579.972.199.099.317.086.435-.05.118-.135.505-.589.638-.792.133-.203.266-.17.447-.102.181.068 1.147.541 1.345.64.199.099.332.148.38.232.048.084.048.487-.096.892z" />
  </svg>
)
