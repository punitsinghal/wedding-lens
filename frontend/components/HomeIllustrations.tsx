// Flat-style vector illustrations for the marketing homepage's placeholder
// tiles — no external image assets, colored entirely from the app's
// existing accent/accent-2/neutral CSS custom properties.

type Variant =
  | 'mandap'
  | 'sangeet'
  | 'reception'
  | 'corporate'
  | 'mehendi'
  | 'baraat'
  | 'photobooth'
  | 'fireworks'
  | 'conference'
  | 'garland';

function Backdrop({ id, from, to }: { id: string; from: string; to: string }) {
  return (
    <>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={from} />
          <stop offset="1" stopColor={to} />
        </linearGradient>
      </defs>
      <rect width="240" height="180" fill={`url(#${id})`} />
    </>
  );
}

function Person({
  x,
  y,
  scale = 1,
  mirror = false,
  color,
  armUp = false,
  holdingGlass = false,
}: {
  x: number;
  y: number;
  scale?: number;
  mirror?: boolean;
  color: string;
  armUp?: boolean;
  holdingGlass?: boolean;
}) {
  const sx = mirror ? -scale : scale;
  return (
    <g transform={`translate(${x} ${y}) scale(${sx} ${scale})`}>
      <circle cx="0" cy="-32" r="7" fill={color} />
      <path d="M-9 -24 Q0 -29 9 -24 L12 8 Q0 13 -12 8 Z" fill={color} />
      {armUp && (
        <path d="M7 -20 Q16 -28 15 -38" stroke={color} strokeWidth="4" strokeLinecap="round" fill="none" />
      )}
      {holdingGlass && (
        <>
          <path d="M7 -20 Q14 -24 14 -32" stroke={color} strokeWidth="4" strokeLinecap="round" fill="none" />
          <path d="M10 -40 L18 -40 L14 -34 Z" fill={color} />
          <line x1="14" y1="-34" x2="14" y2="-32" stroke={color} strokeWidth="2" />
        </>
      )}
    </g>
  );
}

function Flower({
  cx,
  cy,
  r = 9,
  petalR = 3,
  petalColor,
  centerColor,
}: {
  cx: number;
  cy: number;
  r?: number;
  petalR?: number;
  petalColor: string;
  centerColor: string;
}) {
  const petals = Array.from({ length: 5 }, (_, i) => {
    const angle = (i / 5) * Math.PI * 2 - Math.PI / 2;
    return { px: cx + r * Math.cos(angle), py: cy + r * Math.sin(angle) };
  });
  return (
    <g>
      {petals.map((p, i) => (
        <circle key={i} cx={p.px} cy={p.py} r={petalR} fill={petalColor} />
      ))}
      <circle cx={cx} cy={cy} r={petalR * 0.9} fill={centerColor} />
    </g>
  );
}

function Hand({ x, mirror = false, color }: { x: number; mirror?: boolean; color: string }) {
  const sx = mirror ? -1 : 1;
  return (
    <g transform={`translate(${x} 95) scale(${sx} 1)`}>
      <rect x="-14" y="0" width="28" height="34" rx="14" fill={color} />
      {[-9, -3, 3, 9].map((fx, i) => (
        <rect key={i} x={fx - 2.5} y={-24 + (i % 2) * 3} width="5" height="24" rx="2.5" fill={color} />
      ))}
    </g>
  );
}

function Firework({ cx, cy, size = 20, color }: { cx: number; cy: number; size?: number; color: string }) {
  const spokes = Array.from({ length: 10 }, (_, i) => (i / 10) * Math.PI * 2);
  return (
    <g>
      {spokes.map((angle, i) => (
        <line
          key={i}
          x1={cx}
          y1={cy}
          x2={cx + size * Math.cos(angle)}
          y2={cy + size * Math.sin(angle)}
          stroke={color}
          strokeWidth="1.6"
          strokeLinecap="round"
          opacity={0.85}
        />
      ))}
      <circle cx={cx} cy={cy} r={2.5} fill={color} />
    </g>
  );
}

