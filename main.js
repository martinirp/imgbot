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

let originX = 0;
let originY = 0;

ipcMain.on("set-origin", (event, pt) => {
    originX = pt.x;
    originY = pt.y;
    if (mainWindow) mainWindow.webContents.send("origin-set", pt);
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

ipcMain.on("save-region", (event, bounds) => {
    if (mainWindow) {
        bounds.relX = bounds.x - originX;
        bounds.relY = bounds.y - originY;
        mainWindow.webContents.send("new-region", bounds);
    }
});

ipcMain.on("stop-tracking", () => {
    if (trackingInterval) {
        clearInterval(trackingInterval);
        trackingInterval = null;
    }
});

ipcMain.on("close-app", () => app.quit());
