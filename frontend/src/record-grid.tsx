import {useMemo} from 'react';
import DataGrid from './data-grid';
import type {Cell} from './grid-utils';
export default function RecordGrid({records,scope,download}:{records:Record<string,unknown>[];scope:string;download?:(headers:string[],rows:Cell[][])=>Promise<void>}){
 const table=useMemo(()=>{const headers=[...new Set(records.flatMap(r=>Object.keys(r)))];return {headers,rows:records.map(r=>headers.map(h=>{const v=r[h];return v==null?null:typeof v==='string'||typeof v==='number'?v:typeof v==='boolean'?String(v):JSON.stringify(v)}))}},[records]);
 return <DataGrid headers={table.headers} rows={table.rows} storageKey={scope} filename="AI result" matchedExport={download&&table.headers.length?download:undefined} exportLabel="Download result table (Excel)"/>;
}
