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

// ─── Modo Área (F8 para abrir Overlay) ──────────────────────────────────────
let overlayWindow = null;

let originX = 0;
let originY = 0;

ipcMain.on("start-origin-mode", () => {
    if (overlayWindow) return;
    overlayWindow = new BrowserWindow({
        transparent: true, opacity: 0.5, frame: false, fullscreen: true, alwaysOnTop: true, skipTaskbar: true,
        webPreferences: { nodeIntegration: true, contextIsolation: false }
    });
    overlayWindow.loadFile(path.join(__dirname, "ui", "origin.html"));
});

ipcMain.on("start-region-mode", () => {
    if (overlayWindow) return;
    overlayWindow = new BrowserWindow({
        transparent: true, opacity: 0.5, frame: false, fullscreen: true, alwaysOnTop: true, skipTaskbar: true,
        webPreferences: { nodeIntegration: true, contextIsolation: false }
    });
    overlayWindow.loadFile(path.join(__dirname, "ui", "overlay.html"));
});

ipcMain.on("origin-selected", (event, pt) => {
    if (overlayWindow) { overlayWindow.close(); overlayWindow = null; }
    originX = pt.x;
    originY = pt.y;
    if (mainWindow) mainWindow.webContents.send("origin-set", pt);
});

ipcMain.on("region-selected", (event, bounds) => {
    if (overlayWindow) { overlayWindow.close(); overlayWindow = null; }
    if (mainWindow) {
        bounds.relX = bounds.x - originX;
        bounds.relY = bounds.y - originY;
        mainWindow.webContents.send("new-region", bounds);
    }
});

ipcMain.on("overlay-canceled", () => {
    if (overlayWindow) { overlayWindow.close(); overlayWindow = null; }
});

ipcMain.on("stop-tracking", () => {
    if (trackingInterval) {
        clearInterval(trackingInterval);
        trackingInterval = null;
    }
});

ipcMain.on("close-app", () => app.quit());
