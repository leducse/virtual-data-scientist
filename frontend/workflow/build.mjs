import {build} from 'esbuild';
import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../../',import.meta.url));
await build({entryPoints:[fileURLToPath(new URL('view.jsx',import.meta.url))],outfile:root+'static/workflow.js',bundle:true,minify:true,
  format:'iife',target:['es2022'],define:{'process.env.NODE_ENV':'"production"'},legalComments:'eof',logLevel:'info'});
const packages=['@xyflow/react','@xyflow/system','react','react-dom','scheduler','zustand','use-sync-external-store','classcat','d3-drag','d3-dispatch','d3-selection','d3-zoom','d3-interpolate','d3-color','d3-transition','d3-timer','d3-ease'];
let notices='Third-party licenses for the self-hosted workflow viewer.\n';
for(const name of packages){
  const base=new URL('node_modules/'+name+'/',import.meta.url);
  const pkg=JSON.parse(await readFile(new URL('package.json',base),'utf8'));
  let license;for(const file of ['LICENSE','LICENSE.txt','LICENSE.md']){try{license=await readFile(new URL(file,base),'utf8');break;}catch{}}
  if(!license)throw new Error('Missing license for '+name);
  notices+='\n--- '+name+' '+pkg.version+' ---\n'+license+'\n';
}
await writeFile(root+'static/workflow-LICENSE.txt',notices);
