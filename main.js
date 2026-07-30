const { app, BrowserWindow, ipcMain, globalShortcut } = require("electron");
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

// ─── Calibração (F8) ────────────────────────────────────────────────────────
ipcMain.on("start-calibration", (event) => {
    globalShortcut.unregisterAll();
    
    globalShortcut.register("F8", () => {
        try {
            const mouseOut = sh("xdotool getmouselocation --shell");
            const mx = parseInt(mouseOut.match(/X=(\d+)/)?.[1] || "0");
            const my = parseInt(mouseOut.match(/Y=(\d+)/)?.[1] || "0");
            
            event.sender.send("calibration-done", { x: mx, y: my });
        } catch (e) {
            console.error(e);
        }
    });
});

ipcMain.on("stop-calibration", () => {
    globalShortcut.unregister("F8");
});

// ─── Tracking de coordenadas ──────────────────────────────────────────────────
let trackingInterval = null;
let originX = 0;
let originY = 0;

ipcMain.on("start-tracking", (event, origin) => {
    if (trackingInterval) clearInterval(trackingInterval);
    originX = origin.x;
    originY = origin.y;

    trackingInterval = setInterval(() => {
        try {
            const mouseOut = sh("xdotool getmouselocation --shell");
            const mx = parseInt(mouseOut.match(/X=(\d+)/)?.[1] || "0");
            const my = parseInt(mouseOut.match(/Y=(\d+)/)?.[1] || "0");

            event.sender.send("coords-update", {
                relX: mx - originX,
                relY: my - originY,
                absX: mx,
                absY: my
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