function SceneMandap() {
  const garland: [number, number][] = [
    [80, 46],
    [96, 33],
    [112, 26],
    [128, 24],
    [144, 28],
    [158, 38],
    [164, 48],
  ];
  return (
    <>
      <Backdrop id="g-mandap" from="var(--color-accent-100)" to="var(--color-accent-2-100)" />
      <rect x="72" y="50" width="7" height="100" rx="3" fill="var(--color-accent-2-700)" />
      <rect x="161" y="50" width="7" height="100" rx="3" fill="var(--color-accent-2-700)" />
      <path d="M72 52 Q120 14 168 52" stroke="var(--color-accent-2-700)" strokeWidth="7" fill="none" strokeLinecap="round" />
      {garland.map(([cx, cy], i) => (
        <circle key={i} cx={cx} cy={cy} r={3.2} fill={i % 2 === 0 ? 'var(--color-accent-500)' : 'var(--color-accent-2-500)'} />
      ))}
      <Person x={112} y={150} scale={1.05} color="var(--color-accent-900)" mirror />
      <Person x={132} y={150} scale={1.05} color="var(--color-accent-2-900)" />
      <Flower cx={60} cy={162} r={7} petalR={2.6} petalColor="var(--color-accent-2-400)" centerColor="var(--color-accent-700)" />
      <Flower cx={186} cy={158} r={7} petalR={2.6} petalColor="var(--color-accent-400)" centerColor="var(--color-accent-2-700)" />
    </>
  );
}

function SceneSangeet() {
  const lights: [number, number][] = Array.from({ length: 8 }, (_, i) => [
    10 + i * 31,
    24 + Math.sin(i * 1.1) * 8,
  ]);
  const path = `M0 20 ${lights.map(([x, y]) => `Q${x - 15} ${y - 10} ${x} ${y}`).join(' ')}`;
  return (
    <>
      <Backdrop id="g-sangeet" from="var(--color-accent-2-100)" to="var(--color-accent-100)" />
      <path d={path} stroke="var(--color-accent-2-600)" strokeWidth="1.5" fill="none" opacity={0.6} />
      {lights.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={2.6} fill={i % 2 === 0 ? 'var(--color-accent-500)' : 'var(--color-accent-2-500)'} />
      ))}
      <Person x={70} y={165} scale={0.95} color="var(--color-accent-800)" armUp />
      <Person x={120} y={172} scale={1.1} color="var(--color-accent-2-800)" armUp mirror />
      <Person x={168} y={162} scale={0.9} color="var(--color-accent-800)" armUp />
    </>
  );
}

function SceneReception() {
  const bokeh: [number, number, number][] = [
    [30, 30, 14],
    [200, 24, 18],
    [50, 100, 8],
    [190, 110, 10],
    [20, 140, 6],
    [215, 150, 7],
  ];
  const sparkles: [number, number][] = [
    [120, 106],
    [130, 100],
    [112, 98],
  ];
  return (
    <>
      <Backdrop id="g-reception" from="var(--color-accent-2-200)" to="var(--color-accent-100)" />
      {bokeh.map(([cx, cy, r], i) => (
        <circle key={i} cx={cx} cy={cy} r={r} fill="var(--color-accent-2-500)" opacity={0.18} />
      ))}
      <Person x={104} y={158} scale={1.05} color="var(--color-accent-900)" holdingGlass mirror />
      <Person x={136} y={158} scale={1.05} color="var(--color-accent-2-900)" holdingGlass />
      {sparkles.map(([x, y], i) => (
        <g key={i} stroke="var(--color-accent-500)" strokeWidth="1.4" strokeLinecap="round">
          <line x1={x - 3.5} y1={y} x2={x + 3.5} y2={y} />
          <line x1={x} y1={y - 3.5} x2={x} y2={y + 3.5} />
        </g>
      ))}
    </>
  );
}

function SceneCorporate() {
  const buildings = [
    { x: 10, w: 22, h: 70 },
    { x: 36, w: 16, h: 100 },
    { x: 56, w: 26, h: 60 },
    { x: 86, w: 18, h: 120 },
    { x: 108, w: 22, h: 85 },
    { x: 134, w: 16, h: 105 },
    { x: 154, w: 28, h: 65 },
    { x: 186, w: 18, h: 95 },
    { x: 208, w: 22, h: 75 },
  ];
  const confetti: [number, number][] = [
    [40, 30],
    [90, 15],
    [150, 25],
    [190, 40],
    [70, 50],
    [130, 45],
  ];
  return (
    <>
      <Backdrop id="g-corporate" from="var(--color-neutral-800)" to="var(--color-neutral-900)" />
      {buildings.map((b, i) => (
        <rect key={i} x={b.x} y={180 - b.h} width={b.w} height={b.h} fill="var(--color-neutral-700)" />
      ))}
      {buildings.flatMap((b, bi) =>
        Array.from({ length: 3 }, (_, wi) => (
          <rect
            key={`${bi}-${wi}`}
            x={b.x + 4 + (wi % 2) * 8}
            y={180 - b.h + 10 + wi * 16}
            width="4"
            height="6"
            fill="var(--color-accent-300)"
            opacity={0.7}
          />
        )),
      )}
      {confetti.map(([x, y], i) => (
        <rect
          key={i}
          x={x}
          y={y}
          width="5"
          height="5"
          fill={i % 2 === 0 ? 'var(--color-accent-400)' : 'var(--color-accent-2-400)'}
          transform={`rotate(${i * 37} ${x} ${y})`}
        />
      ))}
    </>
  );
}

