const { getWindows, mouse } = require("@nut-tree-fork/nut-js");
const inquirer = require("inquirer");

async function main() {
    console.log("==========================================");
    console.log(" MAPEADOR DE COORDENADAS PARA AUTOMAÇÃO ");
    console.log("==========================================");
    console.log("\nCarregando lista de janelas ativas...\n");

    const windows = await getWindows();
    const windowList = [];

    // Pegar o título de todas as janelas
    for (const win of windows) {
        try {
            const title = await win.title;
            // Só adiciona na lista se tiver um título válido
            if (title && title.trim() !== "") {
                windowList.push({ name: title, value: win });
            }
        } catch (e) {
            // Ignorar janelas que derem erro ao pegar título
        }
    }

    if (windowList.length === 0) {
        console.log("Nenhuma janela com título encontrada.");
        console.log("Se você estiver num ambiente sem interface gráfica, isso é normal.");
        return;
    }

    // Filtrar janelas com o mesmo título para deixar a lista mais limpa
    const uniqueList = windowList.filter((v, i, a) => a.findIndex(t => (t.name === v.name)) === i);

    // Perguntar ao usuário qual janela ele quer
    const answer = await inquirer.prompt([
        {
            type: "list",
            name: "selectedWindow",
            message: "Selecione o programa/janela que deseja automatizar:",
            choices: uniqueList
        }
    ]);

    const targetWindow = answer.selectedWindow;
    const title = await targetWindow.title;
    
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
