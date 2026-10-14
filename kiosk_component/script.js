/**
 * =============================================================================
 * SMART FACIAL ATTENDANCE KIOSK - SCRIPT LOGIC
 * =============================================================================
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Digital Clock & Calendar Date Updater
    function updateClock() {
        const now = new Date();
        const days = ['Chủ Nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];
        const dayName = days[now.getDay()];
        
        const dd = String(now.getDate()).padStart(2, '0');
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const yyyy = now.getFullYear();

        const hh = String(now.getHours()).padStart(2, '0');
        const min = String(now.getMinutes()).padStart(2, '0');
        const ss = String(now.getSeconds()).padStart(2, '0');

        const clockEl = document.getElementById('digital-clock');
        const dayEl = document.getElementById('day-name');
        const dateEl = document.getElementById('calendar-date');

        if (clockEl) clockEl.textContent = `${hh}:${min}:${ss}`;
        if (dayEl) dayEl.textContent = dayName;
        if (dateEl) dateEl.textContent = `${dd}/${mm}/${yyyy}`;
    }

    setInterval(updateClock, 1000);
    updateClock();

    // 2. Fullscreen Toggle
    const btnFullscreen = document.getElementById('btn-fullscreen');
    if (btnFullscreen) {
        btnFullscreen.addEventListener('click', () => {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(() => {});
            } else {
                if (document.exitFullscreen) document.exitFullscreen();
            }
        });
    }

    // 3. Web Camera Toggle (for Tablet Webcam integration)
    const btnCamera = document.getElementById('btn-camera');
    const videoStream = document.getElementById('camera-video-stream');
    const imgStream = document.getElementById('camera-stream-img');
    let localStream = null;

    if (btnCamera && videoStream) {
        btnCamera.addEventListener('click', async () => {
            if (localStream) {
                localStream.getTracks().forEach(t => t.stop());
                localStream = null;
                videoStream.style.display = 'none';
                if (imgStream) imgStream.style.display = 'block';
                btnCamera.style.color = '';
            } else {
                try {
                    localStream = await navigator.mediaDevices.getUserMedia({
                        video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } }
                    });
                    videoStream.srcObject = localStream;
                    await videoStream.play();
                    videoStream.style.display = 'block';
                    if (imgStream) imgStream.style.display = 'none';
                    btnCamera.style.color = '#38bdf8';
                } catch (e) {
                    console.warn('Webcam permission not granted or unavailable:', e);
                }
            }
        });
    }

    // 4. API Live Status Hook (When connected to backend server)
    async function checkApiStatus() {
        try {
            const res = await fetch('/api/status', { cache: 'no-store' });
            if (!res.ok) return;
            const data = await res.json();

            // If active card detected, update center column
            if (data.active_card) {
                const card = data.active_card;
                const profile = card.profile || {};
                const name = profile.FullName || card.name || card.code;
                const code = profile.EmployeeCode || card.code || 'NV9835';
                const dept = profile.Dept_Name || card.dept || 'BAN HẠ TẦNG';
                const time = card.time ? card.time.split(' ')[1] || card.time : '08:00:01';

                const nameEl = document.getElementById('user-fullname');
                const idEl = document.getElementById('user-empid');
                const subcodeEl = document.getElementById('user-subcode');
                const deptEl = document.getElementById('user-dept');
                const timeEl = document.getElementById('user-checkin-time');
                const avatarEl = document.getElementById('user-avatar');

                if (nameEl) nameEl.textContent = name.toUpperCase();
                if (idEl) idEl.textContent = code;
                if (subcodeEl) subcodeEl.textContent = code;
                if (deptEl) deptEl.textContent = dept.toUpperCase();
                if (timeEl) timeEl.textContent = time;

                if (card.avatar && avatarEl) {
                    avatarEl.src = card.avatar;
                }
            }

            // If real logs exist, update counter
            if (data.logs && data.logs.length > 0) {
                const counterTotal = document.getElementById('counter-total');
                if (counterTotal) counterTotal.textContent = data.logs.length;
            }
        } catch (err) {
            // Standalone mode / offline mock
        }
    }

    setInterval(checkApiStatus, 1000);
});
