# VS Code Statusline Extension

Shows Botte token savings in the VS Code status bar.

## Quick setup

Create `.vscode/extensions/botte-statusline/extension.js`:

```javascript
const vscode = require('vscode');
const { exec } = require('child_process');

function activate(context) {
    const item = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right, 100
    );
    item.command = 'botte.showCheckup';

    function update() {
        exec('python -m skills.statusline --compact',
             { cwd: vscode.workspace.rootPath },
             (err, stdout) => {
                 if (!err) item.text = stdout.trim();
                 else item.text = '🦶?';
             });
    }

    update();
    setInterval(update, 30000); // every 30s
    item.show();
}
```

## Alternative: browser bookmarklet

```javascript
javascript:(async()=>{
    const r=await fetch('http://localhost:8769/statusline');
    const t=await r.text();
    document.title=t+' '+document.title;
})();
```
