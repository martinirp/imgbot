const { getWindows, mouse } = require("@nut-tree-fork/nut-js");
const inquirer = require("inquirer");

async function main() {
    console.log("==========================================");
    console.log(" MAPEADOR DE COORDENADAS PARA AUTOMAÇÃO ");
    console.log("==========================================");
    console.log("\nCarregando lista de janelas ativas...\n");

    // Permitir passar o nome (ex: com.tibia.client) direto no terminal
    const searchName = process.argv[2];

    const windows = await getWindows();
    const windowList = [];
    let autoSelectedWindow = null;
    let autoSelectedTitle = "";

    // Pegar o título de todas as janelas (mesmo as ocultas/sem nome)
    for (const win of windows) {
        try {
            let title = await win.title;
            
            // Se o usuário passou um nome específico no terminal, a gente busca direto
            if (searchName && title && title.toLowerCase().includes(searchName.toLowerCase())) {
                autoSelectedWindow = win;
                autoSelectedTitle = title;
            }

            if (!title || title.trim() === "") {
                title = "[Janela sem título / Oculta]";
            }
            
            windowList.push({ name: title, value: win });
        } catch (e) {
            // Ignorar erros
        }
    }

    if (windowList.length === 0) {
        console.log("Nenhuma janela encontrada (nem mesmo as ocultas).");
        return;
    }

    let targetWindow;
    let title;

    if (autoSelectedWindow) {
        targetWindow = autoSelectedWindow;
        title = autoSelectedTitle;
        console.log(`\n[+] Janela encontrada automaticamente: ${title}`);
    } else {
        // Filtrar duplicatas para não sujar a lista
        const uniqueList = windowList.filter((v, i, a) => a.findIndex(t => (t.name === v.name)) === i);

        // Perguntar ao usuário qual janela ele quer
        const answer = await inquirer.prompt([
            {
                type: "list",
                name: "selectedWindow",
                message: "Selecione a janela alvo:",
                choices: uniqueList
            }
        ]);

        targetWindow = answer.selectedWindow;
        title = await targetWindow.title || "[Janela sem título]";
    }
    
    console.log(`\n[+] Janela selecionada: ${title}`);
    console.log("[+] Mova o mouse para ver as posições relativas. Pressione CTRL+C para sair.\n");

    // Fica lendo a posição do mouse a cada 100ms
    setInterval(async () => {
        try {
            const region = await targetWindow.region;
            const currentPos = await mouse.getPosition();
            
            // region contém left, top, width, height da janela
            const relX = currentPos.x - region.left;
            const relY = currentPos.y - region.top;
            
            process.stdout.write(`\rRelativo à janela -> X: ${String(relX).padStart(4)} | Y: ${String(relY).padStart(4)}  (Absoluto -> X: ${String(currentPos.x).padStart(4)} | Y: ${String(currentPos.y).padStart(4)})`);
        } catch (e) {
            // Se a janela for minimizada ou fechada
        }
    }, 100);
}

main().catch(console.error);
