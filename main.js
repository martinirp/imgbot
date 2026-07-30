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

// ─── Modo Área (F8 para abrir Overlay) ──────────────────────────────────────
let overlayWindow = null;

function createOverlay() {
    if (overlayWindow) return;
    overlayWindow = new BrowserWindow({
        transparent: true,
        frame: false,
        fullscreen: true,
        alwaysOnTop: true,
        skipTaskbar: true,
        webPreferences: { nodeIntegration: true, contextIsolation: false }
    });
    overlayWindow.loadFile(path.join(__dirname, "ui", "overlay.html"));
}

let originX = 0;
let originY = 0;

ipcMain.on("start-calibration", () => {
    globalShortcut.unregisterAll();
    
    globalShortcut.register("F7", () => {
        try {
            const mouseOut = sh("xdotool getmouselocation --shell");
            const mx = parseInt(mouseOut.match(/X=(\d+)/)?.[1] || "0");
            const my = parseInt(mouseOut.match(/Y=(\d+)/)?.[1] || "0");
            originX = mx;
            originY = my;
            if (mainWindow) mainWindow.webContents.send("origin-set", { x: mx, y: my });
        } catch (_) {}
    });

    globalShortcut.register("F8", () => {
        createOverlay();
    });
});

ipcMain.on("stop-calibration", () => {
    globalShortcut.unregisterAll();
});

ipcMain.on("region-selected", (event, bounds) => {
    if (overlayWindow) { overlayWindow.close(); overlayWindow = null; }
    if (mainWindow) {
        bounds.relX = bounds.x - originX;
        bounds.relY = bounds.y - originY;
        mainWindow.webContents.send("new-region", bounds);
    }
});

ipcMain.on("region-canceled", () => {
    if (overlayWindow) { overlayWindow.close(); overlayWindow = null; }
});

ipcMain.on("stop-tracking", () => {
    if (trackingInterval) {
        clearInterval(trackingInterval);
        trackingInterval = null;
    }
});

ipcMain.on("close-app", () => app.quit());