function SceneMehendi() {
  const dots: [number, number][] = [
    [70, 80],
    [70, 65],
    [85, 90],
    [55, 90],
    [170, 80],
    [170, 65],
    [155, 90],
    [185, 90],
  ];
  return (
    <>
      <Backdrop id="g-mehendi" from="var(--color-accent-100)" to="var(--color-accent-2-100)" />
      <Hand x={70} color="var(--color-accent-800)" />
      <Hand x={170} mirror color="var(--color-accent-2-800)" />
      {dots.map(([cx, cy], i) => (
        <circle key={i} r={1.6} cx={cx} cy={cy} fill="var(--color-accent-2-700)" opacity={0.7} />
      ))}
      <path d="M60 100 Q70 92 80 100 Q70 108 60 100 Z" stroke="var(--color-accent-2-700)" strokeWidth="1" fill="none" opacity={0.6} />
      <path d="M160 100 Q170 92 180 100 Q170 108 160 100 Z" stroke="var(--color-accent-2-700)" strokeWidth="1" fill="none" opacity={0.6} />
    </>
  );
}

function SceneBaraat() {
  const confetti: [number, number][] = [
    [40, 60],
    [190, 50],
    [60, 40],
    [170, 90],
    [30, 110],
    [200, 120],
  ];
  return (
    <>
      <Backdrop id="g-baraat" from="var(--color-accent-2-100)" to="var(--color-accent-100)" />
      <Person x={115} y={155} scale={1.15} color="var(--color-accent-2-900)" />
      <ellipse cx="115" cy="128" rx="20" ry="14" fill="var(--color-accent-700)" />
      <ellipse cx="115" cy="128" rx="20" ry="14" fill="none" stroke="var(--color-accent-900)" strokeWidth="1.5" opacity={0.5} />
      <line x1="98" y1="128" x2="132" y2="128" stroke="var(--color-accent-900)" strokeWidth="1" opacity={0.4} />
      <line x1="100" y1="120" x2="130" y2="120" stroke="var(--color-accent-900)" strokeWidth="1" opacity={0.3} />
      <line x1="100" y1="136" x2="130" y2="136" stroke="var(--color-accent-900)" strokeWidth="1" opacity={0.3} />
      <line x1="98" y1="118" x2="86" y2="106" stroke="var(--color-accent-900)" strokeWidth="3" strokeLinecap="round" />
      <line x1="132" y1="118" x2="144" y2="106" stroke="var(--color-accent-900)" strokeWidth="3" strokeLinecap="round" />
      {confetti.map(([cx, cy], i) => (
        <circle key={i} cx={cx} cy={cy} r={3} fill={i % 2 === 0 ? 'var(--color-accent-500)' : 'var(--color-accent-2-500)'} />
      ))}
    </>
  );
}

function ScenePhotobooth() {
  const flashSpokes = Array.from({ length: 10 }, (_, i) => (i / 10) * Math.PI * 2);
  return (
    <>
      <Backdrop id="g-photobooth" from="var(--color-neutral-200)" to="var(--color-accent-100)" />
      <rect x="86" y="70" width="68" height="46" rx="10" fill="var(--color-accent-900)" />
      <rect x="86" y="60" width="20" height="14" rx="4" fill="var(--color-accent-900)" />
      <circle cx="120" cy="93" r="16" fill="var(--color-neutral-100)" />
      <circle cx="120" cy="93" r="10" fill="var(--color-accent-700)" />
      <circle cx="120" cy="93" r="4" fill="var(--color-neutral-900)" />
      {flashSpokes.map((angle, i) => (
        <line
          key={i}
          x1={120 + 22 * Math.cos(angle)}
          y1={93 + 22 * Math.sin(angle)}
          x2={120 + 32 * Math.cos(angle)}
          y2={93 + 32 * Math.sin(angle)}
          stroke="var(--color-accent-400)"
          strokeWidth="2"
          strokeLinecap="round"
        />
      ))}
      <g transform="translate(30 55)">
        <rect width="26" height="70" rx="4" fill="var(--color-neutral-100)" stroke="var(--color-neutral-400)" strokeWidth="1" />
        <rect x="4" y="6" width="18" height="16" rx="2" fill="var(--color-accent-100)" />
        <rect x="4" y="26" width="18" height="16" rx="2" fill="var(--color-accent-2-100)" />
        <rect x="4" y="46" width="18" height="16" rx="2" fill="var(--color-accent-100)" />
      </g>
      <g transform="translate(184 58) rotate(6)">
        <rect width="26" height="70" rx="4" fill="var(--color-neutral-100)" stroke="var(--color-neutral-400)" strokeWidth="1" />
        <rect x="4" y="6" width="18" height="16" rx="2" fill="var(--color-accent-2-100)" />
        <rect x="4" y="26" width="18" height="16" rx="2" fill="var(--color-accent-100)" />
        <rect x="4" y="46" width="18" height="16" rx="2" fill="var(--color-accent-2-100)" />
      </g>
    </>
  );
}

