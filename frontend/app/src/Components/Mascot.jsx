import { useEffect, useState } from 'react'

// mood: 'idle' | 'thinking' | 'happy' | 'sad' | 'shocked'
export default function Mascot({ mood = 'idle', size = 72 }) {
  const [blink, setBlink] = useState(false)
  const [bobY, setBobY] = useState(0)

  useEffect(() => {
    const blinkInterval = setInterval(() => {
      setBlink(true)
      setTimeout(() => setBlink(false), 110)
    }, 2600)
    return () => clearInterval(blinkInterval)
  }, [])

  useEffect(() => {
    let t = 0
    const loop = setInterval(() => {
      t += 0.045
      setBobY(Math.sin(t) * 2.5)
    }, 30)
    return () => clearInterval(loop)
  }, [])

  const eyeRy = blink ? 0.6 : 7

  const antennaColor = mood === 'happy' ? '#22c55e' : mood === 'sad' ? '#ef4444' : mood === 'thinking' ? '#0ea5e9' : mood === 'shocked' ? '#a855f7' : '#2563eb'

  const mouthPath = mood === 'happy'
    ? 'M 42 76 Q 54 86 66 76'
    : mood === 'sad'
    ? 'M 42 82 Q 54 74 66 82'
    : mood === 'shocked'
    ? 'M 49 76 Q 54 84 59 76'
    : mood === 'thinking'
    ? 'M 44 79 Q 54 77 64 80'
    : 'M 44 78 Q 54 83 64 78'

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 108 120"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ display: 'block' }}
    >
      <g transform={`translate(0, ${bobY})`}>

        {/* Antenna */}
        <line x1="54" y1="16" x2="54" y2="6" stroke="#c7cbe8" strokeWidth="3" strokeLinecap="round" />
        <circle cx="54" cy="5" r="4.5" fill={antennaColor}>
          <animate attributeName="opacity" values="1;0.4;1" dur="1.4s" repeatCount="indefinite" />
        </circle>

        {/* Round chubby head/body as one blob */}
        <ellipse cx="54" cy="62" rx="42" ry="40" fill="#60a5fa" />
        <ellipse cx="54" cy="64" rx="34" ry="32" fill="#eaf3ff" />

        {/* Cheeks */}
        <circle cx="26" cy="68" r="6" fill="#93c5fd" opacity="0.6" />
        <circle cx="82" cy="68" r="6" fill="#93c5fd" opacity="0.6" />

        {/* Ear bobbles */}
        <circle cx="14" cy="58" r="6" fill="#60a5fa" />
        <circle cx="94" cy="58" r="6" fill="#60a5fa" />

        {/* Eyes */}
        <ellipse cx="40" cy="60" rx="8" ry={eyeRy} fill="#1e3a8a" />
        <ellipse cx="68" cy="60" rx="8" ry={eyeRy} fill="#1e3a8a" />
        {!blink && (
          <>
            <circle cx="43" cy="57" r="2" fill="white" />
            <circle cx="71" cy="57" r="2" fill="white" />
          </>
        )}

        {/* Mouth */}
        <path d={mouthPath} stroke="#1e3a8a" strokeWidth="2.5" strokeLinecap="round" fill="none" />

        {/* Tiny feet peeking out */}
        <ellipse cx="38" cy="100" rx="9" ry="6" fill="#2563eb" />
        <ellipse cx="70" cy="100" rx="9" ry="6" fill="#2563eb" />
      </g>
    </svg>
  )
}
