const { app, BrowserWindow, ipcMain } = require("electron");
const { execSync, exec } = require("child_process");
const path = require("path");

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

// ─── Listar janelas via wmctrl ───────────────────────────────────────────────
ipcMain.handle("get-windows", async () => {
    const windows = [];

    // Tenta wmctrl primeiro (mais confiável no GNOME/Mutter)
    try {
        const out = execSync("wmctrl -l").toString().trim();
        for (const line of out.split("\n")) {
            // Formato: 0x00400004  0 hostname  Título da Janela
            const match = line.match(/^(0x[0-9a-f]+)\s+\S+\s+\S+\s+(.+)$/i);
            if (match) {
                const id = match[1];
                const name = match[2].trim();
                if (name && name !== "N/A") {
                    windows.push({ id, name, tool: "wmctrl" });
                }
            }
        }
    } catch (_) {}

    // Fallback: xdotool (busca por todos os processos, sem filtro de visível)
    if (windows.length === 0) {
        try {
            const ids = execSync("xdotool search --name '' 2>/dev/null")
                .toString().trim().split("\n").filter(Boolean);
            for (const id of ids) {
                try {
                    const name = execSync(`xdotool getwindowname ${id} 2>/dev/null`).toString().trim();
                    if (name) windows.push({ id, name, tool: "xdotool" });
                } catch (_) {}
            }
        } catch (_) {}
    }

    // Remove duplicatas por nome e ordena
    const unique = Array.from(new Map(windows.map(w => [w.name, w])).values())
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
            const mouseOut = execSync("xdotool getmouselocation --shell").toString();
            const mx = parseInt(mouseOut.match(/X=(\d+)/)?.[1] || "0");
            const my = parseInt(mouseOut.match(/Y=(\d+)/)?.[1] || "0");

            // Posição e tamanho da janela alvo
            const geoOut = execSync(`xdotool getwindowgeometry --shell ${windowId}`).toString();
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
