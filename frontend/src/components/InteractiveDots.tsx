import { useCallback, useEffect, useRef } from "react";

interface InteractiveDotsProps {
  backgroundColor?: string;
  dotColor?: string;
  gridSpacing?: number;
  animationSpeed?: number;
  removeWaveLine?: boolean;
}

interface Dot {
  x: number;
  y: number;
  originalX: number;
  originalY: number;
  phase: number;
}

interface Ripple {
  x: number;
  y: number;
  time: number;
  intensity: number;
}

function rgbFromHex(color: string): [number, number, number] {
  const match = /^#([0-9a-f]{6})$/i.exec(color);
  if (!match) return [102, 102, 102];
  return [
    Number.parseInt(match[1].slice(0, 2), 16),
    Number.parseInt(match[1].slice(2, 4), 16),
    Number.parseInt(match[1].slice(4, 6), 16),
  ];
}

export function InteractiveDots({
  backgroundColor = "#F0EEE6",
  dotColor = "#666666",
  gridSpacing = 30,
  animationSpeed = 0.005,
  removeWaveLine = true,
}: InteractiveDotsProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const timeRef = useRef(0);
  const animationFrameId = useRef<number | null>(null);
  const mouseRef = useRef({ x: -1000, y: -1000 });
  const ripples = useRef<Ripple[]>([]);
  const dotsRef = useRef<Dot[]>([]);
  const reducedMotionRef = useRef(false);

  const initializeDots = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dots: Dot[] = [];
    for (let x = gridSpacing / 2; x < canvas.clientWidth; x += gridSpacing) {
      for (let y = gridSpacing / 2; y < canvas.clientHeight; y += gridSpacing) {
        dots.push({
          x,
          y,
          originalX: x,
          originalY: y,
          phase: Math.random() * Math.PI * 2,
        });
      }
    }
    dotsRef.current = dots;
  }, [gridSpacing]);

  const resizeCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const width = window.innerWidth;
    const height = window.innerHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    const context = canvas.getContext("2d");
    context?.setTransform(dpr, 0, 0, dpr, 0, 0);
    initializeDots();
  }, [initializeDots]);

  const animate = useCallback(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    if (!reducedMotionRef.current) timeRef.current += animationSpeed;
    const currentTime = Date.now();
    const [red, green, blue] = rgbFromHex(dotColor);
    const maxRippleAge = 3000;
    ripples.current = ripples.current.filter(
      (ripple) => currentTime - ripple.time < maxRippleAge,
    );

    context.fillStyle = backgroundColor;
    context.fillRect(0, 0, canvas.clientWidth, canvas.clientHeight);

    dotsRef.current.forEach((dot) => {
      let mouseInfluence = 0;
      let rippleInfluence = 0;
      if (!reducedMotionRef.current) {
        const mouseDistance = Math.hypot(
          dot.originalX - mouseRef.current.x,
          dot.originalY - mouseRef.current.y,
        );
        mouseInfluence = Math.max(0, 1 - mouseDistance / 150);

        ripples.current.forEach((ripple) => {
          const age = currentTime - ripple.time;
          const distance = Math.hypot(dot.originalX - ripple.x, dot.originalY - ripple.y);
          const rippleRadius = (age / maxRippleAge) * 300;
          const rippleWidth = 60;
          if (Math.abs(distance - rippleRadius) < rippleWidth) {
            rippleInfluence +=
              (1 - age / maxRippleAge) *
              ripple.intensity *
              (1 - Math.abs(distance - rippleRadius) / rippleWidth);
          }
        });
      }

      const influence = Math.min(mouseInfluence + rippleInfluence, 2);
      dot.x = dot.originalX;
      dot.y = dot.originalY;
      const pulse = reducedMotionRef.current
        ? 0
        : Math.sin(timeRef.current + dot.phase) * 0.35;
      const size = Math.max(0.8, 1.25 + influence * 4.5 + pulse);
      const opacity = Math.min(0.5, 0.18 + influence * 0.24);

      context.beginPath();
      context.arc(dot.x, dot.y, size, 0, Math.PI * 2);
      context.fillStyle = `rgba(${red}, ${green}, ${blue}, ${opacity})`;
      context.fill();
    });

    if (!removeWaveLine && !reducedMotionRef.current) {
      ripples.current.forEach((ripple) => {
        const age = currentTime - ripple.time;
        const progress = age / maxRippleAge;
        const alpha = (1 - progress) * 0.18 * ripple.intensity;
        context.beginPath();
        context.strokeStyle = `rgba(100, 100, 100, ${alpha})`;
        context.lineWidth = 1.5;
        context.arc(ripple.x, ripple.y, progress * 300, 0, 2 * Math.PI);
        context.stroke();
      });
    }

    if (!reducedMotionRef.current) {
      animationFrameId.current = window.requestAnimationFrame(animate);
    }
  }, [animationSpeed, backgroundColor, dotColor, removeWaveLine]);

  useEffect(() => {
    reducedMotionRef.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    resizeCanvas();

    const handleResize = () => {
      resizeCanvas();
      if (reducedMotionRef.current) animate();
    };
    const handlePointerMove = (event: PointerEvent) => {
      mouseRef.current = { x: event.clientX, y: event.clientY };
    };
    const handlePointerDown = (event: PointerEvent) => {
      if (reducedMotionRef.current) return;
      ripples.current.push({
        x: event.clientX,
        y: event.clientY,
        time: Date.now(),
        intensity: 1.4,
      });
    };

    window.addEventListener("resize", handleResize);
    if (!reducedMotionRef.current) {
      window.addEventListener("pointermove", handlePointerMove, { passive: true });
      window.addEventListener("pointerdown", handlePointerDown, { passive: true });
    }
    animate();

    return () => {
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerdown", handlePointerDown);
      if (animationFrameId.current !== null) {
        window.cancelAnimationFrame(animationFrameId.current);
        animationFrameId.current = null;
      }
      timeRef.current = 0;
      ripples.current = [];
      dotsRef.current = [];
    };
  }, [animate, resizeCanvas]);

  return <canvas ref={canvasRef} className="interactive-dots" aria-hidden="true" />;
}
