const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const os = require('os');

function activate(context) {
    console.log('Dossier Extractor is now active!');

    let disposable = vscode.commands.registerCommand('dossier.extract', async function () {
        const outDir = path.join(os.homedir(), 'REPOS', 'ClaudeDossier', 'extracted_conversations');
        fs.mkdirSync(outDir, { recursive: true });

        try {
            const ag = vscode.extensions.getExtension('google.antigravity');
            if (ag) {
                const api = await ag.activate();
                fs.writeFileSync(path.join(outDir, 'api_dump.json'), JSON.stringify(Object.keys(api || {})));

                // Let's also see if the global state has anything exposed
                const globalStateKeys = context.globalState.keys();
                fs.writeFileSync(path.join(outDir, 'global_state_keys.json'), JSON.stringify(globalStateKeys));

            } else {
                fs.writeFileSync(path.join(outDir, 'error.txt'), 'Antigravity extension not found in host');
            }
        } catch (e) {
            fs.writeFileSync(path.join(outDir, 'error.txt'), e.toString());
        }
    });

    context.subscriptions.push(disposable);

    // Auto-run on load
    setTimeout(() => {
        vscode.commands.executeCommand('dossier.extract');
    }, 2000);
}

function deactivate() { }

module.exports = {
    activate,
    deactivate
}