function SceneFireworks() {
  const stars: [number, number][] = [
    [20, 20],
    [50, 10],
    [90, 25],
    [130, 8],
    [170, 20],
    [210, 30],
    [30, 45],
    [200, 55],
  ];
  const buildings = [10, 40, 65, 95, 120, 150, 180, 205];
  return (
    <>
      <Backdrop id="g-fireworks" from="var(--color-neutral-900)" to="var(--color-accent-900)" />
      {stars.map(([cx, cy], i) => (
        <circle key={i} cx={cx} cy={cy} r={1.2} fill="var(--color-neutral-100)" opacity={0.7} />
      ))}
      <Firework cx={70} cy={55} size={22} color="var(--color-accent-400)" />
      <Firework cx={165} cy={40} size={18} color="var(--color-accent-2-400)" />
      <Firework cx={125} cy={75} size={14} color="var(--color-neutral-100)" />
      <rect x="0" y="150" width="240" height="30" fill="var(--color-neutral-800)" />
      {buildings.map((x, i) => (
        <rect key={i} x={x} y={150 - ((i % 3) * 8 + 10)} width="18" height={(i % 3) * 8 + 30} fill="var(--color-neutral-700)" />
      ))}
    </>
  );
}

function SceneConference() {
  const bars = [40, 65, 50, 80, 35];
  return (
    <>
      <Backdrop id="g-conference" from="var(--color-neutral-100)" to="var(--color-neutral-200)" />
      <rect x="60" y="30" width="120" height="76" rx="4" fill="var(--color-neutral-800)" />
      <rect x="66" y="36" width="108" height="64" rx="2" fill="var(--color-neutral-100)" />
      {bars.map((h, i) => (
        <rect
          key={i}
          x={78 + i * 20}
          y={94 - h}
          width="12"
          height={h}
          fill={i % 2 === 0 ? 'var(--color-accent-500)' : 'var(--color-accent-2-500)'}
        />
      ))}
      <rect x="110" y="106" width="20" height="30" fill="var(--color-accent-900)" />
      <Person x={140} y={136} scale={0.9} color="var(--color-accent-800)" />
      {Array.from({ length: 9 }, (_, i) => (
        <circle key={i} cx={20 + i * 25} cy={168} r={3.2} fill="var(--color-neutral-600)" />
      ))}
    </>
  );
}

function SceneGarland() {
  const spots: [number, number][] = [
    [30, 150],
    [60, 118],
    [92, 90],
    [128, 66],
    [165, 46],
    [200, 28],
  ];
  const path = `M10 170 Q${spots[0].join(' ')} ${spots[1].join(' ')} Q${spots[2].join(' ')} ${spots[3].join(' ')} Q${spots[4].join(' ')} ${spots[5].join(' ')}`;
  return (
    <>
      <Backdrop id="g-garland" from="var(--color-accent-2-100)" to="var(--color-accent-100)" />
      <path d={path} stroke="var(--color-accent-2-600)" strokeWidth="2" fill="none" opacity={0.4} />
      {spots.map(([cx, cy], i) => (
        <Flower
          key={i}
          cx={cx}
          cy={cy}
          r={9 - (i % 2)}
          petalR={3}
          petalColor={i % 2 === 0 ? 'var(--color-accent-400)' : 'var(--color-accent-2-400)'}
          centerColor="var(--color-accent-800)"
        />
      ))}
    </>
  );
}

const SCENES: Record<Variant, () => JSX.Element> = {
  mandap: SceneMandap,
  sangeet: SceneSangeet,
  reception: SceneReception,
  corporate: SceneCorporate,
  mehendi: SceneMehendi,
  baraat: SceneBaraat,
  photobooth: ScenePhotobooth,
  fireworks: SceneFireworks,
  conference: SceneConference,
  garland: SceneGarland,
};

export function IllustrationTile({ variant, className = '' }: { variant: Variant; className?: string }) {
  const Scene = SCENES[variant];
  return (
    <div className={`relative overflow-hidden ${className}`}>
      <svg viewBox="0 0 240 180" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 w-full h-full" aria-hidden="true">
        <Scene />
      </svg>
    </div>
  );
}
