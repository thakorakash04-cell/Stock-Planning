import type {ModelTable,Cell} from './model-data';
// Include every model table, retaining complete original columns and exposing
// the link to the selected material separately from the saved Excel value.
export function selectDetails(tables:ModelTable[],tab:number,row:Cell[],_col:number,all=false){
 const code=row[tab===2||tab===3?3:0];
 if(all)return tables;
 if(code===null||code===undefined||code==='')return tables.map(t=>({...t,rows:[]}));
 const children=new Set<Cell>();const parents=new Set<Cell>();const boms=tables.filter(t=>t.headers.includes('Material')&&t.headers.includes('Component'));
 for(const bom of boms){const mi=bom.headers.indexOf('Material'),ci=bom.headers.indexOf('Component');for(const r of bom.rows)if(r[ci]===code&&r[mi])parents.add(r[mi]);}
 const frontier:Cell[]=[code],visited=new Set<Cell>();
 while(frontier.length){const current=frontier.pop()!;if(visited.has(current))continue;visited.add(current);for(const bom of boms){const mi=bom.headers.indexOf('Material'),ci=bom.headers.indexOf('Component');for(const r of bom.rows)if(r[mi]===current&&r[ci]&&r[ci]!==code&&!children.has(r[ci])){children.add(r[ci]);frontier.push(r[ci]);}}}
 const linked=new Set<Cell>([code,...children,...parents]);
 const relation=(v:Cell)=>v===code?'Selected material':children.has(v)?'BOM component':parents.has(v)?'Product using selected component':'';
 const dates=new Set<string>();
 const matched=tables.filter(t=>t.name!=='Calendar').map(t=>{const key=['Material','Material Code','Material Number','SKU Code'].find(k=>t.headers.includes(k));const ki=key?t.headers.indexOf(key):-1;const ci=t.headers.indexOf('Component');const rows=t.rows.filter(r=>ki>=0&&(linked.has(r[ki])||(ci>=0&&r[ci]===code))).map(r=>{for(let i=0;i<t.headers.length;i++)if(/date|attribute|valid from|created on|changed on|last change/i.test(t.headers[i])&&typeof r[i]==='string'&&/^\d{4}-\d{2}-\d{2}/.test(String(r[i])))dates.add(String(r[i]).slice(0,10));return [...r,relation(r[ki])||(ci>=0&&r[ci]===code?'Product using selected component':'Related record')]});return {...t,headers:[...t.headers,'Relationship to selection'],rows}});
 const calendar=tables.find(t=>t.name==='Calendar');if(calendar){const di=calendar.headers.indexOf('Date');matched.push({...calendar,headers:[...calendar.headers,'Relationship to selection'],rows:calendar.rows.filter(r=>dates.has(String(r[di]).slice(0,10))).map(r=>[...r,'Date in related source records'])})}
 return tables.map(t=>matched.find(m=>m.name===t.name)||{...t,rows:[]});
}
