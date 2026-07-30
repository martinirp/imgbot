const { app, BrowserWindow, ipcMain, screen } = require("electron");
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

let originX = 0;
let originY = 0;
let trackingInterval = null;
let overlayWindow = null;

function createCoordinateOverlay() {
    if (overlayWindow) return;
    const primaryDisplay = screen.getPrimaryDisplay();
    const { width } = primaryDisplay.workAreaSize;

    overlayWindow = new BrowserWindow({
        width: 220,
        height: 60,
        x: width / 2 - 110, // Top center
        y: 20,
        transparent: true,
        opacity: 0.9,
        frame: false,
        alwaysOnTop: true,
        skipTaskbar: true,
        focusable: false,
        webPreferences: { nodeIntegration: true, contextIsolation: false }
    });
    
    // Deixa os cliques passarem direto pelo overlay (ignora mouse)
    overlayWindow.setIgnoreMouseEvents(true);
    overlayWindow.loadFile(path.join(__dirname, "ui", "overlay.html"));
}

ipcMain.on("set-origin-and-track", (event, pt) => {
    originX = pt.x;
    originY = pt.y;
    
    if (mainWindow) mainWindow.webContents.send("origin-set", pt);
    
    createCoordinateOverlay();

    if (trackingInterval) clearInterval(trackingInterval);
    trackingInterval = setInterval(() => {
        try {
            const mouseOut = sh("xdotool getmouselocation --shell");
            const mx = parseInt(mouseOut.match(/X=(\d+)/)?.[1] || "0");
            const my = parseInt(mouseOut.match(/Y=(\d+)/)?.[1] || "0");
            
            if (overlayWindow) {
                overlayWindow.webContents.send("update-coords", {
                    x: mx - originX,
                    y: my - originY
                });
            }
        } catch (_) {}
    }, 80); // Atualiza super rápido (80ms)
});

ipcMain.on("capture-mouse", (event) => {
    try {
        const mouseOut = sh("xdotool getmouselocation --shell");
        const mx = parseInt(mouseOut.match(/X=(\d+)/)?.[1] || "0");
        const my = parseInt(mouseOut.match(/Y=(\d+)/)?.[1] || "0");
        event.sender.send("mouse-captured", { x: mx, y: my });
    } catch (_) {
        event.sender.send("mouse-captured", { x: 0, y: 0 });
    }
});

ipcMain.on("stop-tracking", () => {
    if (trackingInterval) {
        clearInterval(trackingInterval);
        trackingInterval = null;
    }
    if (overlayWindow) {
        overlayWindow.close();
        overlayWindow = null;
    }
});

ipcMain.on("close-app", () => app.quit());
