document.addEventListener('DOMContentLoaded', () => {
    // --- 1. CONFIGURATION ---
    const CONFIG = {
        particleCount: 30, // Reduced for "No heavy particles"
        mouseRepelRadius: 300,
        mouseRepelForce: 0.15,
        baseFloatDuration: 20
    };

    // --- 2. TYPEWRITER ANIMATION (REAL - NO CURSOR) ---
    const title = document.querySelector('.hero-title');
    if (title) {
        const textStr = "GAMEDAY TACTICS";
        title.innerHTML = ""; // Clear existing text

        // Structure: Just text, no cursor
        const textSpan = document.createElement('span');
        title.appendChild(textSpan);

        let charIndex = 0;

        function typeWriter() {
            if (charIndex < textStr.length) {
                textSpan.textContent += textStr.charAt(charIndex);
                charIndex++;
                // Slight random variance for realism
                const randomDelay = 70 + (Math.random() * 20 - 10);
                setTimeout(typeWriter, randomDelay);
            }
        }

        // Start after a minimal delay
        setTimeout(typeWriter, 300);
    }

    // --- 3. MOUSE TRACKING & PARALLAX ---
    const cursor = document.getElementById('cursor-glow');
    let mouseX = window.innerWidth / 2;
    let mouseY = window.innerHeight / 2;

    document.addEventListener('mousemove', (e) => {
        mouseX = e.clientX;
        mouseY = e.clientY;

        // Smooth Cursor Glow
        gsap.to(cursor, {
            x: mouseX,
            y: mouseY,
            duration: 0.4,
            ease: "power2.out"
        });

        // Grid Parallax
        const bg = document.querySelector('.hero-bg-grid');
        if (bg) {
            const rotX = (mouseY / window.innerHeight - 0.5) * 8 + 60;
            const moveX = (mouseX / window.innerWidth - 0.5) * -20;
            gsap.to(bg, {
                rotationX: rotX,
                x: moveX,
                duration: 1.2,
                ease: "power2.out"
            });
        }
    });

    // --- 4. PARTICLE SYSTEM WITH PHYSICS ---
    const container = document.querySelector('.hero-container');
    const particles = [];

    // Create Particles
    for (let i = 0; i < CONFIG.particleCount; i++) {
        const p = document.createElement('div');
        p.className = 'particle';

        // Random properties
        const size = Math.random() * 3 + 1;
        // prevent right/bottom overflow
        const startX = Math.random() * (window.innerWidth - size);
        const startY = Math.random() * (window.innerHeight - size);

        // CSS Init
        p.style.width = `${size}px`;
        p.style.height = `${size}px`;
        p.style.left = '0px';
        p.style.top = '0px';
        p.style.opacity = Math.random() * 0.4 + 0.1;

        container.appendChild(p);

        // Store Physics Object
        particles.push({
            el: p,
            x: startX,
            y: startY,
            vx: (Math.random() - 0.5) * 0.4,
            vy: (Math.random() - 0.5) * 0.4,
            size: size
        });
    }

    // Physics Loop
    gsap.ticker.add(() => {
        const w = window.innerWidth;
        const h = window.innerHeight;

        particles.forEach(p => {
            // 1. Base Float
            p.x += p.vx;
            p.y += p.vy;

            // Boundary Wrap (Strict)
            if (p.x < 0) p.x = w - p.size;
            if (p.x > w - p.size) p.x = 0;
            if (p.y < 0) p.y = h - p.size;
            if (p.y > h - p.size) p.y = 0;

            // 2. Mouse Repulsion
            const dx = p.x - mouseX;
            const dy = p.y - mouseY;
            const dist = Math.sqrt(dx * dx + dy * dy);

            if (dist < CONFIG.mouseRepelRadius) {
                const angle = Math.atan2(dy, dx);
                const force = (CONFIG.mouseRepelRadius - dist) * CONFIG.mouseRepelForce;

                // Physics push
                p.x += Math.cos(angle) * force;
                p.y += Math.sin(angle) * force;
            }

            // 3. Render
            gsap.set(p.el, { x: p.x, y: p.y });
        });
    });
});
