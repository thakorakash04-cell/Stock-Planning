import React from 'react';
import {createRoot} from 'react-dom/client';
import Dashboard from './dashboard';
import {startBridge} from './bridge';
import './globals.css';
const root=createRoot(document.getElementById('root')!);
root.render(<p style={{padding:35,color:'#6a8979'}}>Loading your workspace…</p>);
let mounted=false;
startBridge(args=>{if(!mounted){mounted=true;root.render(<Dashboard user={args.user}/>);}});
