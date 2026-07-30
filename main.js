const { app, BrowserWindow, ipcMain } = require("electron");
const { execSync, exec } = require("child_process");
const path = require("path");

// Garante que o DISPLAY está disponível mesmo se lançado via SSH
const ENV = { ...process.env, DISPLAY: process.env.DISPLAY || ":0" };
const sh = (cmd) => execSync(cmd, { env: ENV }).toString();

let mainWindow;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 480,
        height: 600,
        resizable: false,
        frame: false,
        transparent: true,
        alwaysOnTop: true,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
        },
    });

    mainWindow.loadFile(path.join(__dirname, "ui", "index.html"));
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => app.quit());

// ─── Listar janelas via xprop (pega XWayland + X11) ─────────────────────────
ipcMain.handle("get-windows", async () => {
    const windows = [];

    // xprop _NET_CLIENT_LIST pega TODOS os clientes X11/XWayland registrados
    try {
        const clientList = sh("xprop -root _NET_CLIENT_LIST 2>/dev/null");
        const ids = clientList.match(/0x[0-9a-f]+/gi) || [];

        for (const hexId of ids) {
            try {
                const nameProp = sh(`xprop -id ${hexId} WM_NAME 2>/dev/null`);
                const nameMatch = nameProp.match(/WM_NAME\([^)]+\)\s*=\s*"(.+)"/);
                if (!nameMatch) continue;
                const name = nameMatch[1].trim();
                if (!name) continue;
                const decId = parseInt(hexId, 16).toString();
                windows.push({ id: decId, name });
            } catch (_) {}
        }
    } catch (_) {}

    // Fallback: wmctrl se xprop não funcionar
    if (windows.length === 0) {
        try {
            const out = sh("wmctrl -l 2>/dev/null").trim();
            for (const line of out.split("\n")) {
                const match = line.match(/^(0x[0-9a-f]+)\s+\S+\s+\S+\s+(.+)$/i);
                if (match) {
                    const name = match[2].trim();
                    const decId = parseInt(match[1], 16).toString();
                    if (name && name !== "N/A") windows.push({ id: decId, name });
                }
            }
        } catch (_) {}
    }

    // Filtra janelas de sistema e remove duplicatas
    const SKIP = ["N/A", "gsd-", "ibus-", "mutter"];
    const unique = Array.from(new Map(windows.map(w => [w.name, w])).values())
        .filter(w => !SKIP.some(s => w.name.startsWith(s)))
        .sort((a, b) => a.name.localeCompare(b.name));

    return unique;
});

// ─── Tracking de coordenadas ──────────────────────────────────────────────────
let trackingInterval = null;

ipcMain.on("start-tracking", (event, windowId) => {
    if (trackingInterval) clearInterval(trackingInterval);

    trackingInterval = setInterval(() => {
        try {
            // Posição absoluta do mouse
            const mouseOut = sh("xdotool getmouselocation --shell");
            const mx = parseInt(mouseOut.match(/X=(\d+)/)?.[1] || "0");
            const my = parseInt(mouseOut.match(/Y=(\d+)/)?.[1] || "0");

            // Posição e tamanho da janela alvo
            const geoOut = sh(`xdotool getwindowgeometry --shell ${windowId}`);
            const wx = parseInt(geoOut.match(/X=(\d+)/)?.[1] || "0");
            const wy = parseInt(geoOut.match(/Y=(\d+)/)?.[1] || "0");
            const ww = parseInt(geoOut.match(/WIDTH=(\d+)/)?.[1] || "0");
            const wh = parseInt(geoOut.match(/HEIGHT=(\d+)/)?.[1] || "0");

            event.sender.send("coords-update", {
                relX: mx - wx,
                relY: my - wy,
                absX: mx,
                absY: my,
                winX: wx,
                winY: wy,
                winW: ww,
                winH: wh,
            });
        } catch (_) {}
    }, 80);
});

ipcMain.on("stop-tracking", () => {
    if (trackingInterval) {
        clearInterval(trackingInterval);
        trackingInterval = null;
    }
});

ipcMain.on("close-app", () => app.quit());
